"""Remote worker scheduler for Gmail polling and weekly drift checks."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Dict

from loguru import logger

from ronin.config import load_config, load_env
from ronin.db import get_db_manager
from ronin.feedback import GmailOutcomeTracker, run_weekly_drift_jobs


def _env_flag(name: str):
    raw = os.environ.get(name)
    if raw is None:
        return None
    text = str(raw).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return None


def poll_and_process_gmail() -> Dict[str, int]:
    """Run one Gmail polling + parsing sync cycle."""
    load_env()
    try:
        config = load_config()
    except Exception:
        config = {}

    gmail_cfg = (
        config.get("tracking", {}).get("gmail", {}) if isinstance(config, dict) else {}
    )
    enabled = bool(gmail_cfg.get("enabled", False))
    enabled_override = _env_flag("RONIN_GMAIL_ENABLED")
    if enabled_override is None:
        enabled_override = _env_flag("RONIN_TRACKING_GMAIL_ENABLED")
    if enabled_override is not None:
        enabled = enabled_override

    if not enabled:
        logger.info("Gmail tracking disabled; skipping poll.")
        return {
            "emails_scanned": 0,
            "outcome_emails": 0,
            "events_recorded": 0,
            "matched": 0,
            "manual_review": 0,
            "duplicates": 0,
            "ignored": 0,
        }

    query = (
        os.environ.get("RONIN_GMAIL_QUERY") or gmail_cfg.get("query") or "newer_than:1d"
    )
    credentials_path = (
        os.environ.get("RONIN_GMAIL_CREDENTIALS_PATH")
        or gmail_cfg.get("credentials_path")
        or None
    )
    token_path = (
        os.environ.get("RONIN_GMAIL_TOKEN_PATH") or gmail_cfg.get("token_path") or None
    )

    db = get_db_manager(config=config, allow_spool_fallback=False)
    try:
        tracker = GmailOutcomeTracker(
            db_manager=db,
            credentials_path=credentials_path,
            token_path=token_path,
            query=query,
            auth_mode=gmail_cfg.get("auth_mode", "auto"),
        )
        max_messages_raw = (
            os.environ.get("RONIN_GMAIL_MAX_MESSAGES")
            or gmail_cfg.get("max_messages_per_sync")
            or 250
        )
        try:
            max_messages = int(max_messages_raw)
        except Exception:
            max_messages = 250
        stats = tracker.sync(max_messages=max_messages, dry_run=False)
        logger.info(f"Gmail worker sync complete: {stats}")
        return stats
    finally:
        db.close()


def run_weekly_drift() -> Dict:
    """Run weekly centroid and drift checks once."""
    load_env()
    try:
        config = load_config()
    except Exception:
        config = {}
    db = get_db_manager(config=config, allow_spool_fallback=False)
    try:
        result = run_weekly_drift_jobs(db_manager=db)
        logger.info(f"Drift worker cycle complete: {result}")
        return result
    finally:
        db.close()


def run_worker_once() -> Dict:
    """Run one full worker pass (Gmail + drift checks)."""
    return {
        "timestamp": datetime.now().isoformat(),
        "gmail": poll_and_process_gmail(),
        "drift": run_weekly_drift(),
    }


def run_worker_scheduler() -> None:
    """Start APScheduler loop for remote worker duties."""
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
    except Exception as exc:
        raise RuntimeError(
            "APScheduler is required for worker scheduler mode. "
            "Install with: pip install apscheduler"
        ) from exc

    scheduler = BlockingScheduler()

    scheduler.add_job(poll_and_process_gmail, "interval", minutes=15)
    scheduler.add_job(run_weekly_drift, "cron", day_of_week="sun", hour=0, minute=0)

    logger.info("Worker scheduler started (Gmail every 15m, drift weekly).")
    scheduler.start()
