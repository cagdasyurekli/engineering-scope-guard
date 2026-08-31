#!/usr/bin/env python3
"""Validate the repository's canonical current agent handoff."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from engineering_scope_guard.agent_handoff import HandoffValidationError, load_handoff


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--handoff", type=Path, default=Path("experiment/agent_handoff.json")
    )
    args = parser.parse_args()
    root = args.root.resolve()
    handoff = args.handoff if args.handoff.is_absolute() else root / args.handoff
    try:
        value = load_handoff(handoff, root)
    except (HandoffValidationError, OSError) as error:
        print(f"agent_handoff: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": "valid",
                "goal": value["goal"]["name"],
                "current_decision": value["current_decision"]["decision"],
                "next_action": value["next_action"]["kind"],
                "authorization": value["next_action"]["authorization"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
