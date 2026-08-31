import json
import tempfile
import unittest
from pathlib import Path

from scripts.run_development_pool import audit_registry, summarize_wave, trace_mechanics


class DevelopmentPoolTests(unittest.TestCase):
    def test_registered_task_packets_match_frozen_hashes(self):
        audit = audit_registry()
        self.assertEqual(audit["status"], "pass")
        self.assertEqual(audit["task_count"], 4)

    def test_trace_mechanics_counts_failed_loop_rework_and_reads(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "src.py").write_text("value = 1\n", encoding="utf-8")
            records = [
                {"type": "item.completed", "item": {"type": "command_execution", "command": "/bin/zsh -lc 'pwd && sed -n 1p src.py && rg value src.py'", "exit_code": 0}},
                {"type": "item.completed", "item": {"type": "file_change", "changes": [{"path": str(root / "src.py"), "kind": "update"}]}},
                {"type": "item.completed", "item": {"type": "command_execution", "command": "python -m unittest", "exit_code": 1}},
                {"type": "item.completed", "item": {"type": "file_change", "changes": [{"path": "src.py", "kind": "update"}]}},
            ]
            trace = root / "trace.jsonl"
            trace.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
            result = trace_mechanics(trace, root)
            self.assertEqual(result["read_search_commands"], 2)
            self.assertEqual(result["observed_repository_paths"], ["src.py"])
            self.assertEqual(result["failed_verification_loops"], 1)
            self.assertEqual(result["post_hoc_rework_paths"], ["src.py"])

    def test_summary_preserves_diagnostics_and_unavailable_billing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            derived = root / "cell"
            derived.mkdir()
            record = {
                "execution": {"wall_time_ms": 10, "timed_out": False},
                "turns": {"completed": 1},
                "usage": {"status": "available", "components": {"input_tokens": 5}},
                "billing": {"status": "unavailable"},
                "v0_events": [
                    {"event": "structural_delta", "files": {"counts": {"added": 0, "modified": 1, "deleted": 0}}, "loc": {"added": 2, "deleted": 1}},
                    {"event": "dependency_delta", "added": [], "removed": []},
                ],
            }
            mechanics = {
                "failed_verification_loops": 0, "post_hoc_rework_paths": [],
                "verification_commands": 1, "failed_verification_commands": 0,
                "read_search_commands": 1, "observed_repository_paths": ["src.py"],
            }
            (derived / "record.json").write_text(json.dumps(record), encoding="utf-8")
            (derived / "mechanics.json").write_text(json.dumps(mechanics), encoding="utf-8")
            (root / "ledger.json").write_text(json.dumps({"wave": 1, "runs": [{
                "task_id": "task", "run_id": "r1", "arm": "baseline",
                "result": "completed", "accepted": True,
                "record": "cell/record.json", "mechanics": "cell/mechanics.json",
            }]}), encoding="utf-8")
            result = summarize_wave(root)
            self.assertEqual(result["arms"]["baseline"]["accepted"], 1)
            self.assertEqual(result["arms"]["baseline"]["billing_statuses"], ["unavailable"])
            self.assertEqual(result["arms"]["baseline"]["loc_added"], 2)


if __name__ == "__main__":
    unittest.main()
