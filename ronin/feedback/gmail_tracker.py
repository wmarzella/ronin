"""Gmail outcome tracker for closed-loop job application feedback."""

from __future__ import annotations

import email
import imaplib
import os
import re
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from email.utils import parseaddr, parsedate_to_datetime
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup
from loguru import logger

from ronin.db import SQLiteManager


class GmailOutcomeTracker:
    """Parses Gmail for outcomes and links them to submitted applications."""

    IMAP_HOST = "imap.gmail.com"
    SYNC_STATE_KEY = "gmail_outcomes_last_sync"

    OUTCOME_PATTERNS: Dict[str, List[str]] = {
        "OFFER": [
            r"\bemployment offer\b",
            r"\bpleased to (?:offer|extend)\b",
            r"\boffer letter\b",
            r"\bcompensation package\b",
            r"\bwritten offer\b",
        ],
        "INTERVIEW": [
            r"\binterview\b",
            r"\bschedule(?:d)?\b.{0,40}\binterview\b",
            r"\bavailability\b.{0,40}\binterview\b",
            r"\bmeet with (?:the )?team\b",
            r"\bpanel interview\b",
        ],
        "CALLBACK": [
            r"\bnext steps?\b",
            r"\bphone screen\b",
            r"\bquick chat\b",
            r"\bwould like to (?:speak|chat|connect)\b",
            r"\bmove(?:d)? forward\b",
        ],
        "REJECTION": [
            r"\bunfortunately\b",
            r"\bregret to inform\b",
            r"\bnot moving forward\b",
            r"\bapplication (?:was|has been)?\s*unsuccessful\b",
            r"\bother candidates\b",
            r"\bwon'?t be progressing\b",
        ],
    }

    OUTCOME_PRIORITY: Dict[str, int] = {
        "UNKNOWN": 0,
        "REJECTION": 1,
        "CALLBACK": 2,
        "INTERVIEW": 3,
        "OFFER": 4,
    }

    TOKEN_STOPWORDS = {
        "team",
        "limited",
        "ltd",
        "pty",
        "group",
        "company",
        "the",
        "and",
        "for",
        "role",
        "position",
        "senior",
        "junior",
    }

    def __init__(
        self,
        db_manager: SQLiteManager,
        email_address: Optional[str] = None,
        app_password: Optional[str] = None,
        mailbox: str = "INBOX",
        lookback_days: int = 45,
    ):
        self.db_manager = db_manager
        self.email_address = (
            email_address
            or os.getenv("GMAIL_ADDRESS")
            or os.getenv("GOOGLE_EMAIL")
            or ""
        ).strip()
        self.app_password = (
            app_password
            or os.getenv("GMAIL_APP_PASSWORD")
            or os.getenv("GOOGLE_PASSWORD")
            or ""
        ).strip()
        self.mailbox = mailbox
        self.lookback_days = max(1, int(lookback_days))

        self._compiled_patterns: Dict[str, List[re.Pattern[str]]] = {
            outcome: [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
            for outcome, patterns in self.OUTCOME_PATTERNS.items()
        }

    def sync(self, max_messages: int = 250, dry_run: bool = False) -> Dict[str, int]:
        """Sync outcome emails from Gmail into the local outcome tables."""
        if not self.email_address or not self.app_password:
            raise ValueError(
                "Missing Gmail credentials. Set GMAIL_ADDRESS and "
                "GMAIL_APP_PASSWORD (recommended app password)."
            )

        max_messages = max(1, int(max_messages))
        since_date = self._resolve_since_date()
        applications = self.db_manager.get_applications(limit=0)

        stats = {
            "emails_scanned": 0,
            "outcome_emails": 0,
            "events_recorded": 0,
            "matched": 0,
            "duplicates": 0,
        }

        with imaplib.IMAP4_SSL(self.IMAP_HOST) as imap:
            imap.login(self.email_address, self.app_password)

            status, _ = imap.select(self.mailbox)
            if status != "OK":
                raise RuntimeError(f"Failed to open mailbox '{self.mailbox}'")

            criteria = f'(SINCE "{since_date.strftime("%d-%b-%Y")}")'
            status, data = imap.uid("search", None, criteria)
            if status != "OK":
                raise RuntimeError("Failed to search Gmail inbox")

            uids = data[0].split() if data and data[0] else []
            if len(uids) > max_messages:
                uids = uids[-max_messages:]

            stats["emails_scanned"] = len(uids)

            for uid in uids:
                event = self._fetch_event(imap=imap, uid=uid)
                if not event:
                    continue

                if event["outcome"] == "UNKNOWN":
                    continue

                stats["outcome_emails"] += 1

                matched_application_id, match_strategy = self._match_application(
                    event=event,
                    applications=applications,
                )
                event["matched_application_id"] = matched_application_id
                event["match_strategy"] = match_strategy

                if dry_run:
                    stats["events_recorded"] += 1
                    if matched_application_id:
                        stats["matched"] += 1
                    continue

                inserted = self.db_manager.record_outcome_event(event)
                if inserted:
                    stats["events_recorded"] += 1
                    if matched_application_id:
                        stats["matched"] += 1
                else:
                    stats["duplicates"] += 1

        if not dry_run:
            self.db_manager.set_sync_state(
                self.SYNC_STATE_KEY,
                datetime.now(timezone.utc).isoformat(),
            )

        return stats

    def _resolve_since_date(self) -> datetime:
        cursor = self.db_manager.get_sync_state(self.SYNC_STATE_KEY)
        if cursor:
            try:
                parsed = datetime.fromisoformat(cursor)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed - timedelta(days=2)
            except ValueError:
                logger.warning(f"Invalid gmail sync cursor '{cursor}', using lookback")

        return datetime.now(timezone.utc) - timedelta(days=self.lookback_days)

    def _fetch_event(self, imap: imaplib.IMAP4_SSL, uid: bytes) -> Optional[Dict]:
        status, data = imap.uid("fetch", uid, "(X-GM-THRID RFC822)")
        if status != "OK" or not data:
            return None

        raw_email = b""
        thread_id = ""
        for item in data:
            if isinstance(item, tuple):
                header_blob = ""
                if isinstance(item[0], bytes):
                    header_blob = item[0].decode("utf-8", errors="ignore")
                if isinstance(item[1], bytes):
                    raw_email = item[1]

                match = re.search(r"X-GM-THRID\s+(\d+)", header_blob)
                if match:
                    thread_id = match.group(1)

        if not raw_email:
            return None

        message = email.message_from_bytes(raw_email)

        subject = self._decode_header(message.get("Subject", ""))
        sender_name, sender_email = parseaddr(message.get("From", ""))
        sender = sender_email or sender_name or ""
        body = self._extract_message_text(message)
        snippet = " ".join(body.split())[:700]

        received_at = datetime.now(timezone.utc).isoformat()
        raw_date = message.get("Date")
        if raw_date:
            try:
                parsed_date = parsedate_to_datetime(raw_date)
                received_at = parsed_date.isoformat()
            except Exception:
                pass

        outcome, confidence = self._classify_outcome(subject=subject, body=body)

        message_id = (message.get("Message-ID", "") or "").strip()
        message_id = message_id.strip("<>") if message_id else f"uid-{uid.decode()}"

        return {
            "message_id": message_id,
            "thread_id": thread_id,
            "sender": sender,
            "subject": subject,
            "received_at": received_at,
            "outcome": outcome,
            "confidence": confidence,
            "snippet": snippet,
        }

    def _decode_header(self, value: str) -> str:
        if not value:
            return ""
        decoded_parts = decode_header(value)
        chunks: List[str] = []
        for text, charset in decoded_parts:
            if isinstance(text, bytes):
                enc = charset or "utf-8"
                try:
                    chunks.append(text.decode(enc, errors="replace"))
                except LookupError:
                    chunks.append(text.decode("utf-8", errors="replace"))
            else:
                chunks.append(text)
        return "".join(chunks).strip()

    def _extract_message_text(self, message: email.message.Message) -> str:
        plain_parts: List[str] = []
        html_parts: List[str] = []

        if message.is_multipart():
            for part in message.walk():
                content_type = part.get_content_type()
                disposition = part.get("Content-Disposition", "")
                if "attachment" in disposition.lower():
                    continue

                payload = part.get_payload(decode=True)
                if payload is None:
                    continue

                charset = part.get_content_charset() or "utf-8"
                try:
                    decoded = payload.decode(charset, errors="replace")
                except LookupError:
                    decoded = payload.decode("utf-8", errors="replace")

                if content_type == "text/plain":
                    plain_parts.append(decoded)
                elif content_type == "text/html":
                    html_parts.append(decoded)
        else:
            payload = message.get_payload(decode=True)
            if payload is not None:
                charset = message.get_content_charset() or "utf-8"
                try:
                    decoded = payload.decode(charset, errors="replace")
                except LookupError:
                    decoded = payload.decode("utf-8", errors="replace")

                if message.get_content_type() == "text/html":
                    html_parts.append(decoded)
                else:
                    plain_parts.append(decoded)

        if plain_parts:
            return "\n".join(plain_parts)
        if html_parts:
            soup = BeautifulSoup("\n".join(html_parts), "html.parser")
            return soup.get_text(separator=" ", strip=True)
        return ""

    def _classify_outcome(self, subject: str, body: str) -> Tuple[str, float]:
        subject_l = (subject or "").lower()
        body_l = (body or "").lower()

        scores: Dict[str, int] = {key: 0 for key in self.OUTCOME_PATTERNS}

        for outcome, patterns in self._compiled_patterns.items():
            for pattern in patterns:
                if pattern.search(subject_l):
                    scores[outcome] += 2
                if pattern.search(body_l):
                    scores[outcome] += 1

        best_outcome = "UNKNOWN"
        best_score = 0
        second_score = 0

        for outcome in ["OFFER", "INTERVIEW", "CALLBACK", "REJECTION"]:
            score = scores.get(outcome, 0)
            if score > best_score:
                second_score = best_score
                best_score = score
                best_outcome = outcome
            elif score > second_score:
                second_score = score

        if best_score == 0:
            return "UNKNOWN", 0.0

        confidence = 0.45 + min(0.45, best_score * 0.1)
        if second_score == best_score and second_score > 0:
            confidence -= 0.2
        confidence = max(0.1, min(0.99, confidence))

        return best_outcome, confidence

    def _match_application(
        self,
        event: Dict,
        applications: List[Dict],
    ) -> Tuple[Optional[int], str]:
        if not applications:
            return None, "none"

        blob = (
            f"{event.get('sender', '')} {event.get('subject', '')} {event.get('snippet', '')}"
        ).lower()
        now = datetime.now(timezone.utc)

        best_application_id: Optional[int] = None
        best_score = 0.0
        best_strategy = "none"

        for application in applications:
            score = 0.0
            strategies: list[str] = []

            job_id = str(application.get("job_id") or "").lower()
            if job_id and job_id in blob:
                score += 12.0
                strategies.append("job_id")

            company_tokens = self._extract_tokens(application.get("company_name") or "")
            company_hits = sum(1 for token in company_tokens if token in blob)
            if company_hits:
                score += float(min(company_hits, 3) * 2)
                strategies.append("company")

            title_tokens = self._extract_tokens(application.get("title") or "")
            title_hits = sum(1 for token in title_tokens if token in blob)
            if title_hits:
                score += float(min(title_hits, 4))
                strategies.append("title")

            applied_at = application.get("applied_at")
            if applied_at:
                try:
                    applied_dt = datetime.fromisoformat(applied_at)
                    if applied_dt.tzinfo is None:
                        applied_dt = applied_dt.replace(tzinfo=timezone.utc)
                    age_days = max(0, (now - applied_dt).days)
                    if age_days <= 30:
                        score += 1.0
                        strategies.append("recency")
                except ValueError:
                    pass

            if score > best_score:
                best_score = score
                best_application_id = int(application.get("id"))
                best_strategy = (
                    "+".join(sorted(set(strategies))) if strategies else "none"
                )

        if best_score < 4.0:
            return None, "none"
        return best_application_id, best_strategy

    def _extract_tokens(self, text: str) -> List[str]:
        raw_tokens = re.findall(r"[a-zA-Z]+", (text or "").lower())
        return [
            token
            for token in raw_tokens
            if len(token) >= 4 and token not in self.TOKEN_STOPWORDS
        ]
