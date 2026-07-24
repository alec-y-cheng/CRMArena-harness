import unittest

from crm_sandbox.agents.working_memory import WorkingMemory


class WorkingMemoryTest(unittest.TestCase):
    def test_reset_renders_compact_task_state(self):
        memory = WorkingMemory(max_chars=500)
        memory.reset(
            "Does this lead satisfy the BANT qualification criteria?",
            {"task_family": "lead_qualification"},
        )

        rendered = memory.render()

        self.assertIn("# Current task state", rendered)
        self.assertIn("Task family: lead_qualification", rendered)
        self.assertIn("Goal: Does this lead satisfy", rendered)
        self.assertIn("Budget", rendered)
        self.assertIn("Authority", rendered)

    def test_failed_queries_are_deterministic_and_deduplicated(self):
        memory = WorkingMemory(max_chars=500)
        query = "SELECT Missing__c FROM Lead"
        memory.reset("Find lead status.", {"task_family": "lead_qualification"})

        memory.record_verifier_failure({"name": "execute", "content": query}, "UNKNOWN_FIELD")
        memory.record_verifier_failure({"name": "execute", "content": query}, "UNKNOWN_FIELD")

        state = memory.as_dict()
        self.assertEqual(state["failed_queries"], [query])
        self.assertIn("UNKNOWN_FIELD", memory.render())

    def test_env_query_error_records_failed_query(self):
        memory = WorkingMemory(max_chars=500)
        query = "SELECT Id FROM Bogus__c"
        memory.reset("Find a record.", {"task_family": "unknown"})

        memory.record_env_step(
            {"name": "execute", "content": query},
            "INVALID_TYPE",
            {"end_reason": {"message": "SOQL/SOSL query error"}},
        )

        self.assertEqual(memory.as_dict()["failed_queries"], [query])
        self.assertIn("do not repeat", memory.render())

    def test_render_respects_max_chars(self):
        memory = WorkingMemory(max_chars=320)
        memory.reset("x" * 1000, {"task_family": "case_routing"})
        for index in range(10):
            memory.record_env_step({"name": "execute", "content": f"SELECT Id FROM Case LIMIT {index}"}, [{"Id": str(index)}], {})

        self.assertLessEqual(len(memory.render()), 320)


if __name__ == "__main__":
    unittest.main()
