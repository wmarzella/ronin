"""Configuration loading and management.

Supports two config locations:
1. ~/.ronin/config.yaml (user data directory, preferred)
2. ./config.yaml (project root, fallback for development)

The RONIN_HOME env var overrides the default ~/.ronin/ path.
"""

import os
from pathlib import Path
from typing import Dict

import yaml
from dotenv import load_dotenv
from loguru import logger


def get_ronin_home() -> Path:
    """Get the Ronin home directory.

    Returns:
        Path to ~/.ronin/ or RONIN_HOME override.
    """
    env_home = os.environ.get("RONIN_HOME")
    if env_home:
        return Path(env_home).expanduser()
    return Path.home() / ".ronin"


def _find_config_file() -> Path:
    """Find the config file, checking user dir first, then project root.

    Returns:
        Path to the config.yaml file.

    Raises:
        FileNotFoundError: If no config file is found.
    """
    # 1. Check RONIN_HOME / user dir
    user_config = get_ronin_home() / "config.yaml"
    if user_config.exists():
        return user_config

    # 2. Check project root (fallback for development)
    project_config = Path(__file__).parent.parent / "config.yaml"
    if project_config.exists():
        return project_config

    raise FileNotFoundError(
        "No config.yaml found. Run 'ronin setup' to create your configuration.\n"
        f"Checked:\n"
        f"  - {user_config}\n"
        f"  - {project_config}"
    )


def _find_env_file() -> Path:
    """Find the .env file, checking user dir first, then project root.

    Returns:
        Path to the .env file (may not exist).
    """
    user_env = get_ronin_home() / ".env"
    if user_env.exists():
        return user_env

    project_env = Path(__file__).parent.parent / ".env"
    if project_env.exists():
        return project_env

    return user_env  # Return user path even if it doesn't exist


def load_config() -> Dict:
    """Load configuration from config.yaml.

    Searches for config in order:
    1. ~/.ronin/config.yaml (or RONIN_HOME)
    2. ./config.yaml (project root)

    Returns:
        Configuration dictionary.

    Raises:
        FileNotFoundError: If no config file is found.
        ValueError: If config file is not a valid YAML dictionary.
    """
    config_path = _find_config_file()

    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        if not isinstance(config, dict):
            raise ValueError(f"Config must be a dictionary, got {type(config)}")

        logger.debug(f"Loaded config from: {config_path}")
        return config
    except yaml.YAMLError as e:
        logger.error(f"Error parsing config YAML: {e}")
        raise
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        raise


def load_env():
    """Load environment variables from .env file.

    Searches for .env in order:
    1. ~/.ronin/.env (or RONIN_HOME)
    2. ./.env (project root)
    """
    env_path = _find_env_file()
    load_dotenv(dotenv_path=env_path)
    if env_path.exists():
        logger.debug(f"Loaded env from: {env_path}")


def ensure_ronin_dirs():
    """Create the Ronin directory structure if it doesn't exist."""
    home = get_ronin_home()
    dirs = [
        home,
        home / "resumes",
        home / "assets",
        home / "data",
        home / "logs",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
