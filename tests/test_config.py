"""Tests for config file loading and validation."""

from pathlib import Path

import pytest

from memory_core.config import dump_config, load_config


def test_load_config_from_yaml(tmp_path: Path) -> None:
    config_file = tmp_path / "memory_config.yaml"
    config_file.write_text(
        """
paths:
  sqlite_db: data/test.db
embedding:
  model_name: all-MiniLM-L6-v2
  allow_model_download_during_setup: false
runtime:
  enforce_offline: true
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_file)
    dumped = dump_config(config)

    assert config.paths.sqlite_db == "data/test.db"
    assert config.embedding.allow_model_download_during_setup is False
    assert dumped["runtime"]["enforce_offline"] is True


def test_load_config_rejects_non_mapping_root(tmp_path: Path) -> None:
    config_file = tmp_path / "memory_config.yaml"
    config_file.write_text("- not-a-mapping", encoding="utf-8")

    with pytest.raises(ValueError):
        load_config(config_file)
