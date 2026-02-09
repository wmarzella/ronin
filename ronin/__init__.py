"""Ronin - Job Search Automation."""

from pathlib import Path

from loguru import logger
from rich.console import Console

from ronin.config import load_config

_console = Console(stderr=True)

# Configure loguru — route console output through Rich, file gets everything
logger.remove()


def _rich_sink(message: str) -> None:
    _console.print(message.rstrip(), highlight=False)


def _get_log_dir() -> Path:
    """Resolve the log directory, preferring RONIN_HOME.

    Returns:
        Path to the logs directory (created if needed).
    """
    try:
        from ronin.config import get_ronin_home

        log_dir = get_ronin_home() / "logs"
    except Exception:
        log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


logger.add(
    _rich_sink,
    level="WARNING",
    format="<dim>{time:HH:mm:ss}</dim> | <level>{level: <7}</level> | {message}",
)

logger.add(
    str(_get_log_dir() / "ronin.log"),
    rotation="10 MB",
    retention="7 days",
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <7} | {name}:{function}:{line} | {message}",
)

__all__ = ["load_config"]
