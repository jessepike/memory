"""Write-time consolidation and deduplication helper functions."""

from __future__ import annotations

import hashlib
import re
import string


_WHITESPACE_RE = re.compile(r"\s+")


def canonicalize_content(content: str) -> str:
    """Normalize content for deterministic duplicate detection."""
    normalized = _WHITESPACE_RE.sub(" ", content).strip().lower()
    return normalized.strip(string.punctuation + " ")


def canonical_content_hash(content: str) -> str:
    """Generate deterministic hash for canonicalized content."""
    canonical = canonicalize_content(content)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_idempotency_key(namespace: str, content: str) -> str:
    """Create namespace-scoped idempotency key."""
    return f"{namespace}:{canonical_content_hash(content)}"
