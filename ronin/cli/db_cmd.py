"""Database maintenance CLI commands (backup, etc)."""

from __future__ import annotations

from typing import Optional

from rich.console import Console

from ronin.backup import backup_database
from ronin.config import load_config, load_env


console = Console()


def backup_db(output_dir: Optional[str] = None, include_spool: bool = True) -> int:
    """Create a point-in-time DB backup."""
    load_env()
    config = load_config()

    result = backup_database(
        config=config,
        output_dir=output_dir,
        include_spool=include_spool,
    )

    console.print("\n[bold blue]Ronin DB Backup[/bold blue]\n")
    console.print(f"Backend: [bold]{result.backend}[/bold]")
    console.print(f"Output:  [bold]{result.output_dir}[/bold]\n")

    if result.created_files:
        console.print("Created:")
        for path in result.created_files:
            console.print(f"  [green]✓[/green] {path}")

    if result.errors:
        console.print("\nErrors:")
        for err in result.errors:
            console.print(f"  [red]✗[/red] {err}")
        return 1

    console.print("\n[green]Backup complete.[/green]")
    return 0
