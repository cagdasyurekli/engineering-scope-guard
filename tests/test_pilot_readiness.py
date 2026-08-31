import copy
import unittest
from unittest.mock import patch

from scripts.pilot_readiness import PilotReadinessError, _readiness, audit_readiness


class PilotReadinessTests(unittest.TestCase):
    def test_current_readiness_record_is_bounded_no_go(self):
        result = audit_readiness()

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["conclusion"], "NO-GO")
        self.assertFalse(result["pilot_authorized"])
        self.assertEqual(result["arms"], ["baseline", "short"])
        self.assertEqual(result["confirmed_distinct_eligible_tasks"], 0)
        self.assertEqual(result["minimum_required_opaque_inventory"], 24)
        self.assertEqual(result["planned_agent_runs_if_gates_pass"], 48)
        self.assertEqual(result["total_agent_run_ceiling_if_gates_pass"], 56)

    def test_audit_rejects_silent_pilot_authorization(self):
        value = copy.deepcopy(_readiness())
        value["pilot_authorized"] = True

        with patch("scripts.pilot_readiness._readiness", return_value=value):
            with self.assertRaisesRegex(PilotReadinessError, "conclusion is invalid"):
                audit_readiness()

    def test_audit_rejects_invented_task_supply(self):
        value = copy.deepcopy(_readiness())
        value["task_supply"]["confirmed_distinct_eligible_tasks"] = 12

        with patch("scripts.pilot_readiness._readiness", return_value=value):
            with self.assertRaisesRegex(PilotReadinessError, "task-supply NO-GO facts"):
                audit_readiness()

    def test_audit_rejects_budget_that_treats_repetitions_as_extra_tasks(self):
        value = copy.deepcopy(_readiness())
        value["task_supply"]["minimum_required_distinct_pilot_tasks"] = 24

        with patch("scripts.pilot_readiness._readiness", return_value=value):
            with self.assertRaisesRegex(PilotReadinessError, "inventory arithmetic"):
                audit_readiness()


if __name__ == "__main__":
    unittest.main()
