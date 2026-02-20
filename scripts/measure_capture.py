#!/usr/bin/env python3
"""Phase 4 measurement — capture rate and signal quality.

Reads all session_end episodes and classifies each logical session:
  - handoff:   /handoff was called (end_session with handoff=True metadata)
  - hook:      SessionEnd hook fired without prior /handoff
  - hook_fail: hook fired but transcript extraction failed

Outputs a report to stdout (plain text, JSON with --json).

Usage:
    python3 scripts/measure_capture.py
    python3 scripts/measure_capture.py --json
    python3 scripts/measure_capture.py --days 14
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

_MEMORY_PROJECT = Path(__file__).resolve().parent.parent
_SRC_DIR = _MEMORY_PROJECT / "src"


def _load_storage():
    if str(_SRC_DIR) not in sys.path:
        sys.path.insert(0, str(_SRC_DIR))
    from memory_core.config import load_config
    from memory_core.storage.db import SQLiteMemoryDB
    from memory_core.storage.episode_storage import EpisodeStorage

    config = load_config(_MEMORY_PROJECT / "config" / "memory_config.yaml")
    db = SQLiteMemoryDB(config.paths.sqlite_db)
    db.initialize()
    return EpisodeStorage(db)


def _classify_episode(ep: dict) -> str:
    """Classify a single session_end episode."""
    meta = ep.get("metadata") or {}
    source = meta.get("source", "")

    # /handoff path: end_session called directly (no source=sessionend_hook)
    if source != "sessionend_hook":
        return "handoff"

    result = meta.get("extraction_result", "")
    if result == "handoff_already_called":
        return "hook_after_handoff"
    if result == "text_extracted":
        return "hook"
    if result == "parse_error" or result == "no_content":
        return "hook_fail"
    return "hook"


def _assess_quality(ep: dict) -> dict:
    """Return simple quality metrics for an episode."""
    content = ep.get("content", "")
    meta = ep.get("metadata") or {}

    has_next_steps = bool(meta.get("next_steps"))
    has_work_done = bool(meta.get("work_done"))
    has_commits = bool(meta.get("commits"))
    content_len = len(content)

    if has_next_steps and has_work_done:
        quality = "high"
    elif content_len > 100:
        quality = "medium"
    else:
        quality = "low"

    return {
        "quality": quality,
        "content_len": content_len,
        "has_next_steps": has_next_steps,
        "has_work_done": has_work_done,
        "has_commits": has_commits,
    }


def run(days: int = 14) -> dict:
    storage = _load_storage()

    since = (datetime.now(UTC) - timedelta(days=days)).isoformat() if days else None
    request = {"event_type": "session_end", "limit": 500}
    if since:
        request["since"] = since
    raw_episodes = storage.get_episodes(request)
    episodes = [e.model_dump() if hasattr(e, "model_dump") else dict(e) for e in raw_episodes]

    # Group episodes by logical session
    # A "logical session" = one user session.
    # hook_after_handoff episodes belong to the same session as the handoff.
    # We track session_ids and their classifications.
    sessions: dict[str, list[dict]] = defaultdict(list)
    for ep in episodes:
        sid = ep.get("session_id", "unknown")
        sessions[sid].append(ep)

    results = []
    for sid, eps in sessions.items():
        classifications = [_classify_episode(e) for e in eps]

        # Determine session capture type (priority: handoff > hook > fail)
        if "handoff" in classifications:
            capture_type = "handoff"
        elif "hook" in classifications:
            capture_type = "hook"
        elif "hook_after_handoff" in classifications:
            capture_type = "hook_after_handoff"  # shouldn't be standalone
        else:
            capture_type = "hook_fail"

        # Quality = max quality across episodes in session
        qualities = [_assess_quality(e) for e in eps]
        quality_rank = {"high": 3, "medium": 2, "low": 1}
        best_quality = max(qualities, key=lambda q: quality_rank[q["quality"]])

        # Earliest timestamp
        timestamps = [e.get("timestamp", "") for e in eps if e.get("timestamp")]
        ts = min(timestamps) if timestamps else None

        results.append({
            "session_id": sid,
            "timestamp": ts,
            "capture_type": capture_type,
            "episode_count": len(eps),
            "quality": best_quality,
        })

    # Aggregate metrics
    total = len(results)
    by_type: dict[str, int] = defaultdict(int)
    by_quality: dict[str, int] = defaultdict(int)
    for r in results:
        by_type[r["capture_type"]] += 1
        by_quality[r["quality"]["quality"]] += 1

    handoff_count = by_type.get("handoff", 0)
    hook_count = by_type.get("hook", 0)
    fail_count = by_type.get("hook_fail", 0)

    handoff_rate = handoff_count / total if total else 0
    capture_rate = (handoff_count + hook_count) / total if total else 0

    return {
        "period_days": days,
        "total_sessions": total,
        "by_type": dict(by_type),
        "by_quality": dict(by_quality),
        "handoff_rate": round(handoff_rate, 3),
        "capture_rate": round(capture_rate, 3),
        "sessions": sorted(results, key=lambda r: r.get("timestamp") or ""),
    }


def _print_report(data: dict) -> None:
    print(f"\n=== Memory Capture Rate Report (last {data['period_days']} days) ===")
    print(f"Total sessions tracked: {data['total_sessions']}")
    print()

    print("Capture method breakdown:")
    for ctype, count in sorted(data["by_type"].items(), key=lambda x: -x[1]):
        pct = count / data["total_sessions"] * 100 if data["total_sessions"] else 0
        print(f"  {ctype:<22} {count:3d}  ({pct:.0f}%)")

    print()
    print("Signal quality:")
    for q, count in sorted(data["by_quality"].items(), key=lambda x: -x[1]):
        pct = count / data["total_sessions"] * 100 if data["total_sessions"] else 0
        print(f"  {q:<10} {count:3d}  ({pct:.0f}%)")

    print()
    print(f"Handoff rate (user-initiated):  {data['handoff_rate']:.1%}")
    print(f"Overall capture rate:           {data['capture_rate']:.1%}")

    target = 0.5
    status = "✓ on track" if data["handoff_rate"] >= target else "✗ below target (50%)"
    print(f"Target (handoff ≥50%):          {status}")

    print()
    print("Recent sessions:")
    for r in data["sessions"][-10:]:
        ts = r["timestamp"][:10] if r["timestamp"] else "unknown"
        q = r["quality"]["quality"]
        print(f"  {ts}  {r['capture_type']:<22}  quality={q}  sid={r['session_id'][:30]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure memory capture rate")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--days", type=int, default=14, help="Lookback window (default 14)")
    args = parser.parse_args()

    try:
        data = run(days=args.days)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        _print_report(data)

    return 0


if __name__ == "__main__":
    sys.exit(main())
