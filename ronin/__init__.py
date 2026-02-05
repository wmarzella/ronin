"""Ronin - Job Search Automation."""

import sys

from loguru import logger

from ronin.config import load_config

# Configure loguru for cleaner output
# Remove default handler and add one that only shows warnings and above
logger.remove()
logger.add(
    sys.stderr,
    level="WARNING",
    format="<dim>{time:HH:mm:ss}</dim> | <level>{level: <7}</level> | {message}",
)

# Add file logging for debug info
logger.add(
    "logs/ronin.log",
    rotation="10 MB",
    retention="7 days",
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <7} | {name}:{function}:{line} | {message}",
)

__all__ = ["load_config"]
