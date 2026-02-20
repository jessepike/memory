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

-- Session lifecycle tracking (chain head, sequence counter)
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    start_ts TEXT NOT NULL,
    end_ts TEXT,
    creator TEXT NOT NULL,
    client TEXT,
    project TEXT,
    namespace TEXT NOT NULL DEFAULT 'global',
    finalized INTEGER NOT NULL DEFAULT 0,
    last_sequence INTEGER NOT NULL DEFAULT 0,
    chain_head TEXT,
    metadata TEXT,
    schema_version INTEGER NOT NULL DEFAULT 1
);

-- Episodic event log (append-only, hash-chained per session)
CREATE TABLE IF NOT EXISTS episodes (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(session_id),
    sequence INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info',
    agent_id TEXT NOT NULL,
    client TEXT,
    project TEXT,
    namespace TEXT NOT NULL DEFAULT 'global',
    content TEXT NOT NULL,
    metadata TEXT,
    source_ref TEXT,
    event_hash TEXT NOT NULL,
    previous_hash TEXT,
    schema_version INTEGER NOT NULL DEFAULT 1,
    UNIQUE(session_id, sequence)
);

CREATE INDEX IF NOT EXISTS idx_episodes_session ON episodes(session_id, sequence);
CREATE INDEX IF NOT EXISTS idx_episodes_timestamp ON episodes(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_episodes_project ON episodes(project, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_episodes_type ON episodes(event_type);
CREATE INDEX IF NOT EXISTS idx_episodes_agent ON episodes(agent_id);
CREATE INDEX IF NOT EXISTS idx_episodes_namespace ON episodes(namespace);
