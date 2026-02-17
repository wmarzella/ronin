"""Database backup helpers.

Supports both:
- SQLite file copy backups
- Postgres logical backups via `pg_dump`

We intentionally do not implement retention (deleting old backups) because this
repository enforces a strict no-delete policy for automated agents.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse, urlunparse

from loguru import logger

from ronin.config import get_ronin_home
from ronin.db import SQLiteManager


@dataclass
class BackupResult:
    backend: str
    output_dir: str
    created_files: List[str]
    errors: List[str]


def _resolve_output_dir(output_dir: Optional[str]) -> Path:
    if output_dir:
        path = Path(output_dir).expanduser()
        return path if path.is_absolute() else (Path.cwd() / path).resolve()
    return (get_ronin_home() / "backups").resolve()


def _get_backend_from_config(config: Dict) -> str:
    backend_env = (
        os.environ.get("RONIN_DB_BACKEND")
        or os.environ.get("RONIN_DATABASE_BACKEND")
        or ""
    )
    cfg = config.get("database", {}) if isinstance(config, dict) else {}
    backend = backend_env or (cfg.get("backend") if isinstance(cfg, dict) else "")
    return str(backend or "sqlite").strip().lower()


def _resolve_postgres_dsn(config: Dict) -> str:
    db_cfg = config.get("database", {}) if isinstance(config, dict) else {}
    pg_cfg = db_cfg.get("postgres", {}) if isinstance(db_cfg, dict) else {}
    dsn = (
        os.environ.get("RONIN_DATABASE_DSN")
        or os.environ.get("DATABASE_URL")
        or (pg_cfg.get("dsn") if isinstance(pg_cfg, dict) else "")
        or (db_cfg.get("dsn") if isinstance(db_cfg, dict) else "")
    )
    return str(dsn or "").strip()


def _mask_password_in_dsn(dsn: str) -> tuple[str, Dict[str, str]]:
    """Return (dsn_without_password, extra_env).

    If DSN is URL-shaped and contains a password, we strip it and pass the
    password via PGPASSWORD.
    """
    extra_env: Dict[str, str] = {}
    raw = str(dsn or "").strip()
    if raw.startswith("postgresql://") or raw.startswith("postgres://"):
        parsed = urlparse(raw)
        if parsed.password:
            extra_env["PGPASSWORD"] = parsed.password
        # Rebuild netloc without password.
        username = parsed.username or ""
        host = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port else ""
        auth = f"{username}@" if username else ""
        safe_netloc = f"{auth}{host}{port}"
        safe = urlunparse(
            (
                parsed.scheme,
                safe_netloc,
                parsed.path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            )
        )
        return safe, extra_env
    return raw, extra_env


def backup_database(
    config: Dict,
    output_dir: Optional[str] = None,
    include_spool: bool = True,
) -> BackupResult:
    """Create a point-in-time backup for the configured backend."""
    backend = _get_backend_from_config(config)
    out_dir = _resolve_output_dir(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    created: List[str] = []
    errors: List[str] = []

    if backend in {"postgres", "postgresql", "pg"}:
        dsn = _resolve_postgres_dsn(config)
        if not dsn:
            errors.append("Postgres backend selected but DSN is missing")
        else:
            dump_path = out_dir / f"ronin-postgres-{ts}.sql"
            safe_dsn, extra_env = _mask_password_in_dsn(dsn)
            env = os.environ.copy()
            env.update(extra_env)
            try:
                with open(dump_path, "wb") as handle:
                    result = subprocess.run(
                        [
                            "pg_dump",
                            "--no-owner",
                            "--no-acl",
                            "--dbname",
                            safe_dsn,
                        ],
                        stdout=handle,
                        stderr=subprocess.PIPE,
                        env=env,
                    )
                if result.returncode != 0:
                    errors.append(
                        f"pg_dump failed (exit {result.returncode}): {result.stderr.decode('utf-8', errors='replace')[:300]}"
                    )
                else:
                    created.append(str(dump_path))
            except FileNotFoundError:
                errors.append("pg_dump not found in PATH")
            except Exception as exc:
                errors.append(f"pg_dump error: {exc}")

    else:
        # Default: SQLite DB file copy.
        try:
            db = SQLiteManager()
            try:
                src = Path(db.db_path)
            finally:
                db.close()

            if src.exists():
                dst = out_dir / f"ronin-sqlite-{ts}.db"
                shutil.copy2(src, dst)
                created.append(str(dst))
            else:
                errors.append(f"SQLite DB not found at {src}")
        except Exception as exc:
            errors.append(f"SQLite backup error: {exc}")

    if include_spool:
        try:
            db_cfg = config.get("database", {}) if isinstance(config, dict) else {}
            raw = (
                db_cfg.get("spool_path") if isinstance(db_cfg, dict) else None
            ) or "data/spool.db"
            spool = Path(str(raw)).expanduser()
            if not spool.is_absolute():
                spool = (get_ronin_home() / spool).resolve()
            if spool.exists():
                dst = out_dir / f"ronin-spool-{ts}.db"
                shutil.copy2(spool, dst)
                created.append(str(dst))
        except Exception as exc:
            logger.debug(f"Spool backup skipped: {exc}")

    return BackupResult(
        backend=backend,
        output_dir=str(out_dir),
        created_files=created,
        errors=errors,
    )
