#!/usr/bin/env python3
"""Config editing helpers for ~/.ronin/config.yaml.

We keep this intentionally small: it exists to enable non-interactive updates
in automation environments without hand-editing YAML.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from ronin.config import get_ronin_home


def set_config_key(key_path: str, value_str: str) -> Path:
    """Set a nested config key (dot-separated) in ~/.ronin/config.yaml.

    Args:
        key_path: Dot-separated path, e.g. "search.date_range".
        value_str: Value encoded as YAML scalar, e.g. "4", "true", "hello".

    Returns:
        Path to the config file that was updated.
    """
    cfg_path = get_ronin_home() / "config.yaml"
    if not cfg_path.exists():
        raise FileNotFoundError(
            f"Config file not found at {cfg_path}. Run `ronin setup` first."
        )

    data = yaml.safe_load(cfg_path.read_text()) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid config format in {cfg_path} (expected mapping)")

    # Parse scalar using YAML so numbers/bools become typed.
    value = yaml.safe_load(value_str)

    parts = [p for p in key_path.split(".") if p]
    if not parts:
        raise ValueError("key_path must not be empty")

    cur: dict = data
    for part in parts[:-1]:
        nxt = cur.get(part)
        if nxt is None:
            nxt = {}
            cur[part] = nxt
        if not isinstance(nxt, dict):
            raise ValueError(
                f"Cannot set {key_path}: {part!r} is not a mapping in config"
            )
        cur = nxt

    cur[parts[-1]] = value

    cfg_path.write_text(
        yaml.safe_dump(
            data,
            sort_keys=False,
            default_flow_style=False,
        )
    )
    return cfg_path
