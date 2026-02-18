"""CLI helpers for Seek profile automation."""

from __future__ import annotations

from rich.console import Console

from ronin.config import load_config, load_env
from ronin.seek.profile_updater import (
    SeekLoginRequired,
    SeekProfileAutomationError,
    SeekProfileUpdater,
    SeekTemplateMissing,
    load_template_from_config,
)

console = Console()


def set_profile(archetype: str, *, yes: bool = False, dry_run: bool = False) -> int:
    """Set Seek profile content to an archetype template."""
    load_env()
    config = load_config()

    updater = SeekProfileUpdater(config=config)
    template = load_template_from_config(config, archetype)

    if not (template.headline or template.summary or template.skills):
        console.print(
            "[red]No Seek profile template configured for this archetype.[/red]\n"
            "Add content under `seek_profile.templates.<archetype>` in your `~/.ronin/config.yaml`."
        )
        return 1

    if not yes:
        console.print(
            f"\n[bold]Seek profile update preview ({template.archetype}):[/bold]"
        )
        if template.headline:
            console.print(f"- headline: {template.headline[:120]}")
        if template.summary:
            summary_preview = template.summary.replace("\n", " ").strip()
            console.print(f"- summary: {summary_preview[:160]}")
        if template.skills:
            console.print(f"- skills: {', '.join(template.skills[:12])}")
        console.print()

        from rich.prompt import Confirm

        if not Confirm.ask("Apply this to Seek now?", default=False):
            console.print("[yellow]Cancelled.[/yellow]")
            return 0

    try:
        updater.apply_archetype(
            archetype=template.archetype,
            template=template,
            dry_run=dry_run,
            allow_manual_login=True,
        )
        if dry_run:
            console.print("[green]Dry run complete.[/green]")
        else:
            console.print(
                f"[green]Seek profile updated to archetype:[/green] {template.archetype}"
            )
        return 0
    except SeekTemplateMissing as exc:
        console.print(f"[red]{exc}[/red]")
        return 1
    except SeekLoginRequired as exc:
        console.print(
            "[red]Seek login required.[/red] "
            "Run with headless disabled and complete login in the opened window.\n"
            f"Details: {exc}"
        )
        return 1
    except SeekProfileAutomationError as exc:
        console.print(f"[red]Seek profile automation failed.[/red]\n{exc}")
        return 1


def debug(url: str = "") -> int:
    """Open Playwright Inspector on the Seek profile page."""
    load_env()
    config = load_config()
    updater = SeekProfileUpdater(config=config)
    try:
        updater.debug_pause(url=url)
        return 0
    except SeekProfileAutomationError as exc:
        console.print(f"[red]{exc}[/red]")
        return 1
