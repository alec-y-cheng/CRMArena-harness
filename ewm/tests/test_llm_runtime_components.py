import unittest
import json

from ewm.ir.environment import ReachableInfo
from ewm.ir.frame import InstanceFrame
from ewm.ir.state import Claim, EvidenceItem, ExecutionState
from ewm.mcp.client import MCPToolSchema
from ewm.runtime.llm_components import LLMRuntimeComponents, _compact_state, parse_json_object


class LLMRuntimeComponentTests(unittest.TestCase):
    def test_parse_json_object_ignores_think_and_fences(self):
        parsed = parse_json_object(
            '<think>private scratch</think>\n```json\n{"answer": "ok"}\n```'
        )
        self.assertEqual(parsed, {"answer": "ok"})

    def test_components_parse_frame_decision_claims_and_verifier(self):
        outputs = iter(
            [
                '{"goal":"lookup account","request_summary":"find account","actor":{"kind":"internal_user"},"evidence_requirements":[{"description":"account record"}],"outcome_contract":{"description":"answer"},"response_contract":{"description":"short answer"}}',
                '{"state_updates":{"frame":{"goal":"lookup account name"},"resolved_entities":[{"object":"Account","description":"target account"}]},"decision_type":"backend_action","backend_action":{"name":"soqlQuery","arguments":{"query":"SELECT Id, Name FROM Account LIMIT 1"}},"reason":"need record"}',
                '{"claims":[{"claim_id":"c1","claim_text":"Account name is Acme.","status":"supported","supporting_evidence_ids":["ev_1"],"value":"Acme"}]}',
                '{"valid":true,"reason":"supported"}',
            ]
        )

        def model_call(messages, max_tokens=None):
            return next(outputs)

        components = LLMRuntimeComponents(model_call, max_retries=0)
        frame = components.infer_frame([{"role": "user", "content": "Find account"}], {})
        self.assertEqual(frame.goal, "lookup account")

        state = ExecutionState(frame)
        decision = components.select_decision(
            frame,
            state,
            [ReachableInfo("Account records", "query_object", object_name="Account")],
            [MCPToolSchema("soqlQuery", input_schema={"type": "object"})],
        )
        self.assertEqual(decision.decision_type, "backend_action")
        self.assertEqual(decision.backend_action.name, "soqlQuery")
        self.assertEqual(decision.state_updates["frame"]["goal"], "lookup account name")
        self.assertEqual(decision.state_updates["resolved_entities"][0]["object"], "Account")

        state.add_evidence(EvidenceItem("ev_1", "obs_1", {"Name": "Acme"}))
        claims = components.extract_claims(frame, state)
        self.assertEqual(claims[0].supporting_evidence_ids, ["ev_1"])

        result = components.verify_completion_payload({"candidate_response": "Acme"})
        self.assertTrue(result["valid"])

    def test_decision_can_extract_claims_from_current_evidence(self):
        outputs = iter(
            [
                '{"decision_type":"complete","candidate_outcome":{"answer":"Acme"},"candidate_response":"Acme","claims":[{"claim_id":"c1","claim_text":"Account name is Acme.","status":"supported","supporting_evidence_ids":["ev_1"],"value":"Acme"}],"reason":"supported"}',
            ]
        )

        def model_call(messages, max_tokens=None):
            return next(outputs)

        components = LLMRuntimeComponents(model_call, max_retries=0)
        frame = InstanceFrame(goal="lookup account")
        state = ExecutionState(frame)
        state.add_evidence(EvidenceItem("ev_1", "obs_1", {"Name": "Acme"}))

        decision = components.select_decision(
            frame,
            state,
            [ReachableInfo("Account records", "query_object", object_name="Account")],
            [MCPToolSchema("soqlQuery", input_schema={"type": "object"})],
        )

        self.assertEqual(decision.decision_type, "complete")
        self.assertEqual(decision.claims[0].claim_text, "Account name is Acme.")

    def test_compact_state_uses_one_step_evidence_inbox_and_persistent_claims(self):
        frame = InstanceFrame(goal="answer policy question")
        state = ExecutionState(frame)
        state.add_evidence(
            EvidenceItem(
                "ev_article",
                "obs_1",
                {
                    "Id": "ka001",
                    "Title": "Return Policy",
                    "FAQ_Answer__c": "Important policy sentence. " + ("extra detail " * 400),
                },
                source_tool="find",
                source_object="Knowledge__kav",
                record_id="ka001",
                provenance={"tool": "find", "arguments": {"search": "return policy"}},
            )
        )

        first = _compact_state(state)
        state.add_claim(
            Claim(
                "claim_policy",
                "Important policy sentence.",
                status="supported",
                supporting_evidence_ids=["ev_article"],
            )
        )
        second = _compact_state(state)

        self.assertEqual(len(first["collected"]["new_evidence_items"]), 1)
        self.assertEqual(
            first["collected"]["new_evidence_items"][0]["content_header"]["Title"],
            "Return Policy",
        )
        self.assertTrue(first["collected"]["new_evidence_items"][0]["content_available"])
        self.assertIn("FAQ_Answer__c", first["collected"]["new_evidence_items"][0]["content"])
        self.assertEqual(first["collected"]["evidence_inventory"][0]["evidence_id"], "ev_article")
        self.assertNotIn("FAQ_Answer__c", first["collected"]["evidence_inventory"][0]["content_header"])
        self.assertEqual(second["collected"]["new_evidence_items"], [])
        self.assertEqual(second["derived"]["claims"][0]["claim_id"], "claim_policy")
        self.assertTrue(second["collected"]["evidence_inventory"][0]["claimed"])

    def test_decision_marks_visible_evidence_items_as_presented(self):
        seen_item_counts = []
        seen_modes = []
        outputs = iter(
            [
                '{"decision_type":"frontend_action","frontend_message":"first","reason":"saw evidence"}',
                '{"decision_type":"frontend_action","frontend_message":"second","reason":"no repeated evidence"}',
            ]
        )

        def model_call(messages, max_tokens=None):
            prompt = json.loads(messages[-1]["content"])
            items = prompt["execution_state"]["collected"]["new_evidence_items"]
            inbox = prompt["execution_state"]["collected"]["new_evidence_inbox"]
            seen_item_counts.append(len(items))
            seen_modes.append(inbox["mode"])
            return next(outputs)

        components = LLMRuntimeComponents(model_call, max_retries=0)
        frame = InstanceFrame(goal="answer policy question")
        state = ExecutionState(frame)
        for index in range(20):
            state.add_evidence(
                EvidenceItem(
                    "ev_{}".format(index),
                    "obs_1",
                    {"Title": "Policy {}".format(index), "FAQ_Answer__c": "Answer text {}".format(index)},
                )
            )

        for _ in range(2):
            components.select_decision(
                frame,
                state,
                [ReachableInfo("Knowledge records", "query_object", object_name="Knowledge__kav")],
                [MCPToolSchema("find", input_schema={"type": "object"})],
            )

        self.assertEqual(seen_item_counts, [20, 0])
        self.assertEqual(seen_modes, ["headers_only_due_context_budget", "readable_content"])
        self.assertEqual(len(state.metrics["presented_evidence_item_ids"]), 20)

    def test_summaries_are_one_step_model_context(self):
        seen_summaries = []
        outputs = iter(
            [
                '{"decision_type":"frontend_action","frontend_message":"first","reason":"saw summary"}',
                '{"decision_type":"frontend_action","frontend_message":"second","reason":"summary consumed"}',
            ]
        )

        def model_call(messages, max_tokens=None):
            prompt = json.loads(messages[-1]["content"])
            seen_summaries.append(prompt["execution_state"]["derived"]["summaries"])
            return next(outputs)

        components = LLMRuntimeComponents(model_call, max_retries=0)
        frame = InstanceFrame(goal="answer policy question")
        state = ExecutionState(frame)
        state.derived["summaries"].append({"description": "temporary orientation"})

        for _ in range(2):
            components.select_decision(
                frame,
                state,
                [ReachableInfo("Knowledge records", "query_object", object_name="Knowledge__kav")],
                [MCPToolSchema("find", input_schema={"type": "object"})],
            )

        self.assertEqual(seen_summaries[0][0]["description"], "temporary orientation")
        self.assertEqual(seen_summaries[1], [])
        self.assertEqual(state.metrics["presented_summary_count"], 1)

    def test_large_evidence_batch_is_headers_only(self):
        state = ExecutionState(
            InstanceFrame(
                goal="Explain why running shoes should be replaced every 300-500 miles",
                request_summary="running shoe replacement mileage",
            )
        )
        for index in range(13):
            state.add_evidence(
                EvidenceItem(
                    "ev_{}".format(index),
                    "obs_1",
                    {
                        "Title": "Running Shoe Replacement Guide {}".format(index),
                        "FAQ_Answer__c": "Replace running shoes every 300-500 miles to ensure support.",
                    },
                )
            )

        compact = _compact_state(state)
        first = compact["collected"]["new_evidence_items"][0]

        self.assertEqual(compact["collected"]["new_evidence_inbox"]["mode"], "headers_only_due_context_budget")
        self.assertEqual(len(compact["collected"]["new_evidence_items"]), 13)
        self.assertFalse(first["content_available"])
        self.assertNotIn("content", first)
        self.assertIn("Title", first["content_header"])


if __name__ == "__main__":
    unittest.main()
