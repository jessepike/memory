"""Sanity checks for initial package scaffold."""

from memory_core import __version__


def test_package_version_is_present() -> None:
    assert __version__ == "0.1.0"
