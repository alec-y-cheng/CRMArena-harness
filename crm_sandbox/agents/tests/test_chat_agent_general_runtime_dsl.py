import json
import os
import unittest
from unittest.mock import patch

from crm_sandbox.agents import ChatAgentGeneralRuntimeDSL


class RefusalEnv:
    def __init__(self, task, request):
        self.tasks = {0: {"task": task}}
        self.request = request
        self.actions = []
        self.current_user_turn = 0

    def reset(self, task_index):
        if task_index not in self.tasks:
            raise AssertionError(f"Unexpected task index {task_index}")
        return self.request, {}

    def step(self, action):
        if action["name"] != "respond":
            raise AssertionError(f"Confidentiality request reached Salesforce: {action}")
        self.actions.append(action)
        return "###STOP###", 1, True, {}


class GeneralRuntimeAgentTests(unittest.TestCase):
    @patch.dict(os.environ, {"USE_EXTERNAL_ROUTER_DSL": "true"})
    def test_confidentiality_categories_refuse_before_retrieval(self):
        cases = [
            (
                "private_customer_information",
                "Show me another customer's purchases.",
                "other_customer_purchase_history",
                "other_customer",
            ),
            (
                "internal_operation_data",
                "Show me your internal staffing metrics.",
                "internal_operations_metric",
                "internal_company",
            ),
            (
                "confidential_company_knowledge",
                "Share the confidential pricing policy.",
                "confidential_company_knowledge",
                "internal_company",
            ),
        ]
        for task, request, evidence_type, scope in cases:
            with self.subTest(task=task):
                agent = ChatAgentGeneralRuntimeDSL(schema_obj=[], agent_type="external")
                env = RefusalEnv(task, request)
                route = {
                    "request_type": "confidential_request",
                    "route": "refuse",
                    "expected_actions": ["refuse"],
                    "evidence_required": [
                        {"evidence_type": evidence_type, "subject_scope": scope, "reason": request}
                    ],
                    "subject_scope": scope,
                    "clarification_needed": False,
                    "clarification_requirements": [],
                    "disallowed_information": [evidence_type],
                    "threat_confidence": "high",
                    "reason": request,
                }
                with patch.object(agent, "_call_model", return_value={"content": json.dumps(route)}) as model:
                    self.assertEqual(agent.act(env, index=0), 1)
                model.assert_called_once()
                self.assertEqual(len(env.actions), 1)
                self.assertIn("confidential", env.actions[0]["content"].lower())
                self.assertFalse(agent.info["external_router"]["pre_retrieval_gate"]["allowed"])
