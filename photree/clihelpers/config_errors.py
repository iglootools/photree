"""Rendering of configuration errors, shared by every command that reads the
config file (album/albums/gallery import and export, and the CLI entry point).
"""

from __future__ import annotations

from ..config import ConfigError


def format_config_error(exc: ConfigError) -> str:
    """Plain text (print with ``markup=False``: TOML tables look like markup)."""
    return (
        f"Invalid configuration: {exc}\n"
        "Fix the config file, or pass --config to use another one."
    )
