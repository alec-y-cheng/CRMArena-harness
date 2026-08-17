import unittest

from ewm.runtime.frame_sanitizer import drop_protocol_constraints


class ChatAgentEWMTests(unittest.TestCase):
    def test_protocol_constraint_sanitizer_preserves_task_constraints(self):
        cleaned = drop_protocol_constraints(
            [
                "Use Salesforce evidence before answering.",
                "Preserve the required ReAct tags: <thought>...</thought> then <execute>...</execute>.",
                "Return only the Id of the knowledge article or None.",
                "Do not solve the task during InstanceFrame compilation.",
                "If multiple results are found, return a comma-separated string.",
            ]
        )

        self.assertEqual(
            cleaned,
            [
                "Use Salesforce evidence before answering.",
                "Return only the Id of the knowledge article or None.",
                "If multiple results are found, return a comma-separated string.",
            ],
        )


if __name__ == "__main__":
    unittest.main()
