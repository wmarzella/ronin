#!/usr/bin/env python3
"""Job application CLI with progress display."""

import sys

from loguru import logger
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)
from rich.table import Table

from ronin.applier import SeekApplier
from ronin.config import load_config, load_env
from ronin.db import SQLiteManager

console = Console()

# Configure logging — file gets everything, console gets INFO+ routed through Rich
logger.remove()
logger.add(
    "logs/apply.log",
    rotation="10 MB",
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <7} | {message}",
)


def _rich_sink(message: str) -> None:
    console.print(message.rstrip(), highlight=False)


logger.add(
    _rich_sink,
    level="INFO",
    format="<dim>{time:HH:mm:ss}</dim> | <level>{level: <7}</level> | {message}",
)


def main():
    """Main job application function."""
    load_env()

    console.print("\n[bold blue]Ronin Job Applier[/bold blue]\n")

    applier = None

    try:
        config = load_config()
        applier = SeekApplier()
        db_manager = SQLiteManager()

        # Get batch limit from config (0 = unlimited)
        batch_limit = config.get("application", {}).get("batch_limit", 100)
        if batch_limit == 0:
            batch_limit = 10000  # Effectively unlimited

        # Get pending jobs
        with console.status("[bold green]Fetching pending jobs..."):
            job_records = db_manager.get_pending_jobs(limit=batch_limit)

        if not job_records:
            console.print("[yellow]No pending jobs found[/yellow]")
            console.print("[dim]Run 'make search' first to discover new jobs[/dim]")
            return

        console.print(f"[green]✓[/green] Found {len(job_records)} jobs to apply to\n")

        # Track results
        successful = 0
        failed = 0
        stale = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task(
                "[cyan]Applying to jobs...", total=len(job_records)
            )

            for record in job_records:
                job_title = record.get("title", "N/A")[:35]
                company = record.get("company_name", "N/A")[:20]
                score = record.get("score", 0)

                progress.update(
                    task, description=f"[cyan]{job_title} @ {company} (score: {score})"
                )

                try:
                    result = applier.apply_to_job(
                        job_id=record.get("job_id", ""),
                        job_description=record.get("description", ""),
                        score=score,
                        tech_stack=record.get("tech_stack", ""),
                        company_name=record.get("company_name", ""),
                        title=record.get("title", ""),
                        resume_profile=record.get("resume_profile", "default"),
                        work_type=record.get("work_type", ""),
                    )

                    record_id = record.get("id")

                    if result == "APPLIED":
                        successful += 1
                        db_manager.update_record(record_id, {"status": "APPLIED"})
                        console.print(f"  [green]✓[/green] {job_title}")
                    elif result == "STALE":
                        stale += 1
                        db_manager.update_record(record_id, {"status": "STALE"})
                        console.print(
                            f"  [yellow]○[/yellow] {job_title} [dim](expired)[/dim]"
                        )
                    else:
                        failed += 1
                        console.print(f"  [red]✗[/red] {job_title}")

                except Exception as e:
                    failed += 1
                    console.print(
                        f"  [red]✗[/red] {job_title} [dim]({str(e)[:30]})[/dim]"
                    )

                progress.advance(task)

        # Show results
        console.print()
        table = Table(title="Results", show_header=False, border_style="dim")
        table.add_column("Metric", style="dim")
        table.add_column("Value", style="bold")

        table.add_row("Applied", f"[green]{successful}[/green]")
        if stale > 0:
            table.add_row("Expired", f"[yellow]{stale}[/yellow]")
        if failed > 0:
            table.add_row("Failed", f"[red]{failed}[/red]")
        table.add_row("Total", f"{len(job_records)}")

        console.print(table)
        console.print()

    except KeyboardInterrupt:
        console.print("\n[yellow]Application cancelled[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)
    finally:
        if applier:
            applier.cleanup()
            console.print("[dim]Browser closed (session preserved)[/dim]\n")


if __name__ == "__main__":
    main()
