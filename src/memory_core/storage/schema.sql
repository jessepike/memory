PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    memory_type TEXT NOT NULL,
    namespace TEXT NOT NULL DEFAULT 'global',
    writer_id TEXT NOT NULL,
    writer_type TEXT NOT NULL,
    source_project TEXT,
    idempotency_key TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0 CHECK(confidence >= 0.0 AND confidence <= 1.0),
    status TEXT NOT NULL DEFAULT 'staged',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (memory_type IN ('observation', 'preference', 'decision', 'progress', 'relationship')),
    CHECK (writer_type IN ('agent', 'user', 'system')),
    CHECK (status IN ('staged', 'committed', 'failed', 'archived'))
);

CREATE INDEX IF NOT EXISTS idx_memories_namespace ON memories(namespace, status);
CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(memory_type);
CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memories_status ON memories(status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_idempotency_active
ON memories(idempotency_key) WHERE status IN ('staged', 'committed');
