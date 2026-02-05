#!/usr/bin/env python3
"""Job search CLI with progress display."""

import sys

from dotenv import load_dotenv
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

from ronin.analyzer import JobAnalyzerService
from ronin.config import load_config
from ronin.db import SQLiteManager
from ronin.scraper import SeekScraper

# Configure logging to file
logger.remove()
logger.add(
    "logs/search.log",
    rotation="10 MB",
    level="DEBUG",
    format="{time:HH:mm:ss} | {level: <7} | {message}",
)
logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level: <7} | {message}")

console = Console()


def main():
    """Main job search function."""
    load_dotenv()

    console.print("\n[bold blue]Ronin Job Search[/bold blue]\n")

    try:
        config = load_config()
        keywords = config["search"]["keywords"]
        console.print(f"[dim]Searching for {len(keywords)} keyword groups...[/dim]\n")

        scraper = SeekScraper(config)
        analyzer = JobAnalyzerService(config)  # Uses Anthropic internally
        db_manager = SQLiteManager()

        # Scrape jobs with spinner
        with console.status("[bold green]Scraping jobs from Seek...") as status:
            jobs = scraper.scrape_jobs()

        if not jobs:
            console.print("[yellow]No jobs found matching your criteria[/yellow]")
            return

        console.print(f"[green]✓[/green] Found {len(jobs)} jobs\n")

        # Filter duplicates
        stats = db_manager.get_jobs_stats()
        console.print(
            f"[dim]Checking against {stats.get('total_jobs', 0)} existing jobs...[/dim]"
        )

        new_jobs = []
        duplicate_count = 0

        for job in jobs:
            job_id = job.get("job_id", "")
            if job_id and db_manager.job_exists(job_id):
                duplicate_count += 1
            else:
                new_jobs.append(job)

        if duplicate_count > 0:
            console.print(f"[dim]Skipped {duplicate_count} duplicates[/dim]")

        if not new_jobs:
            console.print("[yellow]No new jobs to analyze[/yellow]")
            return

        console.print(f"[green]✓[/green] {len(new_jobs)} new jobs to analyze\n")

        # Analyze jobs with progress bar
        analyzed_jobs = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Analyzing jobs...", total=len(new_jobs))

            for job in new_jobs:
                title = job.get("title", "Unknown")[:40]
                progress.update(task, description=f"[cyan]Analyzing: {title}...")

                try:
                    analyzed_job = analyzer.analyze_job(job)
                    if analyzed_job:
                        analyzed_jobs.append(analyzed_job)
                except Exception:
                    pass  # Skip failed analyses silently

                progress.advance(task)

        if not analyzed_jobs:
            console.print("[yellow]No jobs were successfully analyzed[/yellow]")
            return

        # Insert to database
        with console.status("[bold green]Saving to database..."):
            results = db_manager.batch_insert_jobs(analyzed_jobs)

        # Show results table
        console.print()
        table = Table(title="Results", show_header=False, border_style="dim")
        table.add_column("Metric", style="dim")
        table.add_column("Value", style="bold")

        table.add_row("New jobs added", f"[green]{results['new_jobs']}[/green]")
        table.add_row(
            "Duplicates skipped",
            f"[yellow]{duplicate_count + results['duplicates']}[/yellow]",
        )
        if results["errors"] > 0:
            table.add_row("Errors", f"[red]{results['errors']}[/red]")

        console.print(table)
        console.print()

    except KeyboardInterrupt:
        console.print("\n[yellow]Search cancelled[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
