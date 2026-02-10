"""Tests for deterministic consolidation helpers."""

from memory_core.utils.consolidation import (
    build_idempotency_key,
    canonical_content_hash,
    canonicalize_content,
)


def test_canonicalize_content_normalizes_whitespace_case_and_punctuation() -> None:
    canonical = canonicalize_content("  Hello,\n\nWORLD!!!  ")
    assert canonical == "hello, world"


def test_canonical_hash_stable_for_equivalent_text() -> None:
    one = canonical_content_hash("Hello world!")
    two = canonical_content_hash("  hello   world ")
    assert one == two


def test_idempotency_key_scoped_by_namespace() -> None:
    key_a = build_idempotency_key("project-a", "Hello")
    key_b = build_idempotency_key("project-b", "Hello")
    assert key_a != key_b
