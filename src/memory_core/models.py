"""Pydantic models for memory records, config, and API payloads."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MemoryType(str, Enum):
    """Allowed memory categories."""

    OBSERVATION = "observation"
    PREFERENCE = "preference"
    DECISION = "decision"
    PROGRESS = "progress"
    RELATIONSHIP = "relationship"


class WriterType(str, Enum):
    """Identity type of the memory writer."""

    AGENT = "agent"
    USER = "user"
    SYSTEM = "system"


class MemoryStatus(str, Enum):
    """Lifecycle states for memory entries."""

    STAGED = "staged"
    COMMITTED = "committed"
    FAILED = "failed"
    ARCHIVED = "archived"


class ConsolidationAction(str, Enum):
    """Outcomes of write-time consolidation."""

    ADDED = "added"
    SKIPPED = "skipped"


class MemoryBase(BaseModel):
    """Shared fields for create/update memory operations."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    content: str = Field(min_length=1)
    memory_type: MemoryType = MemoryType.OBSERVATION
    namespace: str = Field(default="global", min_length=1, max_length=128)
    writer_id: str = Field(default="unknown", min_length=1, max_length=128)
    writer_type: WriterType = WriterType.AGENT
    source_project: str | None = Field(default=None, max_length=128)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @field_validator("namespace")
    @classmethod
    def validate_namespace(cls, value: str) -> str:
        lowered = value.lower()
        if lowered in {"global", "private"}:
            return lowered
        return value


class MemoryEntry(MemoryBase):
    """Canonical memory row shape mirrored from SQLite."""

    id: UUID = Field(default_factory=uuid4)
    idempotency_key: str = Field(min_length=1)
    status: MemoryStatus = MemoryStatus.STAGED
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ClientProfile(BaseModel):
    """Static authorization profile for trusted local callers."""

    model_config = ConfigDict(extra="forbid")

    allowed_namespaces: list[str] = Field(default_factory=lambda: ["global"])
    can_cross_scope: bool = False
    can_access_private: bool = False


class PathsConfig(BaseModel):
    """Filesystem paths for runtime state."""

    model_config = ConfigDict(extra="forbid")

    sqlite_db: str = "data/memory.db"
    chroma_dir: str = "data/chroma"


class EmbeddingConfig(BaseModel):
    """Embedding model and provisioning behavior."""

    model_config = ConfigDict(extra="forbid")

    model_name: str = "all-MiniLM-L6-v2"
    allow_model_download_during_setup: bool = True


class ConsolidationConfig(BaseModel):
    """Deduplication policy configuration."""

    model_config = ConfigDict(extra="forbid")

    similarity_threshold: float = Field(default=0.92, ge=0.0, le=1.0)


class RuntimeConfig(BaseModel):
    """Runtime behavior toggles."""

    model_config = ConfigDict(extra="forbid")

    enforce_offline: bool = True


class MemoryConfig(BaseModel):
    """Top-level application config from YAML + env."""

    model_config = ConfigDict(extra="forbid")

    paths: PathsConfig = Field(default_factory=PathsConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    consolidation: ConsolidationConfig = Field(default_factory=ConsolidationConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    client_profiles: dict[str, ClientProfile] = Field(default_factory=dict)


class WriteMemoryRequest(MemoryBase):
    """Input payload for write_memory."""


class WriteMemoryResponse(BaseModel):
    """Output payload for write_memory."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    action: ConsolidationAction
    similar_id: UUID | None = None
    similarity: float | None = Field(default=None, ge=0.0, le=1.0)


class UpdateMemoryRequest(BaseModel):
    """Input payload for update_memory."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: UUID
    content: str | None = Field(default=None, min_length=1)
    memory_type: MemoryType | None = None
    namespace: str | None = Field(default=None, min_length=1, max_length=128)
    writer_id: str | None = Field(default=None, min_length=1, max_length=128)
    writer_type: WriterType | None = None
    source_project: str | None = Field(default=None, max_length=128)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class SearchMemoriesRequest(BaseModel):
    """Input payload for search_memories."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(min_length=1)
    limit: int = Field(default=20, ge=1, le=100)
    namespace: str | None = Field(default=None, min_length=1, max_length=128)
    memory_type: MemoryType | None = None
    min_similarity: float | None = Field(default=None, ge=0.0, le=1.0)


class SearchResultItem(BaseModel):
    """A single search result item."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    content: str
    memory_type: MemoryType
    namespace: str
    similarity: float = Field(ge=0.0, le=1.0)
    writer_id: str
    created_at: datetime


class ForbiddenScopeError(BaseModel):
    """Structured forbidden-scope error response."""

    model_config = ConfigDict(extra="forbid")

    error_code: str = "forbidden_scope"
    id: UUID | None = None
    namespace: str | None = None
    caller_id: str


class StatsResponse(BaseModel):
    """Summary statistics for committed memory rows."""

    model_config = ConfigDict(extra="forbid")

    total: int = Field(ge=0)
    by_type: dict[str, int] = Field(default_factory=dict)
    by_namespace: dict[str, int] = Field(default_factory=dict)
    recent_7d: int = Field(ge=0)
    recent_30d: int = Field(ge=0)
    drift: dict[str, int | str | None] | None = None


def memory_entry_from_db_row(row: dict[str, Any]) -> MemoryEntry:
    """Convert a SQLite row dict into a validated MemoryEntry."""

    return MemoryEntry.model_validate(row)
