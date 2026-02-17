"""Unified CLI entry point for Ronin.

Dispatches subcommands to their respective modules:

    ronin setup [--step STEP]
    ronin search
    ronin apply
    ronin apply queue
    ronin apply batch <archetype>
    ronin apply status
    ronin apply drift
    ronin apply classify <file>
    ronin apply log-call
    ronin apply sync
    ronin apply versions
    ronin apply alerts
    ronin run
    ronin feedback sync [--max-messages N] [--dry-run]
    ronin feedback report [--min-samples N]
    ronin worker start
    ronin worker once
    ronin config set --key KEY --value VALUE
    ronin status
    ronin schedule install [--interval HOURS] [--task TASK] [--at HH:MM] [--weekdays]
    ronin schedule uninstall
    ronin schedule status
"""

import argparse
import sys

from loguru import logger


__version__ = "2.0.0"


def _build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser with all subcommands.

    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        prog="ronin",
        description="Ronin — AI-Powered Job Automation Platform",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # -- setup ---------------------------------------------------------------
    setup_parser = subparsers.add_parser("setup", help="Run setup wizard")
    setup_parser.add_argument(
        "--step",
        type=str,
        default=None,
        help="Run a specific setup step instead of the full wizard",
    )

    # -- search --------------------------------------------------------------
    subparsers.add_parser("search", help="Run job search")

    # -- apply ---------------------------------------------------------------
    apply_parser = subparsers.add_parser(
        "apply",
        help="Run job applications and queue/batch workflows",
    )
    apply_sub = apply_parser.add_subparsers(dest="apply_action")

    apply_sub.add_parser("run", help="Legacy mode: apply to all pending jobs")

    apply_queue = apply_sub.add_parser(
        "queue",
        help="Show queued applications grouped by archetype",
    )
    apply_queue.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Max queued rows to preview (default: 200)",
    )

    apply_batch = apply_sub.add_parser(
        "batch",
        help="Apply to all queued jobs for an archetype",
    )
    apply_batch.add_argument(
        "archetype",
        choices=["builder", "fixer", "operator", "translator"],
        help="Archetype batch to apply",
    )
    apply_batch.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional max jobs to apply in this batch",
    )
    apply_batch.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt",
    )

    apply_sub.add_parser("status", help="Show funnel metrics and conversion rates")

    apply_corpus = apply_sub.add_parser(
        "corpus",
        help="Show corpus analysis (normalized job title counts)",
    )
    apply_corpus.add_argument(
        "--limit",
        type=int,
        default=30,
        help="Max title rows to show (default: 30)",
    )

    apply_sample = apply_sub.add_parser(
        "sample-labels",
        help="Export a JD sample JSONL for manual labeling",
    )
    apply_sample.add_argument(
        "--count",
        type=int,
        default=50,
        help="How many JDs to sample (default: 50)",
    )
    apply_sample.add_argument(
        "--output",
        type=str,
        default="labels_sample.jsonl",
        help="Output JSONL file path (default: labels_sample.jsonl)",
    )

    apply_validate = apply_sub.add_parser(
        "validate-labels",
        help="Run classifier agreement against a labeled JSONL file",
    )
    apply_validate.add_argument(
        "file",
        help="Path to labels JSONL (must include description/jd_text + manual_label)",
    )

    apply_drift = apply_sub.add_parser(
        "drift",
        help="Show drift metrics and active alerts",
    )
    apply_drift.add_argument(
        "--run-checks",
        action="store_true",
        help="Run weekly drift checks before displaying metrics",
    )

    apply_classify = apply_sub.add_parser(
        "classify",
        help="Score a single JD file and return archetype weights",
    )
    apply_classify.add_argument("file", help="Path to JD text/markdown file")

    apply_sub.add_parser(
        "log-call",
        help="Open local phone call intake form in browser",
    )

    apply_sync = apply_sub.add_parser(
        "sync",
        help="Force sync queue gating and resume variant alignments",
    )
    apply_sync.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional max jobs to re-evaluate during sync",
    )

    apply_review = apply_sub.add_parser(
        "review",
        help="Review and override close-call archetype selections",
    )
    apply_review.add_argument(
        "--limit",
        type=int,
        default=25,
        help="Max close-call rows to review (default: 25)",
    )

    apply_ghosts = apply_sub.add_parser(
        "ghosts",
        help="List ghosted applications (no signal after 30+ days)",
    )
    apply_ghosts.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max ghosted applications to show (default: 50)",
    )

    apply_versions = apply_sub.add_parser(
        "versions",
        help="Show resume commit-hash performance comparison",
    )
    apply_versions.add_argument(
        "--min-apps",
        type=int,
        default=15,
        help="Minimum applications per version row (default: 15)",
    )

    apply_sub.add_parser(
        "alerts",
        help="Show all unacknowledged drift alerts",
    )

    # -- status --------------------------------------------------------------
    subparsers.add_parser("status", help="Show status dashboard")

    # -- run -----------------------------------------------------------------
    subparsers.add_parser(
        "run",
        help="Run search then apply if jobs are pending",
    )

    # -- feedback ------------------------------------------------------------
    feedback_parser = subparsers.add_parser(
        "feedback",
        help="Sync Gmail outcomes and show feedback analytics",
    )
    feedback_sub = feedback_parser.add_subparsers(dest="feedback_action")

    feedback_sync = feedback_sub.add_parser(
        "sync",
        help="Parse Gmail for application outcomes",
    )
    feedback_sync.add_argument(
        "--max-messages",
        type=int,
        default=250,
        help="Max Gmail messages to inspect per sync (default: 250)",
    )
    feedback_sync.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and match without writing to the database",
    )

    feedback_report = feedback_sub.add_parser(
        "report",
        help="Show outcome conversion report",
    )
    feedback_report.add_argument(
        "--min-samples",
        type=int,
        default=2,
        help="Minimum sample size per bucket (default: 2)",
    )

    feedback_review = feedback_sub.add_parser(
        "review",
        help="Resolve emails requiring manual match review",
    )
    feedback_review.add_argument(
        "--limit",
        type=int,
        default=25,
        help="Max manual-review emails to show (default: 25)",
    )

    feedback_ignore = feedback_sub.add_parser(
        "ignore",
        help="Manage sender ignore list",
    )
    ignore_sub = feedback_ignore.add_subparsers(dest="ignore_action")

    ignore_add = ignore_sub.add_parser("add", help="Add an ignore rule")
    ignore_add.add_argument(
        "--domain",
        type=str,
        default="",
        help="Ignore sender domain (e.g. example.com)",
    )
    ignore_add.add_argument(
        "--address",
        type=str,
        default="",
        help="Ignore sender address (e.g. person@example.com)",
    )
    ignore_add.add_argument(
        "--reason",
        type=str,
        default="",
        help="Optional note for why this sender is ignored",
    )

    ignore_list = ignore_sub.add_parser("list", help="List ignore rules")
    ignore_list.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Max rows to display (default: 200)",
    )

    # -- worker --------------------------------------------------------------
    worker_parser = subparsers.add_parser(
        "worker",
        help="Run remote worker scheduler jobs",
    )
    worker_sub = worker_parser.add_subparsers(dest="worker_action")
    worker_sub.add_parser("start", help="Start APScheduler worker loop")
    worker_sub.add_parser("once", help="Run one worker cycle immediately")

    # -- config --------------------------------------------------------------
    config_parser = subparsers.add_parser(
        "config",
        help="Edit ~/.ronin/config.yaml",
    )
    config_sub = config_parser.add_subparsers(dest="config_action")
    config_set = config_sub.add_parser("set", help="Set a config key")
    config_set.add_argument(
        "--key",
        type=str,
        required=True,
        help='Dot path, e.g. "search.date_range"',
    )
    config_set.add_argument(
        "--value",
        type=str,
        required=True,
        help='YAML scalar, e.g. "4", "true", "hello"',
    )

    # -- db ------------------------------------------------------------------
    db_parser = subparsers.add_parser(
        "db",
        help="Database maintenance commands",
    )
    db_sub = db_parser.add_subparsers(dest="db_action")

    db_backup = db_sub.add_parser("backup", help="Create a point-in-time backup")
    db_backup.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Directory to write backups (default: ~/.ronin/backups)",
    )
    db_backup.add_argument(
        "--no-spool",
        action="store_true",
        help="Do not include the local spool DB in the backup",
    )

    # -- schedule ------------------------------------------------------------
    schedule_parser = subparsers.add_parser(
        "schedule", help="Manage scheduled automation"
    )
    schedule_sub = schedule_parser.add_subparsers(
        dest="schedule_action", help="Schedule actions"
    )

    install_parser = schedule_sub.add_parser(
        "install", help="Install scheduled automation"
    )
    install_parser.add_argument(
        "--interval",
        type=int,
        default=2,
        metavar="HOURS",
        help="Run interval in hours (default: 2)",
    )
    install_parser.add_argument(
        "--task",
        type=str,
        default="search",
        choices=["search", "run", "apply"],
        dest="scheduled_command",
        help="Ronin subcommand to schedule (default: search)",
    )
    install_parser.add_argument(
        "--at",
        type=str,
        default=None,
        metavar="HH:MM",
        help="Time-of-day to run (24h). If set, overrides --interval",
    )
    install_parser.add_argument(
        "--weekdays",
        action="store_true",
        help="When used with --at, run Monday-Friday only",
    )

    uninstall_parser = schedule_sub.add_parser("uninstall", help="Remove a schedule")
    uninstall_parser.add_argument(
        "--task",
        type=str,
        default="search",
        choices=["search", "run", "apply"],
        dest="scheduled_command",
        help="Ronin subcommand schedule to remove (default: search)",
    )

    status_parser = schedule_sub.add_parser("status", help="Check schedule status")
    status_parser.add_argument(
        "--task",
        type=str,
        default="search",
        choices=["search", "run", "apply"],
        dest="scheduled_command",
        help="Ronin subcommand schedule to inspect (default: search)",
    )

    return parser


def main() -> None:
    """Parse arguments and dispatch to the appropriate module."""
    from ronin.config import load_env

    load_env()

    parser = _build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    logger.debug(f"CLI command: {args.command}")

    if args.command == "setup":
        from ronin.cli.setup import run_setup

        run_setup(step=args.step)

    elif args.command == "search":
        from ronin.cli.search import main as search_main

        search_main()

    elif args.command == "apply":
        apply_action = getattr(args, "apply_action", None)
        if apply_action in (None, "run"):
            from ronin.cli.apply import main as apply_main

            apply_main()
        elif apply_action == "queue":
            from ronin.cli.apply_ops import show_queue

            rc = show_queue(limit=getattr(args, "limit", 200))
            if rc != 0:
                sys.exit(rc)
        elif apply_action == "batch":
            from ronin.cli.apply_ops import batch_apply

            rc = batch_apply(
                archetype=getattr(args, "archetype"),
                limit=int(getattr(args, "limit", 0) or 0),
                yes=bool(getattr(args, "yes", False)),
            )
            if rc != 0:
                sys.exit(rc)
        elif apply_action == "status":
            from ronin.cli.apply_ops import show_apply_status

            rc = show_apply_status()
            if rc != 0:
                sys.exit(rc)
        elif apply_action == "corpus":
            from ronin.cli.apply_ops import show_corpus

            rc = show_corpus(limit=int(getattr(args, "limit", 30) or 30))
            if rc != 0:
                sys.exit(rc)
        elif apply_action == "sample-labels":
            from ronin.cli.apply_ops import sample_labels

            rc = sample_labels(
                count=int(getattr(args, "count", 50) or 50),
                output_path=str(getattr(args, "output", "labels_sample.jsonl")),
            )
            if rc != 0:
                sys.exit(rc)
        elif apply_action == "validate-labels":
            from ronin.cli.apply_ops import validate_labels

            rc = validate_labels(str(getattr(args, "file")))
            if rc != 0:
                sys.exit(rc)
        elif apply_action == "drift":
            from ronin.cli.apply_ops import show_drift

            rc = show_drift(run_checks=bool(getattr(args, "run_checks", False)))
            if rc != 0:
                sys.exit(rc)
        elif apply_action == "classify":
            from ronin.cli.apply_ops import classify_file

            rc = classify_file(getattr(args, "file"))
            if rc != 0:
                sys.exit(rc)
        elif apply_action == "log-call":
            from ronin.cli.apply_ops import log_call

            rc = log_call()
            if rc != 0:
                sys.exit(rc)
        elif apply_action == "sync":
            from ronin.cli.apply_ops import sync_queue

            rc = sync_queue(limit=int(getattr(args, "limit", 0) or 0))
            if rc != 0:
                sys.exit(rc)
        elif apply_action == "review":
            from ronin.cli.apply_ops import review_selections

            rc = review_selections(limit=int(getattr(args, "limit", 25) or 25))
            if rc != 0:
                sys.exit(rc)
        elif apply_action == "ghosts":
            from ronin.cli.apply_ops import show_ghosts

            rc = show_ghosts(limit=int(getattr(args, "limit", 50) or 50))
            if rc != 0:
                sys.exit(rc)
        elif apply_action == "versions":
            from ronin.cli.apply_ops import show_versions

            rc = show_versions(min_apps=int(getattr(args, "min_apps", 15) or 15))
            if rc != 0:
                sys.exit(rc)
        elif apply_action == "alerts":
            from ronin.cli.apply_ops import show_alerts

            rc = show_alerts()
            if rc != 0:
                sys.exit(rc)
        else:
            parser.parse_args(["apply", "--help"])
            return

    elif args.command == "run":
        from ronin.cli.run import main as run_main

        run_main()

    elif args.command == "feedback":
        from ronin.cli.feedback import (
            review_manual_matches,
            show_feedback_report,
            sync_gmail_outcomes,
        )

        if args.feedback_action == "sync":
            rc = sync_gmail_outcomes(
                max_messages=getattr(args, "max_messages", 250),
                dry_run=bool(getattr(args, "dry_run", False)),
            )
            if rc != 0:
                sys.exit(rc)
        elif args.feedback_action == "report":
            rc = show_feedback_report(
                min_samples=getattr(args, "min_samples", 2),
            )
            if rc != 0:
                sys.exit(rc)
        elif args.feedback_action == "review":
            rc = review_manual_matches(limit=int(getattr(args, "limit", 25) or 25))
            if rc != 0:
                sys.exit(rc)
        elif args.feedback_action == "ignore":
            from ronin.cli.feedback import add_sender_ignore, list_sender_ignores

            ignore_action = getattr(args, "ignore_action", None)
            if ignore_action == "add":
                rc = add_sender_ignore(
                    sender_domain=str(getattr(args, "domain", "")),
                    sender_address=str(getattr(args, "address", "")),
                    reason=str(getattr(args, "reason", "")),
                )
                if rc != 0:
                    sys.exit(rc)
            elif ignore_action == "list":
                rc = list_sender_ignores(limit=int(getattr(args, "limit", 200)))
                if rc != 0:
                    sys.exit(rc)
            else:
                parser.parse_args(["feedback", "ignore", "--help"])
                return
        else:
            parser.parse_args(["feedback", "--help"])
            return

    elif args.command == "worker":
        from rich.console import Console

        from ronin.worker import run_worker_once, run_worker_scheduler

        console = Console(stderr=True)
        action = getattr(args, "worker_action", None)
        if action == "start":
            console.print("[bold blue]Starting worker scheduler...[/bold blue]")
            try:
                run_worker_scheduler()
            except Exception as exc:
                console.print(f"[red]Worker start failed:[/red] {exc}")
                sys.exit(1)
        elif action == "once":
            console.print("[bold blue]Running one worker cycle...[/bold blue]")
            try:
                result = run_worker_once()
                console.print(result)
            except Exception as exc:
                console.print(f"[red]Worker run failed:[/red] {exc}")
                sys.exit(1)
        else:
            parser.parse_args(["worker", "--help"])
            return

    elif args.command == "status":
        from ronin.cli.status import show_status

        show_status()

    elif args.command == "config":
        if args.config_action == "set":
            from rich.console import Console

            from ronin.cli.config_cmd import set_config_key

            console = Console(stderr=True)
            path = set_config_key(args.key, args.value)
            console.print(f"[green]Updated[/green] {path}")
        else:
            parser.parse_args(["config", "--help"])
            return

    elif args.command == "schedule":
        _handle_schedule(args, parser)

    elif args.command == "db":
        from ronin.cli.db_cmd import backup_db

        action = getattr(args, "db_action", None)
        if action == "backup":
            rc = backup_db(
                output_dir=getattr(args, "output_dir", None),
                include_spool=not bool(getattr(args, "no_spool", False)),
            )
            if rc != 0:
                sys.exit(rc)
        else:
            parser.parse_args(["db", "--help"])
            return


def _handle_schedule(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    """Dispatch schedule sub-actions.

    Args:
        args: Parsed CLI arguments.
        parser: Root parser (used to print help on missing sub-action).
    """
    from rich.console import Console

    from ronin.scheduler import (
        get_schedule_status,
        install_schedule,
        uninstall_schedule,
    )

    console = Console(stderr=True)

    if args.schedule_action is None:
        parser.parse_args(["schedule", "--help"])
        return

    if args.schedule_action == "install":
        interval: int = args.interval
        command: str = getattr(args, "scheduled_command", "search")
        at_time: str | None = getattr(args, "at", None)
        weekdays_only: bool = bool(getattr(args, "weekdays", False))
        console.print(
            (
                f"[bold blue]Installing schedule: ronin {command} at {at_time}...[/bold blue]"
                if at_time
                else f"[bold blue]Installing schedule: ronin {command} (every {interval}h)...[/bold blue]"
            )
        )
        if install_schedule(
            interval_hours=interval,
            command=command,
            at_time=at_time,
            weekdays_only=weekdays_only,
        ):
            console.print("[green]Schedule installed successfully[/green]")
        else:
            console.print("[red]Failed to install schedule[/red]")
            sys.exit(1)

    elif args.schedule_action == "uninstall":
        command: str = getattr(args, "scheduled_command", "search")
        console.print("[bold blue]Removing scheduled search...[/bold blue]")
        if uninstall_schedule(command=command):
            console.print("[green]Schedule removed[/green]")
        else:
            console.print("[red]Failed to remove schedule[/red]")
            sys.exit(1)

    elif args.schedule_action == "status":
        command: str = getattr(args, "scheduled_command", "search")
        status = get_schedule_status(command=command)
        if status["installed"]:
            console.print(f"[green]Installed[/green] on {status['platform']}")
            console.print(f"  Interval: every {status['interval_hours']}h")
            if status.get("next_run"):
                console.print(f"  Next run: {status['next_run']}")
        else:
            console.print("[yellow]Not installed[/yellow]")


if __name__ == "__main__":
    main()
