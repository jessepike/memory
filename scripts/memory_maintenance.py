#!/usr/bin/env python3
"""Memory maintenance — staleness sweep, duplicate detection, reconcile.

Designed to run as a scheduled Krypton job (weekly recommended).

Usage:
    python scripts/memory_maintenance.py                # report only (default)
    python scripts/memory_maintenance.py --auto-archive  # archive stale + duplicates
    python scripts/memory_maintenance.py --json          # machine-readable output
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml


def load_config(config_path: Path) -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def get_storage(config_path: Path):
    """Initialize MemoryStorage from config."""
    src_dir = Path(__file__).resolve().parent.parent / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    from memory_core.config import load_config as load_app_config
    from memory_core.storage.api import MemoryStorage

    config = load_app_config(str(config_path))
    storage = MemoryStorage(config)
    storage.initialize()
    return storage


def sweep_stale(storage, *, auto_archive: bool = False) -> dict:
    """Find memories past their type's shelf life."""
    staleness_cfg = storage.config.staleness
    from memory_core.models import MemoryStatus

    committed = storage.db.list_memories(
        statuses=[MemoryStatus.COMMITTED],
        limit=100_000,
    )

    now = datetime.now(UTC)
    stale_entries = []

    for row in committed:
        max_age = staleness_cfg.max_age_days(row.memory_type.value)
        if max_age is None:
            continue
        age_days = (now - row.created_at).days
        if age_days > max_age:
            stale_entries.append({
                "id": str(row.id),
                "memory_type": row.memory_type.value,
                "namespace": row.namespace,
                "age_days": age_days,
                "max_age": max_age,
                "content_preview": row.content[:120],
            })

    archived_ids = []
    if auto_archive and stale_entries:
        for entry in stale_entries:
            try:
                storage.archive_memory(
                    entry["id"],
                    caller_id="maintenance",
                    namespace=entry["namespace"],
                )
                archived_ids.append(entry["id"])
            except Exception as exc:
                entry["archive_error"] = str(exc)

    return {
        "stale_count": len(stale_entries),
        "archived_count": len(archived_ids),
        "entries": stale_entries,
    }


def sweep_duplicates(storage, *, auto_archive: bool = False) -> dict:
    """Find and optionally archive duplicate clusters."""
    candidates = storage.review_candidates(caller_id="maintenance", limit=30)

    duplicate_clusters = []
    archived_ids = []

    for candidate in candidates:
        if candidate.reason != "high_similarity":
            continue
        if not candidate.similar_entries:
            continue

        cluster = {
            "keep_id": None,
            "archive_ids": [],
            "content_preview": candidate.content[:120],
            "similarity": max(e["similarity"] for e in candidate.similar_entries),
        }

        # Determine which to keep (the candidate) and which to archive (similar entries)
        # review_candidates returns the entry + its similar matches
        # We keep the candidate entry, archive similar ones that are older
        cluster["keep_id"] = str(candidate.id)
        for similar in candidate.similar_entries:
            cluster["archive_ids"].append(str(similar["id"]))

        duplicate_clusters.append(cluster)

    # Deduplicate archive targets (same ID might appear in multiple clusters)
    seen_archive = set()
    unique_archive_ids = []
    for cluster in duplicate_clusters:
        for aid in cluster["archive_ids"]:
            if aid not in seen_archive:
                seen_archive.add(aid)
                unique_archive_ids.append(aid)

    if auto_archive:
        for aid in unique_archive_ids:
            try:
                # Need to get the memory's namespace for the archive call
                row = storage.db.get_memory(aid)
                if row and row.status.value == "committed":
                    storage.archive_memory(
                        aid,
                        caller_id="maintenance",
                        namespace=row.namespace,
                    )
                    archived_ids.append(aid)
            except Exception:
                pass

    return {
        "cluster_count": len(duplicate_clusters),
        "archive_targets": len(unique_archive_ids),
        "archived_count": len(archived_ids),
        "clusters": duplicate_clusters,
    }


def check_unscoped(storage) -> dict:
    """Count memories in _unscoped namespace."""
    count = storage.db.count_by_namespace("_unscoped")
    return {"unscoped_count": count}


def run_reconcile(storage) -> dict:
    """Run dual-store reconciliation."""
    return storage.reconcile_dual_store()


def get_stats_summary(storage) -> dict:
    """Get current stats."""
    from memory_core.models import MemoryStatus

    committed = storage.db.list_memories(statuses=[MemoryStatus.COMMITTED], limit=100_000)
    by_type = {}
    by_namespace = {}
    for row in committed:
        t = row.memory_type.value
        by_type[t] = by_type.get(t, 0) + 1
        ns = row.namespace
        by_namespace[ns] = by_namespace.get(ns, 0) + 1

    return {
        "total_committed": len(committed),
        "by_type": by_type,
        "by_namespace": by_namespace,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Memory maintenance — staleness, duplicates, reconcile")
    parser.add_argument("--auto-archive", action="store_true", help="Auto-archive stale and duplicate memories")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--config", default="config/memory_config.yaml", help="Config path")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Config not found: {config_path}", file=sys.stderr)
        return 1

    storage = get_storage(config_path)

    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "auto_archive": args.auto_archive,
    }

    # 1. Stats before
    report["stats"] = get_stats_summary(storage)

    # 2. Staleness sweep
    report["staleness"] = sweep_stale(storage, auto_archive=args.auto_archive)

    # 3. Duplicate detection
    report["duplicates"] = sweep_duplicates(storage, auto_archive=args.auto_archive)

    # 4. Unscoped check
    report["unscoped"] = check_unscoped(storage)

    # 5. Reconcile
    report["reconcile"] = run_reconcile(storage)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"=== Memory Maintenance Report ({report['timestamp'][:10]}) ===\n")

        stats = report["stats"]
        print(f"Total committed: {stats['total_committed']}")
        print(f"By type: {stats['by_type']}")
        print(f"By namespace: {stats['by_namespace']}\n")

        stale = report["staleness"]
        print(f"Stale memories: {stale['stale_count']}")
        if stale["archived_count"]:
            print(f"  Archived: {stale['archived_count']}")
        if stale["entries"] and not args.auto_archive:
            for e in stale["entries"][:10]:
                print(f"  [{e['memory_type']}] {e['age_days']}d old (max {e['max_age']}d): {e['content_preview']}...")
            if len(stale["entries"]) > 10:
                print(f"  ... and {len(stale['entries']) - 10} more")

        dupes = report["duplicates"]
        print(f"\nDuplicate clusters: {dupes['cluster_count']} ({dupes['archive_targets']} archive targets)")
        if dupes["archived_count"]:
            print(f"  Archived: {dupes['archived_count']}")

        unscoped = report["unscoped"]
        print(f"\nUnscoped memories: {unscoped['unscoped_count']}")

        recon = report["reconcile"]
        drift = recon["sqlite_committed_missing_chroma"] + recon["sqlite_archived_present_chroma"] + recon["chroma_orphans"]
        print(f"Reconcile: {'clean' if drift == 0 else f'{drift} issues repaired'}")

        if args.auto_archive:
            total_archived = stale["archived_count"] + dupes["archived_count"]
            print(f"\nTotal archived this run: {total_archived}")
        else:
            actionable = stale["stale_count"] + dupes["archive_targets"]
            if actionable:
                print(f"\nRun with --auto-archive to clean up {actionable} entries")

    return 0


if __name__ == "__main__":
    sys.exit(main())
