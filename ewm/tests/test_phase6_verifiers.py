import unittest

from ewm.ir.environment import EnvironmentIR, ObjectSchema
from ewm.ir.frame import InstanceFrame, OutcomeContract
from ewm.ir.state import Claim, CompletionState, Effect, EvidenceItem, ExecutionState, Observation
from ewm.mcp.client import MCPCall, MCPToolSchema
from ewm.runtime.completion import evaluate_completion
from ewm.runtime.verifier import (
    CompletionVerifierSuite,
    LLMCompletionVerifier,
    run_completion_verifiers,
    validate_mcp_call,
    verify_completion_state,
    verify_effect_support,
    verify_evidence_support,
    verify_schema_validity,
)


class Phase6VerifierTests(unittest.TestCase):
    def test_completion_state_uses_three_generic_statuses(self):
        state = ExecutionState()
        state.completion_state = CompletionState(ready=False, status="needs_information")
        result = verify_completion_state(state)
        self.assertFalse(result.valid)

        state.completion_state = CompletionState(ready=False, status="needs_action")
        self.assertTrue(verify_completion_state(state).valid)

        state.completion_state = CompletionState(ready=False, status="needs_verification")
        self.assertTrue(verify_completion_state(state).valid)

        state.completion_state = CompletionState(ready=True, status="ready_to_respond")
        self.assertTrue(verify_completion_state(state).valid)

    def test_evidence_support_verifier_rejects_missing_evidence_ids(self):
        state = ExecutionState()
        state.add_claim(Claim("c1", "unsupported", supporting_evidence_ids=["missing"]))
        result = verify_evidence_support(state)
        self.assertFalse(result.valid)
        self.assertIn("c1", result.metadata["claim_ids"])

    def test_effect_support_verifier_rejects_missing_references(self):
        state = ExecutionState()
        state.add_effect(
            Effect(
                "effect_bad",
                operation="update",
                evidence_ids=["missing_ev"],
                observation_id="missing_obs",
            )
        )

        result = verify_effect_support(state)

        self.assertFalse(result.valid)
        self.assertEqual(result.metadata["effect_ids"], ["effect_bad"])

    def test_generic_semantic_verifier_can_block_constraint_violation(self):
        state = ExecutionState(
            InstanceFrame(
                actor={"kind": "external_customer"},
                constraints=["only disclose requester-appropriate information"],
            )
        )
        state.add_evidence(
            EvidenceItem(
                "ev_internal",
                "obs_1",
                {"policy": "internal"},
                subject_scope="internal_company",
            )
        )
        state.add_claim(
            Claim(
                "c1",
                "Internal policy says no.",
                status="supported",
                supporting_evidence_ids=["ev_internal"],
            )
        )
        state.candidates["outcome"] = {"supporting_evidence_ids": ["ev_internal"]}
        state.candidates["response"] = "Internal fact."

        def model(payload):
            return {
                "valid": False,
                "reason": "Candidate response violates the instance constraints.",
            }

        suite_result = CompletionVerifierSuite(
            semantic_verifiers=[LLMCompletionVerifier(model)]
        ).run(state.frame, state, EnvironmentIR())
        completion = evaluate_completion(state.frame, state, suite_result=suite_result)

        self.assertFalse(completion.ready)
        self.assertEqual(completion.status, "needs_verification")
        self.assertEqual(completion.verifier_summary["status"], "blocked")
        self.assertIn("violates", completion.reason)

    def test_aggregate_completion_verifiers(self):
        env_ir = EnvironmentIR(objects={"Account": ObjectSchema("Account", fields={"Id": {"type": "id"}})})
        state = ExecutionState(InstanceFrame(outcome_contract=OutcomeContract("direct lookup")))
        state.add_evidence(EvidenceItem("ev_1", "obs_1", {"Id": "001"}, source_object="Account"))
        state.add_claim(Claim("c1", "Account exists.", status="supported", supporting_evidence_ids=["ev_1"]))
        state.candidates["outcome"] = {"answer": "001"}
        state.candidates["response"] = "001"
        state.completion_state = CompletionState(ready=True, status="ready_to_respond")

        self.assertTrue(verify_schema_validity(env_ir).valid)
        self.assertTrue(run_completion_verifiers(state.frame, state, env_ir).valid)

    def test_completion_can_be_supported_by_confirmed_effect(self):
        env_ir = EnvironmentIR(objects={"Opportunity": ObjectSchema("Opportunity", fields={"Id": {"type": "id"}})})
        state = ExecutionState(InstanceFrame(outcome_contract=OutcomeContract("update if confirmed")))
        state.add_effect(
            Effect(
                "effect_1",
                operation="update",
                object_name="Opportunity",
                record_id="006xx",
                status="confirmed",
                changes={"StageName": {"old": "Discovery", "new": "Negotiation"}},
            )
        )
        state.candidates["outcome"] = {"updated": True}
        state.candidates["response"] = "Updated."

        self.assertTrue(run_completion_verifiers(state.frame, state, env_ir).valid)

    def test_completion_suite_accepts_llm_style_semantic_verifier(self):
        env_ir = EnvironmentIR(objects={"Account": ObjectSchema("Account", fields={"Id": {"type": "id"}})})
        state = ExecutionState(InstanceFrame(outcome_contract=OutcomeContract("answer if supported")))
        state.add_evidence(EvidenceItem("ev_1", "obs_1", {"Id": "001"}, source_object="Account"))
        state.candidates["outcome"] = {"answer": "001"}
        state.candidates["response"] = "001"

        def semantic_verifier(frame, state, env_ir):
            from ewm.mcp.client import ValidationResult

            return ValidationResult(True, "LLM verifier judged state sufficient.", {"verifier": "semantic_completion"})

        result = CompletionVerifierSuite(semantic_verifiers=[semantic_verifier]).run(state.frame, state, env_ir)

        self.assertTrue(result.valid)
        self.assertEqual(result.status, "allowed")
        self.assertIn("semantic_completion", str(result.to_dict()))

    def test_llm_completion_verifier_receives_compact_write_effect_payload(self):
        captured = {}
        env_ir = EnvironmentIR(objects={"Opportunity": ObjectSchema("Opportunity", fields={"Id": {"type": "id"}})})
        state = ExecutionState(InstanceFrame(outcome_contract=OutcomeContract("update if supported")))
        state.add_observation(Observation("obs_1", "updateRecord", {"ok": True}))
        state.add_evidence(EvidenceItem("ev_1", "obs_1", {"Id": "006xx"}, source_object="Opportunity"))
        state.add_effect(
            Effect(
                "effect_1",
                operation="update",
                object_name="Opportunity",
                record_id="006xx",
                status="confirmed",
                evidence_ids=["ev_1"],
                observation_id="obs_1",
            )
        )
        state.candidates["outcome"] = {"updated": True}
        state.candidates["response"] = "Updated."

        def model(payload):
            captured.update(payload)
            return {"valid": True, "reason": "effect confirms update"}

        suite_result = CompletionVerifierSuite(
            semantic_verifiers=[LLMCompletionVerifier(model)]
        ).run(state.frame, state, env_ir)

        self.assertTrue(suite_result.valid)
        effects = captured["execution_state"]["effects"]
        self.assertEqual(effects[0]["effect_id"], "effect_1")
        self.assertEqual(captured["cited_evidence_spans"][0]["evidence_id"], "ev_1")
        self.assertIn("execution_state", captured)
        self.assertNotIn("collected", captured["execution_state"])


if __name__ == "__main__":
    unittest.main()
