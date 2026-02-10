"""Embedding generation helpers for local sentence-transformer models."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from memory_core.models import MemoryConfig


class EmbeddingMode(str, Enum):
    """Execution mode for embedding model access."""

    SETUP = "setup"
    RUNTIME = "runtime"


class EmbeddingModelUnavailableError(RuntimeError):
    """Raised when the configured embedding model is unavailable."""


class EmbeddingService:
    """Local embedding wrapper around sentence-transformers."""

    def __init__(
        self,
        config: MemoryConfig,
        *,
        mode: EmbeddingMode = EmbeddingMode.RUNTIME,
        cache_dir: str | Path | None = None,
    ) -> None:
        self.config = config
        self.mode = mode
        self.cache_dir = str(cache_dir) if cache_dir is not None else None
        self._model: Any | None = None

    @property
    def model_name(self) -> str:
        """Configured embedding model identifier."""
        return self.config.embedding.model_name

    def preflight(self) -> None:
        """Fail fast if runtime mode cannot load model from local cache."""
        self._load_model()

    def provision_model(self) -> None:
        """Install model artifacts during setup when policy allows it."""
        if not self.config.embedding.allow_model_download_during_setup:
            raise EmbeddingModelUnavailableError(
                "Model download during setup is disabled by configuration"
            )
        self._load_model(force_allow_download=True)

    def embed_text(self, text: str) -> list[float]:
        """Embed a single text input."""
        if not text.strip():
            raise ValueError("Text for embedding must be non-empty")
        vector = self._load_model().encode(text, normalize_embeddings=True)
        return [float(value) for value in vector]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of text inputs."""
        if not texts:
            return []
        for text in texts:
            if not text.strip():
                raise ValueError("Batch contains empty text input")
        vectors = self._load_model().encode(texts, normalize_embeddings=True)
        return [[float(value) for value in vector] for vector in vectors]

    def _load_model(self, *, force_allow_download: bool = False) -> Any:
        if self._model is not None:
            return self._model

        sentence_transformers = _import_sentence_transformers()
        local_only = self._should_use_local_files_only(force_allow_download=force_allow_download)

        try:
            self._model = sentence_transformers.SentenceTransformer(
                self.model_name,
                cache_folder=self.cache_dir,
                local_files_only=local_only,
            )
        except Exception as exc:  # pragma: no cover - dependency-specific details
            detail = (
                f"Unable to load embedding model '{self.model_name}' "
                f"(mode={self.mode.value}, local_files_only={local_only})."
            )
            if self.mode is EmbeddingMode.RUNTIME and local_only:
                detail += " Ensure setup provisioning has downloaded the model."
            raise EmbeddingModelUnavailableError(detail) from exc
        return self._model

    def _should_use_local_files_only(self, *, force_allow_download: bool) -> bool:
        if force_allow_download:
            return False
        if self.mode is EmbeddingMode.RUNTIME:
            return bool(self.config.runtime.enforce_offline)
        if self.mode is EmbeddingMode.SETUP:
            return not self.config.embedding.allow_model_download_during_setup
        return True


def _import_sentence_transformers() -> Any:
    try:
        import sentence_transformers  # type: ignore[import-untyped]
    except Exception as exc:  # pragma: no cover - import path is environment-specific
        raise EmbeddingModelUnavailableError(
            "sentence-transformers is required but not installed."
        ) from exc
    return sentence_transformers
