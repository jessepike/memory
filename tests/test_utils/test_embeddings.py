"""Tests for embedding service setup/runtime behavior."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from memory_core.models import MemoryConfig
from memory_core.utils.embeddings import (
    EmbeddingMode,
    EmbeddingModelUnavailableError,
    EmbeddingService,
)


class _FakeModel:
    def __init__(self, *_args, **kwargs) -> None:
        self.kwargs = kwargs

    def encode(self, payload, normalize_embeddings: bool = True):
        assert normalize_embeddings is True
        if isinstance(payload, list):
            return [[0.1, 0.2] for _ in payload]
        return [0.1, 0.2]


def test_runtime_preflight_uses_local_files_only(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _CaptureModel(_FakeModel):
        def __init__(self, *_args, **kwargs) -> None:
            captured.update(kwargs)
            super().__init__(*_args, **kwargs)

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=_CaptureModel),
    )

    config = MemoryConfig()
    service = EmbeddingService(config, mode=EmbeddingMode.RUNTIME)
    service.preflight()

    assert captured["local_files_only"] is True


def test_setup_provision_allows_download_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _CaptureModel(_FakeModel):
        def __init__(self, *_args, **kwargs) -> None:
            captured.update(kwargs)
            super().__init__(*_args, **kwargs)

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=_CaptureModel),
    )

    config = MemoryConfig()
    service = EmbeddingService(config, mode=EmbeddingMode.SETUP)
    service.provision_model()

    assert captured["local_files_only"] is False


def test_setup_provision_fails_when_download_disabled() -> None:
    config = MemoryConfig.model_validate(
        {
            "embedding": {
                "model_name": "all-MiniLM-L6-v2",
                "allow_model_download_during_setup": False,
            }
        }
    )
    service = EmbeddingService(config, mode=EmbeddingMode.SETUP)

    with pytest.raises(EmbeddingModelUnavailableError):
        service.provision_model()


def test_embed_single_and_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=_FakeModel),
    )
    service = EmbeddingService(MemoryConfig())

    single = service.embed_text("hello")
    batch = service.embed_batch(["a", "b"])

    assert single == [0.1, 0.2]
    assert batch == [[0.1, 0.2], [0.1, 0.2]]
