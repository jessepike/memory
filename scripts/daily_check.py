#!/usr/bin/env python3
"""Memory daily check — compact summary for SessionStart hook.

Outputs a single status line suitable for session start briefing.
Silent (no output) if no sessions in the lookback window.

Usage:
    python3 scripts/daily_check.py           # last 1 day
    python3 scripts/daily_check.py --days 7  # last 7 days
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_MEMORY_PROJECT = Path(__file__).resolve().parent.parent
_SRC_DIR = _MEMORY_PROJECT / "src"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=1)
    args = parser.parse_args()

    try:
        if str(_SRC_DIR) not in sys.path:
            sys.path.insert(0, str(_SRC_DIR))

        # Import inline to avoid import errors surfacing at session start
        from measure_capture import run  # noqa: PLC0415
        data = run(days=args.days)
    except Exception:
        return 0  # Silent failure — never block session start

    total = data["total_sessions"]
    if total == 0:
        return 0  # Nothing to report

    handoff_rate = data["handoff_rate"]
    capture_rate = data["capture_rate"]
    by_type = data["by_type"]

    handoff = by_type.get("handoff", 0)
    hook = by_type.get("hook", 0)
    fail = by_type.get("hook_fail", 0)

    label = f"last {args.days}d" if args.days != 1 else "yesterday"
    on_track = handoff_rate >= 0.5
    status = "✓" if on_track else "✗ below 50% target"

    parts = [f"memory ({label}): {total} session{'s' if total != 1 else ''}"]
    parts.append(f"handoff={handoff_rate:.0%}")
    if hook:
        parts.append(f"hook={hook}")
    if fail:
        parts.append(f"fail={fail}")
    parts.append(status)

    print(" | ".join(parts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
