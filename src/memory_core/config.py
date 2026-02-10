"""Configuration loading utilities for the Memory Layer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from memory_core.models import MemoryConfig


def load_config(path: str | Path = "config/memory_config.yaml") -> MemoryConfig:
    """Load and validate Memory Layer config from YAML."""
    config_path = Path(path)
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("Config root must be a mapping")
    return MemoryConfig.model_validate(raw)


def dump_config(config: MemoryConfig) -> dict[str, Any]:
    """Return a plain mapping representation of the config model."""
    return config.model_dump(mode="python")
