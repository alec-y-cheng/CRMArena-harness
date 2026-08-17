import unittest

from ewm.ir.environment import EnvironmentIR, ObjectSchema
from ewm.ir.frame import EvidenceRequirement, InstanceFrame, OutcomeContract, ResponseContract
from ewm.ir.state import Claim, CompletionState, ExecutionState
from ewm.mcp.client import MCPCall, MCPClient, MCPObservation, MCPToolSchema, ValidationResult
from ewm.runtime.action_selector import WorkflowDecision
from ewm.runtime.renderer import render_response
from ewm.runtime.verifier import CompletionVerifierSuite
from ewm.runtime.workflow_driver import WorkflowDriver


class FakeMCPClient(MCPClient):
    def __init__(self):
        self.calls = []

    def list_tools(self):
        return [
            MCPToolSchema(
                "soqlQuery",
                "Run read-only SOQL.",
                {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            )
        ]

    def call(self, call):
        self.calls.append(call)
        return MCPObservation(
            call=call,
            ok=True,
            payload={
                "records": [
                    {
                        "Id": "001xx",
                        "Name": "Acme",
                    }
                ],
                "totalSize": 1,
            },
            raw={
                "ok": True,
                "tool": "soqlQuery",
                "content": {
                    "records": [
                        {
                            "Id": "001xx",
                            "Name": "Acme",
                        }
                    ],
                    "totalSize": 1,
                },
            },
        )


class FailingMCPClient(FakeMCPClient):
    def call(self, call):
        self.calls.append(call)
        return MCPObservation(
            call=call,
            ok=False,
            payload=None,
            error={"message": "Backend rejected this query shape."},
            raw={"ok": False, "error": {"message": "Backend rejected this query shape."}},
        )


class Phase5WorkflowDriverTests(unittest.TestCase):
    def test_driver_executes_backend_action_then_completes(self):
        env_ir = EnvironmentIR(
            objects={"Account": ObjectSchema("Account", fields={"Id": {"type": "id"}, "Name": {"type": "string"}})},
            tool_schemas=[{"name": "soqlQuery"}],
        )
        decisions = [
            WorkflowDecision(
                "backend_action",
                backend_action=MCPCall("soqlQuery", {"query": "SELECT Id, Name FROM Account LIMIT 1"}),
                reason="need account evidence",
            ),
            WorkflowDecision(
                "complete",
                candidate_outcome={"answer": "Acme"},
                candidate_response="Acme",
                state_updates={
                    "frame": {"request_summary": "resolved account lookup"},
                    "resolved_entities": [{"object": "Account", "id": "001xx"}],
                },
                claims=[
                    Claim(
                        "claim_from_decision",
                        "The account name is Acme.",
                        status="supported",
                        value="Acme",
                        supporting_evidence_ids=["ev_obs_soqlQuery_001xx"],
                    )
                ],
                reason="answer is supported by evidence",
            ),
        ]

        def frame_inferer(messages, env_summary):
            return InstanceFrame(
                goal="answer direct account lookup",
                request_summary=messages[-1]["content"],
                evidence_requirements=[EvidenceRequirement("retrieve the account record")],
                outcome_contract=OutcomeContract("answer supported by cited evidence"),
                response_contract=ResponseContract("short factual answer"),
            )

        def selector(frame, state, reachable, tools):
            self.assertTrue(reachable)
            self.assertEqual(tools[0].name, "soqlQuery")
            return decisions.pop(0)

        def claim_extractor(frame, state):
            if not state.collected["evidence"]:
                return []
            return [
                Claim(
                    "claim_1",
                    "The account name is Acme.",
                    status="supported",
                    value="Acme",
                    supporting_evidence_ids=[state.collected["evidence"][0].evidence_id],
                )
            ]

        driver = WorkflowDriver(
            FakeMCPClient(),
            env_ir,
            frame_inferer=frame_inferer,
            decision_selector=selector,
            claim_extractor=claim_extractor,
            max_steps=4,
        )

        state = driver.run([{"role": "user", "content": "What is the account name?"}])

        self.assertTrue(state.completion_state.ready)
        self.assertEqual(driver.render(state), "Acme")
        self.assertEqual(state.metrics["env_calls"], 1)
        self.assertEqual(state.collected["observations"][0].source, "soqlQuery")
        self.assertEqual(state.collected["evidence"][0].source_object, "Account")
        self.assertEqual(state.frame.request_summary, "resolved account lookup")
        self.assertEqual(state.resolved["entities"][0]["object"], "Account")
        self.assertTrue(any(claim.claim_id == "claim_from_decision" for claim in state.derived["claims"]))
        self.assertEqual(state.derived["claims"][0].supporting_evidence_ids, [state.collected["evidence"][0].evidence_id])

    def test_driver_pauses_on_frontend_action(self):
        driver = WorkflowDriver(
            FakeMCPClient(),
            EnvironmentIR(),
            frame_inferer=lambda messages, env_summary: InstanceFrame(goal="clarify target"),
            decision_selector=lambda frame, state, reachable, tools: WorkflowDecision(
                "frontend_action",
                frontend_message="which account",
                reason="target is ambiguous",
            ),
        )

        state = driver.run([{"role": "user", "content": "Look this up"}])

        self.assertFalse(state.completion_state.ready)
        self.assertEqual(state.completion_state.status, "needs_action")
        self.assertEqual(state.completion_state.needed[0]["source"], "user")
        self.assertIn("which account", driver.render(state))

    def test_renderer_does_not_emit_unverified_candidate(self):
        state = ExecutionState(frame=InstanceFrame(goal="answer"))
        state.candidates["response"] = "Unverified answer"

        rendered = render_response(
            state.frame,
            state,
            CompletionState(ready=False, status="needs_verification", reason="not supported"),
        )

        self.assertEqual(rendered, "")

    def test_driver_records_verifier_feedback_for_repair_loop(self):
        def semantic_rejector(frame, state, env_ir):
            return ValidationResult(False, "Candidate does not satisfy the instance constraints.")

        driver = WorkflowDriver(
            FakeMCPClient(),
            EnvironmentIR(),
            frame_inferer=lambda messages, env_summary: InstanceFrame(
                goal="answer account lookup",
                outcome_contract=OutcomeContract("answer", requires_verification=False),
            ),
            decision_selector=lambda frame, state, reachable, tools: WorkflowDecision(
                "complete",
                candidate_outcome={"answer": "Acme"},
                candidate_response="Acme",
                reason="attempt completion",
            ),
            completion_verifier_suite=CompletionVerifierSuite(semantic_verifiers=[semantic_rejector]),
            max_steps=1,
        )

        state = driver.initialize_state([{"role": "user", "content": "What is the account name?"}], {})
        state = driver.step(state)

        self.assertFalse(state.completion_state.ready)
        self.assertEqual(state.completion_state.status, "needs_verification")
        self.assertTrue(state.resolved["unresolved"])
        self.assertEqual(state.resolved["unresolved"][0]["source"], "completion_verifier")
        self.assertIn("Candidate does not satisfy", state.resolved["unresolved"][0]["description"])
        self.assertTrue(state.derived["summaries"])

    def test_driver_rejects_invalid_backend_arguments_before_execution(self):
        client = FakeMCPClient()
        driver = WorkflowDriver(
            client,
            EnvironmentIR(),
            frame_inferer=lambda messages, env_summary: InstanceFrame(goal="query account"),
            decision_selector=lambda frame, state, reachable, tools: WorkflowDecision(
                "backend_action",
                backend_action=MCPCall("soqlQuery", {"query": 123}),
                reason="bad argument type",
            ),
            max_steps=1,
        )

        state = driver.run([{"role": "user", "content": "Look this up"}])

        self.assertEqual(len(client.calls), 0)
        self.assertEqual(state.actions["failed"][0]["reason"], "MCP argument 'query' must be a string.")

    def test_driver_records_backend_error_as_failed_action_for_next_decision(self):
        decisions = [
            WorkflowDecision(
                "backend_action",
                backend_action=MCPCall("soqlQuery", {"query": "SELECT Id FROM Account LIMIT 1"}),
                reason="try backend lookup",
            ),
            WorkflowDecision(
                "frontend_action",
                frontend_message="I need to try a different lookup path.",
                reason="backend rejected previous query shape",
            ),
        ]

        def selector(frame, state, reachable, tools):
            if state.actions["failed"]:
                self.assertIn("Backend rejected", state.actions["failed"][-1]["reason"])
            return decisions.pop(0)

        driver = WorkflowDriver(
            FailingMCPClient(),
            EnvironmentIR(),
            frame_inferer=lambda messages, env_summary: InstanceFrame(goal="lookup account"),
            decision_selector=selector,
            max_steps=2,
        )

        state = driver.run([{"role": "user", "content": "Look this up"}])

        self.assertEqual(len(state.actions["executed"]), 1)
        self.assertEqual(len(state.actions["failed"]), 1)
        self.assertEqual(state.actions["failed"][0]["name"], "soqlQuery")
        self.assertIn("different lookup", driver.render(state))

    def test_driver_can_resume_existing_state_with_new_user_message(self):
        decisions = [
            WorkflowDecision(
                "frontend_action",
                frontend_message="which account",
                reason="target is ambiguous",
            ),
            WorkflowDecision(
                "complete",
                candidate_outcome={"answer": "Acme"},
                candidate_response="Acme",
                reason="clarified",
            ),
        ]
        driver = WorkflowDriver(
            FakeMCPClient(),
            EnvironmentIR(),
            frame_inferer=lambda messages, env_summary: InstanceFrame(
                goal="clarify target",
                outcome_contract=OutcomeContract("direct clarification", requires_verification=False),
            ),
            decision_selector=lambda frame, state, reachable, tools: decisions.pop(0),
        )

        state = driver.run([{"role": "user", "content": "Look this up"}])
        self.assertEqual(state.completion_state.status, "needs_action")

        state = driver.run(
            [{"role": "user", "content": "Look this up"}, {"role": "user", "content": "Account is Acme"}],
            initial_state=state,
        )

        self.assertTrue(state.completion_state.ready)
        self.assertTrue(any(message.get("content") == "Account is Acme" for message in state.history))

    def test_followup_turn_refocuses_frame_and_clears_stale_candidate(self):
        def selector(frame, state, reachable, tools):
            self.assertIsNone(state.candidates.get("response"))
            self.assertFalse(state.completion_state.ready)
            self.assertEqual(frame.goal, "Answer the original policy question.")
            self.assertEqual(frame.metadata.get("latest_user_message"), "What about after 30 days?")
            self.assertTrue(
                any(item.get("source") == "user_followup" for item in state.resolved["unresolved"])
            )
            return WorkflowDecision(
                "frontend_action",
                frontend_message="I will answer the latest follow-up.",
                state_updates={
                    "frame": {
                        "goal": "Answer whether the policy still applies after 30 days.",
                        "request_summary": "User asks what happens after 30 days.",
                    }
                },
                reason="follow-up focus is active",
            )

        driver = WorkflowDriver(
            FakeMCPClient(),
            EnvironmentIR(),
            frame_inferer=lambda messages, env_summary: InstanceFrame(
                goal="Answer the original policy question.",
                request_summary="Original policy question.",
            ),
            decision_selector=selector,
            max_steps=1,
        )
        state = driver.initialize_state([{"role": "user", "content": "Can I get a refund?"}], {})
        state.candidates["response"] = "Stale answer"
        state.candidates["outcome"] = {"answer": "stale"}
        state.completion_state = CompletionState(ready=True, status="ready_to_respond")

        state = driver.run(
            [
                {"role": "user", "content": "Can I get a refund?"},
                {"role": "assistant", "content": "Stale answer"},
                {"role": "user", "content": "What about after 30 days?"},
            ],
            initial_state=state,
        )

        self.assertEqual(driver.render(state), "I will answer the latest follow-up.")
        self.assertEqual(state.frame.goal, "Answer whether the policy still applies after 30 days.")

    def test_claim_upsert_replaces_existing_claim_and_moves_it_to_end(self):
        env_ir = EnvironmentIR(
            objects={"Account": ObjectSchema("Account", fields={"Id": {"type": "id"}, "Name": {"type": "string"}})},
            tool_schemas=[{"name": "soqlQuery"}],
        )
        decisions = [
            WorkflowDecision(
                "backend_action",
                backend_action=MCPCall("soqlQuery", {"query": "SELECT Id, Name FROM Account LIMIT 1"}),
            ),
            WorkflowDecision(
                "complete",
                candidate_response="Acme Corporation",
                claims=[
                    Claim(
                        "account_name",
                        "The account name is Acme.",
                        status="supported",
                        value="Acme",
                        supporting_evidence_ids=["ev_obs_soqlQuery_001xx"],
                    ),
                    Claim(
                        "other_claim",
                        "The account exists.",
                        status="supported",
                        value=True,
                        supporting_evidence_ids=["ev_obs_soqlQuery_001xx"],
                    ),
                ],
            ),
            WorkflowDecision(
                "complete",
                candidate_response="Acme Corporation",
                claims=[
                    Claim(
                        "account_name",
                        "The account name is Acme Corporation.",
                        status="supported",
                        value="Acme Corporation",
                        supporting_evidence_ids=["ev_obs_soqlQuery_001xx"],
                    )
                ],
            ),
        ]

        def selector(frame, state, reachable, tools):
            return decisions.pop(0)

        driver = WorkflowDriver(
            FakeMCPClient(),
            env_ir,
            frame_inferer=lambda messages, env_summary: InstanceFrame(
                goal="answer account lookup",
                outcome_contract=OutcomeContract("answer", requires_verification=False),
            ),
            decision_selector=selector,
            max_steps=3,
        )

        state = driver.initialize_state([{"role": "user", "content": "What is the account name?"}], {})
        state = driver.step(state)
        state = driver.step(state)
        state.completion_state.ready = False
        state.completion_state.status = "running"
        state = driver.step(state)

        claims = state.derived["claims"]
        self.assertEqual([claim.claim_id for claim in claims], ["other_claim", "account_name"])
        self.assertEqual(claims[-1].value, "Acme Corporation")
        self.assertNotIn("Acme.", [claim.claim_text for claim in claims])

    def test_driver_accepts_effect_state_updates(self):
        decisions = [
            WorkflowDecision(
                "complete",
                candidate_outcome={"updated": True},
                candidate_response="Updated.",
                state_updates={
                    "effects": [
                        {
                            "effect_id": "effect_stage_update",
                            "action_id": "step_1",
                            "operation": "update",
                            "object_name": "Opportunity",
                            "record_id": "006xx",
                            "status": "confirmed",
                            "changes": {"StageName": {"old": "Discovery", "new": "Negotiation"}},
                            "reason": "Stage update confirmed by backend.",
                        }
                    ]
                },
            )
        ]

        driver = WorkflowDriver(
            FakeMCPClient(),
            EnvironmentIR(),
            frame_inferer=lambda messages, env_summary: InstanceFrame(
                goal="update opportunity stage",
                outcome_contract=OutcomeContract("stage update confirmed"),
            ),
            decision_selector=lambda frame, state, reachable, tools: decisions.pop(0),
            max_steps=2,
        )

        state = driver.run([{"role": "user", "content": "Update the stage"}])

        self.assertTrue(state.completion_state.ready)
        self.assertEqual(state.effects[0].effect_id, "effect_stage_update")
        self.assertEqual(state.effects[0].operation, "update")
        self.assertEqual(state.effects[0].changes["StageName"]["new"], "Negotiation")


if __name__ == "__main__":
    unittest.main()
