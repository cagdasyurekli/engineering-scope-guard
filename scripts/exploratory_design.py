#!/usr/bin/env python3
"""Validate the frozen task-free exploratory design."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from engineering_scope_guard.exploratory_design import load_design


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    path = (
        root
        / "experiment/evidence_conditioned_final_scope_review_v0_1_exploratory_design.json"
    )
    design = load_design(path, root)
    print(
        json.dumps(
            {
                "decision": design["decision"],
                "design_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "execution_authorized": design["execution_authorized"],
                "task_count": design["experimental_unit"]["task_count"],
                "task_pool_frozen": design["task_pool_frozen"],
                "total_cells": design["experimental_unit"]["total_cells"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
