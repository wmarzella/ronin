"""Configuration loading and management."""

from pathlib import Path
from typing import Dict

import yaml
from dotenv import load_dotenv
from loguru import logger

# Config path - at project root
CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def load_config() -> Dict:
    """Load configuration from config.yaml."""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Config file not found: {CONFIG_PATH}")

    try:
        with open(CONFIG_PATH, "r") as f:
            config = yaml.safe_load(f)

        if not isinstance(config, dict):
            raise ValueError("Config must be a dictionary")

        return config
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        raise


def load_env():
    """Load environment variables from .env file."""
    load_dotenv()
