"""Local spool DB utilities for split local/remote operation.

When using Postgres as the primary backend, the local agent can fall back to a
local SQLite "spool" database if the remote DB is temporarily unreachable.

This module provides a best-effort sync to flush spool data into Postgres.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from loguru import logger

from ronin.config import get_ronin_home
from ronin.db import SQLiteManager, get_db_manager


def resolve_spool_db_path(config: Dict) -> Path:
    """Resolve the local spool database path from config."""
    db_cfg = config.get("database", {}) if isinstance(config, dict) else {}
    raw = (
        db_cfg.get("spool_path") if isinstance(db_cfg, dict) else None
    ) or "data/spool.db"
    path = Path(str(raw)).expanduser()
    if not path.is_absolute():
        path = (get_ronin_home() / path).resolve()
    return path


def open_spool_db(config: Dict) -> SQLiteManager:
    """Open the spool SQLite database (creating it if needed)."""
    path = resolve_spool_db_path(config)
    return SQLiteManager(db_path=str(path))


def _db_backend(config: Dict) -> str:
    backend_env = (
        os.environ.get("RONIN_DB_BACKEND")
        or os.environ.get("RONIN_DATABASE_BACKEND")
        or ""
    )
    db_cfg = config.get("database", {}) if isinstance(config, dict) else {}
    backend = backend_env or (
        db_cfg.get("backend") if isinstance(db_cfg, dict) else None
    )
    return str(backend or "sqlite").strip().lower()


def sync_spool_to_remote(
    config: Dict,
    dry_run: bool = False,
    limit_jobs: int = 0,
    limit_applications: int = 0,
) -> Dict[str, int | str]:
    """Flush local spool DB into the configured remote Postgres DB.

    This is intentionally conservative:
    - Jobs are inserted if missing (job_id unique)
    - Applications are inserted if missing (job_id unique)
    - Existing application rows are not overwritten (to avoid clobbering outcomes)

    Returns a stats dict suitable for CLI display.
    """
    backend = _db_backend(config)
    if backend not in {"postgres", "postgresql", "pg"}:
        return {"skipped": 1, "reason": "backend_not_postgres"}

    spool_path = resolve_spool_db_path(config)
    if not spool_path.exists():
        return {"skipped": 1, "reason": "no_spool_db"}

    spool = open_spool_db(config)
    try:
        cursor = spool.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM jobs")
        spool_jobs_total = int(cursor.fetchone()[0] or 0)
        cursor.execute("SELECT COUNT(*) FROM applications")
        spool_apps_total = int(cursor.fetchone()[0] or 0)
        cursor.execute("SELECT COUNT(*) FROM resume_variants")
        spool_variants_total = int(cursor.fetchone()[0] or 0)

        if (
            spool_jobs_total == 0
            and spool_apps_total == 0
            and spool_variants_total == 0
        ):
            return {"skipped": 1, "reason": "spool_empty"}

        # Connect to Postgres explicitly (no spool fallback).
        remote = get_db_manager(config=config, allow_spool_fallback=False)

        stats: Dict[str, int | str] = {
            "spool_jobs": spool_jobs_total,
            "spool_applications": spool_apps_total,
            "spool_variants": spool_variants_total,
            "jobs_inserted": 0,
            "jobs_status_updated": 0,
            "applications_inserted": 0,
            "variants_upserted": 0,
            "dry_run": 1 if dry_run else 0,
        }

        # Prefetch remote IDs to avoid N queries.
        remote_job_ids = remote.get_existing_job_ids()
        remote_cursor = remote.conn.cursor()
        remote_cursor.execute("SELECT job_id FROM applications")
        remote_app_job_ids = {str(row["job_id"]) for row in remote_cursor.fetchall()}

        # -- Jobs -----------------------------------------------------------------
        jobs_query = (
            "SELECT j.*, c.name AS company_name "
            "FROM jobs j LEFT JOIN companies c ON j.company_id = c.id "
            "ORDER BY j.created_at DESC"
        )
        params: List = []
        if limit_jobs and int(limit_jobs) > 0:
            jobs_query += " LIMIT ?"
            params.append(int(limit_jobs))
        cursor.execute(jobs_query, tuple(params))
        job_rows = [dict(row) for row in cursor.fetchall()]

        for row in job_rows:
            job_id = str(row.get("job_id") or "").strip()
            if not job_id:
                continue

            if job_id not in remote_job_ids:
                job_data = _reconstruct_job_payload(spool, row)
                if dry_run:
                    stats["jobs_inserted"] += 1
                    remote_job_ids.add(job_id)
                else:
                    ok = remote.insert_job(job_data)
                    if ok:
                        stats["jobs_inserted"] += 1
                        remote_job_ids.add(job_id)

            status = str(row.get("status") or "").strip().upper()
            if status in {"APPLIED", "STALE", "APP_ERROR"}:
                if dry_run:
                    stats["jobs_status_updated"] += 1
                else:
                    updated = _apply_remote_job_status(remote, job_id, row)
                    stats["jobs_status_updated"] += 1 if updated else 0

        # -- Applications ----------------------------------------------------------
        apps_query = "SELECT * FROM applications ORDER BY applied_at DESC"
        apps_params: List = []
        if limit_applications and int(limit_applications) > 0:
            apps_query += " LIMIT ?"
            apps_params.append(int(limit_applications))
        cursor.execute(apps_query, tuple(apps_params))
        app_rows = [dict(row) for row in cursor.fetchall()]

        for row in app_rows:
            job_id = str(row.get("job_id") or "").strip()
            if not job_id or job_id in remote_app_job_ids:
                continue

            if dry_run:
                stats["applications_inserted"] += 1
                remote_app_job_ids.add(job_id)
                continue

            inserted = _insert_remote_application_row(remote, row)
            if inserted:
                stats["applications_inserted"] += 1
                remote_app_job_ids.add(job_id)

        # -- Resume variants -------------------------------------------------------
        variants = spool.list_resume_variants()
        for variant in variants:
            if dry_run:
                stats["variants_upserted"] += 1
                continue

            ok = remote.upsert_resume_variant(
                archetype=str(variant.get("archetype") or ""),
                file_path=str(variant.get("file_path") or ""),
                commit_hash=str(variant.get("current_commit_hash") or ""),
                alignment_score=variant.get("alignment_score"),
                embedding_vector=variant.get("embedding_vector"),
                last_rewritten=variant.get("last_rewritten"),
            )
            stats["variants_upserted"] += 1 if ok else 0

        if not dry_run:
            remote.conn.commit()
            spool.set_sync_state("spool_last_flush_at", datetime.now().isoformat())

        return stats

    except Exception as exc:
        logger.error(f"Spool sync failed: {exc}")
        return {"skipped": 0, "error": str(exc)}
    finally:
        try:
            spool.close()
        except Exception:
            pass


def _reconstruct_job_payload(spool: SQLiteManager, job_row: Dict) -> Dict:
    """Rebuild the `insert_job()` payload shape from a jobs table row."""
    archetype_scores = job_row.get("archetype_scores")
    if isinstance(archetype_scores, str) and archetype_scores.strip().startswith("{"):
        try:
            archetype_scores = json.loads(archetype_scores)
        except Exception:
            pass

    analysis = {
        "score": job_row.get("score", 0),
        "key_tools": job_row.get("key_tools", ""),
        "recommendation": job_row.get("recommendation", ""),
        "overview": job_row.get("overview", ""),
        "job_classification": job_row.get("job_classification", "SHORT_TERM"),
        "resume_profile": job_row.get("resume_profile", "default"),
        "resume_archetype": job_row.get("resume_archetype", "adaptation"),
        "archetype_scores": archetype_scores,
        "archetype_primary": job_row.get("archetype_primary"),
        "embedding_vector": spool._deserialize_vector(job_row.get("embedding_vector")),
        "job_type": job_row.get("job_type", "unknown"),
        "day_rate_or_salary": job_row.get("day_rate_or_salary"),
        "seniority_level": job_row.get("seniority_level", "unknown"),
        "tech_stack_tags": job_row.get("tech_stack_tags"),
        "market_intelligence_only": bool(job_row.get("market_intelligence_only")),
        "selection_needs_review": bool(job_row.get("selection_needs_review")),
        "application_batch_id": job_row.get("application_batch_id"),
        "resume_commit_hash": job_row.get("resume_commit_hash"),
    }

    return {
        "job_id": job_row.get("job_id"),
        "title": job_row.get("title", ""),
        "company": job_row.get("company_name") or "",
        "description": job_row.get("description", ""),
        "url": job_row.get("url", ""),
        "source": job_row.get("source", ""),
        "quick_apply": bool(job_row.get("quick_apply", 0)),
        "created_at": job_row.get("created_at"),
        "pay_rate": job_row.get("pay", ""),
        "work_type": job_row.get("type", ""),
        "location": job_row.get("location", ""),
        "matching_keyword": job_row.get("matching_keyword", ""),
        "analysis": analysis,
    }


def _apply_remote_job_status(remote, job_id: str, job_row: Dict) -> bool:
    """Apply status transitions to remote jobs row without downgrading."""
    status = str(job_row.get("status") or "").strip().upper()
    if not status:
        return False

    now = datetime.now().isoformat()
    cursor = remote.conn.cursor()
    if status == "APPLIED":
        cursor.execute(
            """
            UPDATE jobs
            SET status = 'APPLIED', last_modified = %s
            WHERE job_id = %s AND status <> 'APPLIED'
        """,
            (now, job_id),
        )
    elif status == "STALE":
        cursor.execute(
            """
            UPDATE jobs
            SET status = 'STALE', last_modified = %s
            WHERE job_id = %s AND status IN ('DISCOVERED', 'APP_ERROR')
        """,
            (now, job_id),
        )
    elif status == "APP_ERROR":
        cursor.execute(
            """
            UPDATE jobs
            SET status = 'APP_ERROR', last_modified = %s
            WHERE job_id = %s AND status = 'DISCOVERED'
        """,
            (now, job_id),
        )
    else:
        return False

    # Fill missing batch/commit metadata (do not overwrite).
    batch_id = job_row.get("application_batch_id")
    commit_hash = job_row.get("resume_commit_hash")
    try:
        cursor.execute(
            """
            UPDATE jobs
            SET application_batch_id = COALESCE(application_batch_id, %s),
                resume_commit_hash = COALESCE(resume_commit_hash, %s)
            WHERE job_id = %s
        """,
            (batch_id, commit_hash, job_id),
        )
    except Exception:
        pass

    return cursor.rowcount > 0


def _insert_remote_application_row(remote, app_row: Dict) -> bool:
    """Insert one applications row into remote Postgres with DO NOTHING on conflict."""
    cursor = remote.conn.cursor()

    columns = [
        "job_id",
        "seek_job_id",
        "title",
        "job_title",
        "description",
        "job_description_text",
        "company_name",
        "source",
        "url",
        "date_scraped",
        "date_applied",
        "job_type",
        "day_rate_or_salary",
        "seniority_level",
        "tech_stack_tags",
        "search_keyword_origin",
        "archetype_scores",
        "archetype_primary",
        "embedding_vector",
        "resume_profile",
        "resume_archetype",
        "resume_variant_sent",
        "resume_commit_hash",
        "profile_state_at_application",
        "application_batch_id",
        "key_tools",
        "matching_keyword",
        "job_classification",
        "applied_at",
        "outcome",
        "outcome_confidence",
        "outcome_email_message_id",
        "outcome_email_subject",
        "outcome_email_from",
        "outcome_email_received_at",
        "outcome_updated_at",
        "outcome_stage",
        "outcome_date",
        "outcome_email_id",
        "market_intelligence_only",
        "created_at",
        "updated_at",
        "last_modified",
    ]

    values = [app_row.get(col) for col in columns]
    placeholders = ", ".join(["%s"] * len(columns))
    col_list = ", ".join(columns)

    cursor.execute(
        f"INSERT INTO applications ({col_list}) VALUES ({placeholders}) "
        "ON CONFLICT(job_id) DO NOTHING",
        tuple(values),
    )
    return cursor.rowcount > 0
