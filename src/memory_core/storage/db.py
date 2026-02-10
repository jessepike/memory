"""SQLite persistence layer for memory metadata and lifecycle state."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from memory_core.models import MemoryEntry, MemoryStatus, memory_entry_from_db_row


class MemoryNotFoundError(Exception):
    """Raised when a memory row cannot be found."""


class IdempotencyConflictError(Exception):
    """Raised when staged insert collides with an active idempotency key."""

    def __init__(self, existing_id: UUID | None) -> None:
        self.existing_id = existing_id
        super().__init__("Active idempotency key already exists")


@dataclass(frozen=True)
class MemoryStats:
    """Committed-memory stats summary."""

    total: int
    by_type: dict[str, int]
    by_namespace: dict[str, int]
    recent_7d: int
    recent_30d: int


class SQLiteMemoryDB:
    """SQLite access layer used by MemoryStorage."""

    def __init__(self, db_path: str | Path, schema_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path)
        default_schema = Path(__file__).with_name("schema.sql")
        self.schema_path = Path(schema_path) if schema_path is not None else default_schema

    def initialize(self) -> None:
        """Create DB file, apply pragmas, and load schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        schema_sql = self.schema_path.read_text(encoding="utf-8")
        with self._connect() as conn:
            conn.executescript(schema_sql)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA temp_store=MEMORY;")

    @contextmanager
    def begin_immediate(self) -> Iterator[sqlite3.Connection]:
        """Open a write transaction for deterministic staged reservations."""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def insert_staged(self, entry: MemoryEntry) -> None:
        """Insert a staged row, raising on active idempotency collisions."""
        payload = entry.model_dump(mode="json")
        sql = """
        INSERT INTO memories (
            id, content, memory_type, namespace, writer_id, writer_type,
            source_project, idempotency_key, confidence, status, created_at, updated_at
        ) VALUES (
            :id, :content, :memory_type, :namespace, :writer_id, :writer_type,
            :source_project, :idempotency_key, :confidence, :status, :created_at, :updated_at
        );
        """
        try:
            with self.begin_immediate() as conn:
                conn.execute(sql, payload)
        except sqlite3.IntegrityError as exc:
            if "idx_memories_idempotency_active" in str(exc) or "idempotency_key" in str(exc):
                existing_id = self.get_active_id_by_idempotency_key(entry.idempotency_key)
                raise IdempotencyConflictError(existing_id) from exc
            raise

    def get_active_id_by_idempotency_key(self, idempotency_key: str) -> UUID | None:
        """Return active row ID for an idempotency key."""
        sql = """
        SELECT id
        FROM memories
        WHERE idempotency_key = ?
          AND status IN (?, ?)
        LIMIT 1;
        """
        with self._connect() as conn:
            row = conn.execute(
                sql, (idempotency_key, MemoryStatus.STAGED.value, MemoryStatus.COMMITTED.value)
            ).fetchone()
        return UUID(row["id"]) if row else None

    def get_memory(self, memory_id: UUID | str) -> MemoryEntry | None:
        """Fetch one memory by ID."""
        sql = "SELECT * FROM memories WHERE id = ? LIMIT 1;"
        with self._connect() as conn:
            row = conn.execute(sql, (str(memory_id),)).fetchone()
        if row is None:
            return None
        return self._row_to_entry(row)

    def list_memories(
        self,
        *,
        statuses: list[MemoryStatus] | None = None,
        namespaces: list[str] | None = None,
        memory_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[MemoryEntry]:
        """List memories with optional lifecycle and scope filters."""
        clauses: list[str] = []
        params: list[Any] = []

        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            clauses.append(f"status IN ({placeholders})")
            params.extend(status.value for status in statuses)

        if namespaces:
            placeholders = ", ".join("?" for _ in namespaces)
            clauses.append(f"namespace IN ({placeholders})")
            params.extend(namespaces)

        if memory_type is not None:
            clauses.append("memory_type = ?")
            params.append(memory_type)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
        SELECT * FROM memories
        {where}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?;
        """
        params.extend([limit, offset])

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def update_memory(self, memory_id: UUID | str, **updates: Any) -> MemoryEntry:
        """Update mutable memory fields and return the fresh row."""
        allowed = {
            "content",
            "memory_type",
            "namespace",
            "writer_id",
            "writer_type",
            "source_project",
            "confidence",
            "status",
            "idempotency_key",
        }
        invalid = set(updates).difference(allowed)
        if invalid:
            raise ValueError(f"Unsupported update fields: {sorted(invalid)}")
        if not updates:
            existing = self.get_memory(memory_id)
            if existing is None:
                raise MemoryNotFoundError(f"Memory not found: {memory_id}")
            return existing

        updates["updated_at"] = datetime.now(UTC).isoformat()
        assignments = ", ".join(f"{key} = ?" for key in updates)
        params = list(updates.values()) + [str(memory_id)]
        sql = f"UPDATE memories SET {assignments} WHERE id = ?;"

        with self.begin_immediate() as conn:
            result = conn.execute(sql, params)
            if result.rowcount == 0:
                raise MemoryNotFoundError(f"Memory not found: {memory_id}")

        updated = self.get_memory(memory_id)
        if updated is None:
            raise MemoryNotFoundError(f"Memory not found: {memory_id}")
        return updated

    def set_status(self, memory_id: UUID | str, status: MemoryStatus) -> MemoryEntry:
        """Transition a row status."""
        return self.update_memory(memory_id, status=status.value)

    def archive_memory(self, memory_id: UUID | str) -> MemoryEntry:
        """Soft-delete a committed row by marking it archived."""
        return self.set_status(memory_id, MemoryStatus.ARCHIVED)

    def delete_memory(self, memory_id: UUID | str) -> bool:
        """Hard-delete a row. Intended for internal maintenance only."""
        sql = "DELETE FROM memories WHERE id = ?;"
        with self.begin_immediate() as conn:
            result = conn.execute(sql, (str(memory_id),))
        return result.rowcount > 0

    def get_committed_ids_by_namespaces(self, namespaces: list[str]) -> list[UUID]:
        """Return committed IDs filtered by namespaces."""
        if not namespaces:
            return []
        placeholders = ", ".join("?" for _ in namespaces)
        sql = f"""
        SELECT id FROM memories
        WHERE status = ?
          AND namespace IN ({placeholders});
        """
        params = [MemoryStatus.COMMITTED.value, *namespaces]
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [UUID(row["id"]) for row in rows]

    def list_failed_memories(self, *, limit: int = 100, older_than_days: int | None = None) -> list[MemoryEntry]:
        """List failed rows for operator remediation."""
        clauses = ["status = ?"]
        params: list[Any] = [MemoryStatus.FAILED.value]
        if older_than_days is not None:
            cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
            clauses.append("updated_at <= ?")
            params.append(cutoff.isoformat())
        where = " AND ".join(clauses)
        sql = f"""
        SELECT * FROM memories
        WHERE {where}
        ORDER BY updated_at ASC
        LIMIT ?;
        """
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def list_ids_by_statuses(self, statuses: list[MemoryStatus]) -> list[UUID]:
        """Return IDs matching one or more statuses."""
        if not statuses:
            return []
        placeholders = ", ".join("?" for _ in statuses)
        sql = f"SELECT id FROM memories WHERE status IN ({placeholders});"
        with self._connect() as conn:
            rows = conn.execute(sql, [status.value for status in statuses]).fetchall()
        return [UUID(row["id"]) for row in rows]

    def stats_committed(self, namespaces: list[str] | None = None) -> MemoryStats:
        """Compute committed-only stats for normal read surfaces."""
        where_parts = ["status = ?"]
        params: list[Any] = [MemoryStatus.COMMITTED.value]
        if namespaces:
            placeholders = ", ".join("?" for _ in namespaces)
            where_parts.append(f"namespace IN ({placeholders})")
            params.extend(namespaces)
        where_clause = " AND ".join(where_parts)

        total_sql = f"SELECT COUNT(*) AS total FROM memories WHERE {where_clause};"
        by_type_sql = f"""
        SELECT memory_type, COUNT(*) AS count
        FROM memories
        WHERE {where_clause}
        GROUP BY memory_type;
        """
        by_namespace_sql = f"""
        SELECT namespace, COUNT(*) AS count
        FROM memories
        WHERE {where_clause}
        GROUP BY namespace;
        """
        recent_7d_sql = f"""
        SELECT COUNT(*) AS count
        FROM memories
        WHERE {where_clause} AND created_at >= ?;
        """
        recent_30d_sql = f"""
        SELECT COUNT(*) AS count
        FROM memories
        WHERE {where_clause} AND created_at >= ?;
        """

        now = datetime.now(UTC)
        recent_7d_cutoff = (now - timedelta(days=7)).isoformat()
        recent_30d_cutoff = (now - timedelta(days=30)).isoformat()

        with self._connect() as conn:
            total = int(conn.execute(total_sql, params).fetchone()["total"])
            by_type_rows = conn.execute(by_type_sql, params).fetchall()
            by_namespace_rows = conn.execute(by_namespace_sql, params).fetchall()
            recent_7d = int(conn.execute(recent_7d_sql, [*params, recent_7d_cutoff]).fetchone()["count"])
            recent_30d = int(
                conn.execute(recent_30d_sql, [*params, recent_30d_cutoff]).fetchone()["count"]
            )

        by_type = {row["memory_type"]: int(row["count"]) for row in by_type_rows}
        by_namespace = {row["namespace"]: int(row["count"]) for row in by_namespace_rows}
        return MemoryStats(
            total=total,
            by_type=by_type,
            by_namespace=by_namespace,
            recent_7d=recent_7d,
            recent_30d=recent_30d,
        )

    def _row_to_entry(self, row: sqlite3.Row) -> MemoryEntry:
        data = dict(row)
        return memory_entry_from_db_row(data)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn
