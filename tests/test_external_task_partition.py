from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "external_task_partition.py"
SPEC = importlib.util.spec_from_file_location("external_task_partition", SCRIPT)
assert SPEC and SPEC.loader
partition = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(partition)


def _record(index: int, language: str, repo: str | None = None) -> dict[str, object]:
    return {
        "instance_id": f"owner__repo-{language}-{index}",
        "repo": repo or f"owner/{language}-{index}",
        "created_at": "2026-03-01T00:00:00Z",
        "docker_image": f"example.invalid/{language}-{index}",
        "FAIL_TO_PASS": ["target"],
        "PASS_TO_PASS": ["regression"],
        "rebuild_cmds": ["build"],
        "test_cmds": ["test"],
        "language": language,
    }


def _write_inputs(tmp_path: Path) -> tuple[Path, Path]:
    records: list[dict[str, object]] = []
    for language in partition.PILOT_QUOTAS:
        for index in range(100):
            records.append(_record(index, language))
    records = records[: partition.SOURCE_ROWS]
    while len(records) < partition.SOURCE_ROWS:
        language = next(iter(partition.PILOT_QUOTAS))
        records.append(_record(len(records), language))
    metadata = tmp_path / "metadata.json"
    metadata.write_text(json.dumps(records), encoding="utf-8")
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"tasks": [{"task_id": "dev-only"}]}), encoding="utf-8")
    return metadata, registry


class ExternalTaskPartitionTests(unittest.TestCase):
    def test_partition_is_deterministic_disjoint_and_hides_reserve_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            metadata, registry = _write_inputs(Path(directory))
            with patch.object(partition, "EXPECTED_ELIGIBLE", partition.SOURCE_ROWS):
                first = partition.build_partition(metadata, registry)
                second = partition.build_partition(metadata, registry)

        self.assertEqual(first, second)
        self.assertEqual(
            first["partition"]["pilot_count"], sum(partition.PILOT_QUOTAS.values())
        )
        self.assertIs(first["partition"]["pilot_and_reserve_task_ids_disjoint"], True)
        self.assertIs(first["partition"]["pilot_and_reserve_repositories_disjoint"], True)
        self.assertIs(first["partition"]["reserve_ids_or_bodies_emitted"], False)
        self.assertNotIn("reserve_ids", first["partition"])
        self.assertEqual(first["development_exclusions"]["overlap_with_source"], 0)
        self.assertIs(
            first["partition"]["smoke_candidate"]["selection_uses_task_bodies_or_outcomes"],
            False,
        )

    def test_partition_rejects_task_body_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            metadata, registry = _write_inputs(Path(directory))
            records = json.loads(metadata.read_text(encoding="utf-8"))
            records[0]["problem_statement"] = "must not enter the partition workflow"
            metadata.write_text(json.dumps(records), encoding="utf-8")

            with self.assertRaisesRegex(
                partition.PartitionError, "only the frozen metadata projection"
            ):
                partition.build_partition(metadata, registry)

    def test_partition_rejects_source_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            metadata, registry = _write_inputs(Path(directory))
            with patch.object(partition, "EXPECTED_ELIGIBLE", partition.SOURCE_ROWS - 1):
                with self.assertRaisesRegex(partition.PartitionError, "frozen source expected"):
                    partition.build_partition(metadata, registry)


if __name__ == "__main__":
    unittest.main()
