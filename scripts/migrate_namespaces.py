#!/usr/bin/env python3
"""One-time migration: re-tag alias namespaces to canonical names.

Updates both SQLite (source of truth) and Chroma (vector index).
Recomputes idempotency keys since they include the namespace.

Usage:
    python scripts/migrate_namespaces.py              # dry-run (default)
    python scripts/migrate_namespaces.py --execute    # apply changes
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import yaml


def load_alias_map(config_path: Path) -> dict[str, str]:
    """Build {alias: canonical} map from the namespace registry in config."""
    with open(config_path) as f:
        config = yaml.safe_load(f)

    namespaces = config.get("namespaces", {})
    canonical_entries = namespaces.get("canonical", {})

    alias_map: dict[str, str] = {}
    for canonical_name, entry in canonical_entries.items():
        for alias in entry.get("aliases", []):
            alias_map[alias] = canonical_name
    return alias_map


def canonical_content_hash(content: str) -> str:
    """Reproduce the content hash from consolidation.py."""
    import hashlib

    normalized = " ".join(content.split()).strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def build_idempotency_key(namespace: str, content: str) -> str:
    return f"{namespace}:{canonical_content_hash(content)}"


def migrate_sqlite(
    db_path: Path,
    alias_map: dict[str, str],
    *,
    dry_run: bool = True,
) -> dict[str, int]:
    """Migrate memories, sessions, and episodes from alias to canonical namespaces."""
    stats = {"memories_migrated": 0, "memories_archived_dup": 0, "sessions_migrated": 0, "episodes_migrated": 0}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")

    # Gather distinct alias namespaces actually present in the DB
    present_aliases = set()
    for table in ("memories", "sessions", "episodes"):
        rows = conn.execute(f"SELECT DISTINCT namespace FROM {table}").fetchall()
        for row in rows:
            ns = row["namespace"]
            if ns in alias_map:
                present_aliases.add(ns)

    if not present_aliases:
        print("No alias namespaces found in database. Nothing to migrate.")
        conn.close()
        return stats

    print(f"\nAlias namespaces found in DB: {sorted(present_aliases)}")
    for alias in sorted(present_aliases):
        canonical = alias_map[alias]
        print(f"  {alias} -> {canonical}")

    if dry_run:
        # Report what would change
        for alias in sorted(present_aliases):
            canonical = alias_map[alias]
            mem_count = conn.execute(
                "SELECT COUNT(*) AS c FROM memories WHERE namespace = ? AND status IN ('staged', 'committed')",
                (alias,),
            ).fetchone()["c"]
            sess_count = conn.execute(
                "SELECT COUNT(*) AS c FROM sessions WHERE namespace = ?", (alias,)
            ).fetchone()["c"]
            ep_count = conn.execute(
                "SELECT COUNT(*) AS c FROM episodes WHERE namespace = ?", (alias,)
            ).fetchone()["c"]
            print(f"\n  {alias} -> {canonical}:")
            print(f"    memories: {mem_count}")
            print(f"    sessions: {sess_count}")
            print(f"    episodes: {ep_count}")
        conn.close()
        return stats

    # Execute migration
    for alias in sorted(present_aliases):
        canonical = alias_map[alias]
        print(f"\nMigrating {alias} -> {canonical}...")

        # Memories: recompute idempotency keys, handle duplicates
        rows = conn.execute(
            "SELECT id, content, namespace, idempotency_key FROM memories WHERE namespace = ? AND status IN ('staged', 'committed')",
            (alias,),
        ).fetchall()

        for row in rows:
            new_key = build_idempotency_key(canonical, row["content"])
            # Check if canonical namespace already has this content
            existing = conn.execute(
                "SELECT id FROM memories WHERE idempotency_key = ? AND status IN ('staged', 'committed') AND id != ?",
                (new_key, row["id"]),
            ).fetchone()

            if existing:
                # Duplicate — archive the alias copy
                now = datetime.now(UTC).isoformat()
                conn.execute(
                    "UPDATE memories SET status = 'archived', updated_at = ? WHERE id = ?",
                    (now, row["id"]),
                )
                stats["memories_archived_dup"] += 1
                print(f"    Archived duplicate: {row['id']}")
            else:
                now = datetime.now(UTC).isoformat()
                conn.execute(
                    "UPDATE memories SET namespace = ?, idempotency_key = ?, updated_at = ? WHERE id = ?",
                    (canonical, new_key, now, row["id"]),
                )
                stats["memories_migrated"] += 1

        # Also migrate archived/failed memories (no idempotency concern)
        conn.execute(
            "UPDATE memories SET namespace = ? WHERE namespace = ? AND status IN ('archived', 'failed')",
            (canonical, alias),
        )

        # Sessions
        result = conn.execute("UPDATE sessions SET namespace = ? WHERE namespace = ?", (canonical, alias))
        stats["sessions_migrated"] += result.rowcount

        # Episodes
        result = conn.execute("UPDATE episodes SET namespace = ? WHERE namespace = ?", (canonical, alias))
        stats["episodes_migrated"] += result.rowcount

    conn.commit()
    conn.close()
    return stats


def migrate_chroma(
    chroma_dir: Path,
    alias_map: dict[str, str],
    *,
    dry_run: bool = True,
) -> int:
    """Update namespace metadata in Chroma for migrated memories."""
    try:
        import chromadb
    except ImportError:
        print("chromadb not installed, skipping Chroma migration")
        return 0

    client = chromadb.PersistentClient(path=str(chroma_dir))
    try:
        collection = client.get_collection("memories")
    except Exception:
        print("Chroma collection 'memories' not found, skipping")
        return 0

    updated = 0
    # Get all entries and check which need namespace updates
    # Process in batches to avoid memory issues
    all_ids = collection.get(include=["metadatas"])

    if not all_ids["ids"]:
        print("No entries in Chroma collection")
        return 0

    ids_to_update: list[str] = []
    new_metadatas: list[dict] = []

    for i, entry_id in enumerate(all_ids["ids"]):
        metadata = all_ids["metadatas"][i] if all_ids["metadatas"] else {}
        ns = metadata.get("namespace", "")
        if ns in alias_map:
            new_meta = dict(metadata)
            new_meta["namespace"] = alias_map[ns]
            ids_to_update.append(entry_id)
            new_metadatas.append(new_meta)

    if not ids_to_update:
        print("No Chroma entries need namespace updates")
        return 0

    print(f"\nChroma: {len(ids_to_update)} entries to update")

    if dry_run:
        return len(ids_to_update)

    # Batch update
    batch_size = 100
    for start in range(0, len(ids_to_update), batch_size):
        end = min(start + batch_size, len(ids_to_update))
        collection.update(
            ids=ids_to_update[start:end],
            metadatas=new_metadatas[start:end],
        )
        updated += end - start

    print(f"  Updated {updated} Chroma entries")
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate alias namespaces to canonical names")
    parser.add_argument("--execute", action="store_true", help="Actually apply changes (default is dry-run)")
    parser.add_argument("--config", default="config/memory_config.yaml", help="Path to config YAML")
    args = parser.parse_args()

    dry_run = not args.execute
    config_path = Path(args.config)

    if not config_path.exists():
        print(f"Config not found: {config_path}")
        return

    alias_map = load_alias_map(config_path)
    if not alias_map:
        print("No aliases defined in config. Nothing to migrate.")
        return

    print(f"Alias map ({len(alias_map)} entries):")
    for alias, canonical in sorted(alias_map.items()):
        print(f"  {alias} -> {canonical}")

    # Load paths from config
    with open(config_path) as f:
        config = yaml.safe_load(f)
    db_path = Path(config.get("paths", {}).get("sqlite_db", "data/memory.db"))
    chroma_dir = Path(config.get("paths", {}).get("chroma_dir", "data/chroma"))

    if not db_path.exists():
        print(f"\nSQLite DB not found: {db_path}")
        return

    if dry_run:
        print("\n=== DRY RUN (use --execute to apply) ===")
    else:
        # Backup SQLite before mutation
        backup_path = db_path.with_suffix(f".db.backup-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(db_path, backup_path)
        print(f"\nBacked up SQLite to: {backup_path}")

    sqlite_stats = migrate_sqlite(db_path, alias_map, dry_run=dry_run)
    chroma_count = migrate_chroma(chroma_dir, alias_map, dry_run=dry_run)

    print("\n=== Summary ===")
    print(f"  Memories migrated: {sqlite_stats['memories_migrated']}")
    print(f"  Memories archived (duplicate): {sqlite_stats['memories_archived_dup']}")
    print(f"  Sessions migrated: {sqlite_stats['sessions_migrated']}")
    print(f"  Episodes migrated: {sqlite_stats['episodes_migrated']}")
    print(f"  Chroma entries updated: {chroma_count}")

    if dry_run:
        print("\nNo changes made. Run with --execute to apply.")


if __name__ == "__main__":
    main()
