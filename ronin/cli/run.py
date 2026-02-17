#!/usr/bin/env python3
"""Autopilot runner: search then apply if jobs are pending.

This command is intended for scheduled / daily automation. It runs:

1) ``ronin search``
2) If the database has jobs in a pending state, ``ronin apply``
3) If tracking.gmail.enabled is true, ``ronin feedback sync``

``ronin apply`` already avoids opening the browser when there are no pending
jobs. The extra DB check here lets scheduled runs skip the apply step entirely.
"""

from __future__ import annotations

import subprocess
import sys

from rich.console import Console

from ronin.config import load_config, load_env
from ronin.db import get_db_manager


def _best_effort_flush_spool(config: dict) -> None:
    try:
        from ronin.spool_sync import sync_spool_to_remote

        sync_spool_to_remote(config=config, dry_run=False)
    except Exception:
        return


console = Console()


def _run_cli(*args: str) -> int:
    """Run a ronin CLI subcommand in a fresh process."""
    cmd = [sys.executable, "-m", "ronin.cli.main", *args]
    proc = subprocess.run(cmd)
    return int(proc.returncode)


def main() -> None:
    load_env()
    config = load_config()
    _best_effort_flush_spool(config)
    gmail_tracking_enabled = bool(
        config.get("tracking", {}).get("gmail", {}).get("enabled", False)
    )

    console.print("\n[bold blue]Ronin Autopilot[/bold blue]\n")

    # 1) Search
    rc = _run_cli("search")
    if rc != 0:
        console.print(f"[red]Search failed (exit {rc}); skipping apply[/red]")
        sys.exit(rc)

    # 2) Apply only if there are pending jobs
    db_manager = get_db_manager(config=config)
    pending = db_manager.get_pending_jobs(limit=1)
    db_manager.close()
    if not pending:
        console.print("[yellow]No pending jobs to apply to[/yellow]")
        if gmail_tracking_enabled:
            console.print(
                "[green]Syncing Gmail outcomes for closed-loop feedback...[/green]"
            )
            feedback_rc = _run_cli("feedback", "sync")
            if feedback_rc != 0:
                console.print("[yellow]Feedback sync failed.[/yellow]")
        return

    console.print("[green]Pending jobs detected — running apply...[/green]\n")
    rc = _run_cli("apply")
    if rc != 0:
        sys.exit(rc)

    if gmail_tracking_enabled:
        console.print(
            "[green]Syncing Gmail outcomes for closed-loop feedback...[/green]"
        )
        feedback_rc = _run_cli("feedback", "sync")
        if feedback_rc != 0:
            console.print(
                "[yellow]Feedback sync failed, but search/apply completed.[/yellow]"
            )

    sys.exit(rc)


if __name__ == "__main__":
    main()
