"""Unified CLI entry point for Ronin.

Dispatches subcommands to their respective modules:

    ronin setup [--step STEP]
    ronin search
    ronin apply
    ronin status
    ronin schedule install [--interval HOURS]
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
    subparsers.add_parser("apply", help="Run job applications")

    # -- status --------------------------------------------------------------
    subparsers.add_parser("status", help="Show status dashboard")

    # -- schedule ------------------------------------------------------------
    schedule_parser = subparsers.add_parser("schedule", help="Manage scheduled search")
    schedule_sub = schedule_parser.add_subparsers(
        dest="schedule_action", help="Schedule actions"
    )

    install_parser = schedule_sub.add_parser("install", help="Install scheduled search")
    install_parser.add_argument(
        "--interval",
        type=int,
        default=2,
        metavar="HOURS",
        help="Search interval in hours (default: 2)",
    )

    schedule_sub.add_parser("uninstall", help="Remove scheduled search")
    schedule_sub.add_parser("status", help="Check schedule status")

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
        from ronin.cli.apply import main as apply_main

        apply_main()

    elif args.command == "status":
        from ronin.cli.status import show_status

        show_status()

    elif args.command == "schedule":
        _handle_schedule(args, parser)


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
        console.print(
            f"[bold blue]Installing scheduled search (every {interval}h)...[/bold blue]"
        )
        if install_schedule(interval_hours=interval):
            console.print("[green]Schedule installed successfully[/green]")
        else:
            console.print("[red]Failed to install schedule[/red]")
            sys.exit(1)

    elif args.schedule_action == "uninstall":
        console.print("[bold blue]Removing scheduled search...[/bold blue]")
        if uninstall_schedule():
            console.print("[green]Schedule removed[/green]")
        else:
            console.print("[red]Failed to remove schedule[/red]")
            sys.exit(1)

    elif args.schedule_action == "status":
        status = get_schedule_status()
        if status["installed"]:
            console.print(f"[green]Installed[/green] on {status['platform']}")
            console.print(f"  Interval: every {status['interval_hours']}h")
            if status.get("next_run"):
                console.print(f"  Next run: {status['next_run']}")
        else:
            console.print("[yellow]Not installed[/yellow]")


if __name__ == "__main__":
    main()
