"""Cross-platform scheduling for automated job search.

Creates OS-native scheduled tasks: launchd (macOS), Task Scheduler (Windows),
or crontab (Linux). Uses RONIN_HOME env var (default ~/.ronin/) for paths.
"""

import os
import platform
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Optional

from loguru import logger

DEFAULT_SCHEDULE_COMMAND = "search"


def _plist_label(command: str) -> str:
    return f"com.ronin.{command}"


def _windows_task_name(command: str) -> str:
    title = command.capitalize()
    return f"Ronin {title}" if command != "search" else "Ronin Job Search"


# Keep this intentionally narrow; scheduled runs should be predictable.
ALLOWED_SCHEDULE_COMMANDS = {"search", "run", "apply"}


def _get_ronin_home() -> Path:
    """Get RONIN_HOME at call time (not import time)."""
    return Path(os.environ.get("RONIN_HOME", str(Path.home() / ".ronin")))


def _get_plist_path(command: str) -> Path:
    """Get the launchd plist path (macOS only, safe to call on any platform)."""
    label = _plist_label(command)
    return Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"


CRONTAB_MARKER = "# ronin-scheduled-search"


def _resolve_ronin_command() -> list:
    """Find the ronin command, returning a list of arguments.

    Checks for an installed ``ronin`` CLI first (via PATH), then falls back to
    running via ``python -m ronin.cli.main``.

    Returns:
        List of command parts (e.g. ``["ronin"]`` or
        ``["/path/to/python", "-m", "ronin.cli.main"]``).
    """
    which_ronin = shutil.which("ronin")
    if which_ronin:
        return [str(Path(which_ronin).resolve())]
    return [sys.executable, "-m", "ronin.cli.main"]


def _parse_hhmm(value: str) -> tuple[int, int]:
    """Parse HH:MM to (hour, minute)."""
    match = re.match(r"^(\d{1,2}):(\d{2})$", value.strip())
    if not match:
        raise ValueError(f"Invalid time format: {value!r} (expected HH:MM)")
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour < 0 or hour > 23:
        raise ValueError(f"Hour out of range in {value!r}")
    if minute < 0 or minute > 59:
        raise ValueError(f"Minute out of range in {value!r}")
    return hour, minute


def _current_platform() -> str:
    """Return a normalised platform string.

    Returns:
        One of ``"macos"``, ``"windows"``, or ``"linux"``.

    Raises:
        OSError: If the platform is not supported.
    """
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    if system == "windows":
        return "windows"
    if system == "linux":
        return "linux"
    raise OSError(f"Unsupported platform: {system}")


# ---------------------------------------------------------------------------
# macOS – launchd
# ---------------------------------------------------------------------------


def _macos_install(
    interval_hours: Optional[int],
    command: str,
    at_time: Optional[str],
    weekdays_only: bool,
) -> bool:
    """Write a launchd plist and load it.

    Args:
        interval_hours: How often (in hours) to run the search.

    Returns:
        True if the plist was written and loaded successfully.
    """
    ronin_cmd = _resolve_ronin_command()
    interval_seconds = (interval_hours or 0) * 3600

    ronin_home = _get_ronin_home()
    log_dir = ronin_home / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Build ProgramArguments XML entries
    args_xml = "\n".join(
        f"            <string>{part}</string>" for part in ronin_cmd + [command]
    )

    label = _plist_label(command)
    # If Ronin is being run from a source checkout (not installed as a package),
    # `python -m ronin.cli.main ...` requires the project root on sys.path.
    # Setting WorkingDirectory makes scheduled runs behave like manual runs.
    working_dir = str(Path.cwd())

    plist_xml = textwrap.dedent(
        f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
          "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
        <plist version="1.0">
        <dict>
            <key>Label</key>
            <string>{label}</string>
            <key>WorkingDirectory</key>
            <string>{working_dir}</string>
            <key>ProgramArguments</key>
            <array>
 {args_xml}
            </array>
{_macos_schedule_xml(interval_seconds, at_time, weekdays_only)}
            <key>StandardOutPath</key>
            <string>{log_dir / f"launchd_{command}.log"}</string>
            <key>StandardErrorPath</key>
            <string>{log_dir / f"launchd_{command}.log"}</string>
            <key>RunAtLoad</key>
            <true/>
        </dict>
        </plist>
    """
    )

    plist_path = _get_plist_path(command)
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(plist_xml)
    logger.info(f"Wrote plist to {plist_path}")

    # Unload first if already loaded (launchctl load is idempotent-ish but
    # prints a warning when the job is already loaded).
    subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)

    result = subprocess.run(
        ["launchctl", "load", str(plist_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.error(f"launchctl load failed: {result.stderr.strip()}")
        return False

    logger.info("launchd job loaded")
    return True


def _macos_schedule_xml(
    interval_seconds: int, at_time: Optional[str], weekdays_only: bool
) -> str:
    """Return the launchd schedule XML block."""
    if at_time:
        hour, minute = _parse_hhmm(at_time)
        if weekdays_only:
            entries = "\n".join(
                """            <dict>
                <key>Weekday</key>
                <integer>{weekday}</integer>
                <key>Hour</key>
                <integer>{hour}</integer>
                <key>Minute</key>
                <integer>{minute}</integer>
            </dict>""".format(
                    weekday=wd, hour=hour, minute=minute
                )
                for wd in range(1, 6)
            )
            return textwrap.dedent(
                f"""\
                    <key>StartCalendarInterval</key>
                    <array>
{entries}
                    </array>"""
            ).rstrip()

        return textwrap.dedent(
            f"""\
                <key>StartCalendarInterval</key>
                <dict>
                    <key>Hour</key>
                    <integer>{hour}</integer>
                    <key>Minute</key>
                    <integer>{minute}</integer>
                </dict>"""
        ).rstrip()

    # Default: interval schedule
    return textwrap.dedent(
        f"""\
            <key>StartInterval</key>
            <integer>{interval_seconds}</integer>"""
    ).rstrip()


# ---------------------------------------------------------------------------
# Windows – Task Scheduler (schtasks)
# ---------------------------------------------------------------------------


def _windows_install(
    interval_hours: Optional[int],
    command: str,
    at_time: Optional[str],
    weekdays_only: bool,
) -> bool:
    """Create a Windows scheduled task via schtasks.

    Args:
        interval_hours: How often (in hours) to run the search.

    Returns:
        True if the task was created successfully.
    """
    ronin_cmd = _resolve_ronin_command()
    command_str = " ".join(f'"{part}"' for part in ronin_cmd + [command])

    task_name = _windows_task_name(command)

    if at_time:
        hour, minute = _parse_hhmm(at_time)
        st = f"{hour:02d}:{minute:02d}"
        if weekdays_only:
            schedule_args = ["/SC", "WEEKLY", "/D", "MON,TUE,WED,THU,FRI", "/ST", st]
        else:
            schedule_args = ["/SC", "DAILY", "/ST", st]
    else:
        if not interval_hours:
            raise ValueError("interval_hours is required when at_time is not set")
        schedule_args = ["/SC", "HOURLY", "/MO", str(interval_hours)]

    result = subprocess.run(
        [
            "schtasks",
            "/Create",
            *schedule_args,
            "/TN",
            task_name,
            "/TR",
            command_str,
            "/F",  # force overwrite if exists
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.error(f"schtasks /Create failed: {result.stderr.strip()}")
        return False

    logger.info(f"Windows scheduled task '{task_name}' created")
    return True


def _windows_uninstall(command: str) -> bool:
    """Delete the Windows scheduled task.

    Returns:
        True if the task was deleted (or did not exist).
    """
    task_name = _windows_task_name(command)
    result = subprocess.run(
        ["schtasks", "/Delete", "/TN", task_name, "/F"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        # Task not existing is acceptable.
        if "does not exist" in stderr.lower() or "cannot find" in stderr.lower():
            logger.info("Windows task did not exist; nothing to uninstall")
            return True
        logger.error(f"schtasks /Delete failed: {stderr}")
        return False

    logger.info(f"Windows scheduled task '{task_name}' deleted")
    return True


def _windows_status(command: str) -> dict:
    """Query Task Scheduler for the current task status.

    Returns:
        Dict with ``installed``, ``interval_hours``, and ``next_run`` keys.
    """
    info: dict = {"installed": False, "interval_hours": 0, "next_run": None}

    task_name = _windows_task_name(command)

    result = subprocess.run(
        ["schtasks", "/Query", "/TN", task_name, "/FO", "LIST", "/V"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return info

    info["installed"] = True

    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("Next Run Time:"):
            value = line.split(":", 1)[1].strip()
            if value.lower() not in ("n/a", "disabled"):
                info["next_run"] = value
        if line.startswith("Repeat: Every"):
            # e.g. "Repeat: Every 2 Hour(s), ..."
            match = re.search(r"Every\s+(\d+)\s+Hour", line, re.IGNORECASE)
            if match:
                info["interval_hours"] = int(match.group(1))

    return info


# ---------------------------------------------------------------------------
# Linux – crontab
# ---------------------------------------------------------------------------


def _read_crontab() -> Optional[str]:
    """Read the current user's crontab.

    Returns:
        The crontab text, or None if no crontab is installed.
    """
    result = subprocess.run(
        ["crontab", "-l"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def _write_crontab(text: str) -> bool:
    """Overwrite the current user's crontab.

    Args:
        text: Full crontab content to install.

    Returns:
        True on success.
    """
    result = subprocess.run(
        ["crontab", "-"],
        input=text,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.error(f"crontab write failed: {result.stderr.strip()}")
        return False
    return True


def _linux_install(
    interval_hours: Optional[int],
    command: str,
    at_time: Optional[str],
    weekdays_only: bool,
) -> bool:
    """Add a crontab entry for the search job.

    Args:
        interval_hours: How often (in hours) to run the search.

    Returns:
        True if the crontab was updated successfully.
    """
    ronin_cmd = _resolve_ronin_command()
    ronin_home = _get_ronin_home()
    log_dir = ronin_home / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    cmd_str = " ".join(ronin_cmd + [command])
    if at_time:
        hour, minute = _parse_hhmm(at_time)
        dow = "1-5" if weekdays_only else "*"
        cron_spec = f"{minute} {hour} * * {dow}"
    else:
        if not interval_hours:
            raise ValueError("interval_hours is required when at_time is not set")
        cron_spec = f"0 */{interval_hours} * * *"

    cron_line = (
        f"{cron_spec} "
        f"{cmd_str} "
        f">> {log_dir / f'cron_{command}.log'} 2>&1 "
        f"{CRONTAB_MARKER}"
    )

    existing = _read_crontab() or ""
    # Remove any previous ronin entry.
    lines = [ln for ln in existing.splitlines() if CRONTAB_MARKER not in ln]
    lines.append(cron_line)

    new_crontab = "\n".join(lines) + "\n"
    if not _write_crontab(new_crontab):
        return False

    logger.info("Crontab entry installed")
    return True


def _linux_uninstall() -> bool:
    """Remove the ronin crontab entry.

    Returns:
        True if the entry was removed (or was already absent).
    """
    existing = _read_crontab()
    if existing is None:
        logger.info("No crontab found; nothing to uninstall")
        return True

    lines = [ln for ln in existing.splitlines() if CRONTAB_MARKER not in ln]
    new_crontab = "\n".join(lines) + "\n" if lines else ""

    if not _write_crontab(new_crontab):
        return False

    logger.info("Crontab entry removed")
    return True


def _linux_status() -> dict:
    """Check the crontab for a ronin entry.

    Returns:
        Dict with ``installed``, ``interval_hours``, and ``next_run`` keys.
    """
    info: dict = {"installed": False, "interval_hours": 0, "next_run": None}

    existing = _read_crontab()
    if existing is None:
        return info

    for line in existing.splitlines():
        if CRONTAB_MARKER in line:
            info["installed"] = True
            match = re.search(r"\*/(\d+)", line)
            if match:
                info["interval_hours"] = int(match.group(1))
            break

    return info


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def install_schedule(
    interval_hours: int = 2,
    command: str = DEFAULT_SCHEDULE_COMMAND,
    at_time: Optional[str] = None,
    weekdays_only: bool = False,
) -> bool:
    """Install a recurring OS-native scheduled task.

    Args:
        interval_hours: How often (in hours) to run the task. Defaults to 2.
            Ignored if ``at_time`` is provided.
        command: Ronin subcommand to run. Supported: "search", "run", "apply".
        at_time: Optional time-of-day in HH:MM (24h). If set, installs a
            calendar schedule instead of an interval schedule.
        weekdays_only: If True and ``at_time`` is set, run on weekdays only.

    Returns:
        True if the schedule was installed successfully.

    Raises:
        OSError: If the current platform is not supported.
    """
    if at_time is None and interval_hours < 1:
        raise ValueError(f"interval_hours must be >= 1, got {interval_hours}")

    if command not in ALLOWED_SCHEDULE_COMMANDS:
        allowed = ", ".join(sorted(ALLOWED_SCHEDULE_COMMANDS))
        raise ValueError(
            f"Unsupported scheduled command: {command}. Allowed: {allowed}"
        )

    plat = _current_platform()
    logger.info(
        (
            f"Installing schedule on {plat}: ronin {command} at {at_time}"
            if at_time
            else f"Installing schedule on {plat}: ronin {command} (every {interval_hours}h)"
        )
    )

    if plat == "macos":
        return _macos_install(interval_hours, command, at_time, weekdays_only)
    if plat == "windows":
        return _windows_install(interval_hours, command, at_time, weekdays_only)
    return _linux_install(interval_hours, command, at_time, weekdays_only)


def uninstall_schedule(command: str = DEFAULT_SCHEDULE_COMMAND) -> bool:
    """Remove the previously installed scheduled task.

    Returns:
        True if the schedule was removed (or was already absent).

    Raises:
        OSError: If the current platform is not supported.
    """
    plat = _current_platform()
    logger.info(f"Uninstalling schedule on {plat}")

    if plat == "macos":
        plist_path = _get_plist_path(command)
        if not plist_path.exists():
            logger.info("Plist does not exist; nothing to uninstall")
            return True

        result = subprocess.run(
            ["launchctl", "unload", str(plist_path)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.warning(f"launchctl unload: {result.stderr.strip()}")

        plist_path.unlink(missing_ok=True)
        logger.info("launchd job removed")
        return True
    if plat == "windows":
        return _windows_uninstall(command)
    return _linux_uninstall()


def get_schedule_status(command: str = DEFAULT_SCHEDULE_COMMAND) -> dict:
    """Return the current state of the scheduled task.

    Returns:
        A dict with the following keys:

        - ``installed`` (bool): Whether a schedule is active.
        - ``platform`` (str): One of ``"macos"``, ``"windows"``, or ``"linux"``.
        - ``interval_hours`` (int): Configured interval, or 0 if unknown.
        - ``next_run`` (str | None): Next scheduled execution time (Windows
          only; None on other platforms or when unavailable).

    Raises:
        OSError: If the current platform is not supported.
    """
    plat = _current_platform()

    if plat == "macos":
        info: dict = {"installed": False, "interval_hours": 0, "next_run": None}
        plist_path = _get_plist_path(command)
        if not plist_path.exists():
            info["platform"] = plat
            return info

        plist_text = plist_path.read_text()
        match = re.search(
            r"<key>StartInterval</key>\s*<integer>(\d+)</integer>", plist_text
        )
        interval_seconds = int(match.group(1)) if match else 0

        # Check if the job is actually loaded.
        label = _plist_label(command)
        result = subprocess.run(
            ["launchctl", "list", label],
            capture_output=True,
            text=True,
        )
        loaded = result.returncode == 0

        info["installed"] = loaded
        info["interval_hours"] = interval_seconds // 3600 if interval_seconds else 0
        info["platform"] = plat
        return info
    elif plat == "windows":
        info = _windows_status(command)
    else:
        info = _linux_status()

    info["platform"] = plat
    return info
