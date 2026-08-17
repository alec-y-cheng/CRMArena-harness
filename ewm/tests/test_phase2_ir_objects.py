import json
import unittest

from ewm.ir.environment import EnvironmentIR, ObjectSchema, RelationshipInfo, reachable_information
from ewm.ir.frame import EvidenceRequirement, InstanceFrame, OutcomeContract, ResponseContract
from ewm.ir.state import Claim, Effect, EvidenceItem, ExecutionState, Observation


class Phase2IRObjectTests(unittest.TestCase):
    def test_frame_represents_read_confidentiality_and_lookup_without_task_family(self):
        frame = InstanceFrame(
            goal="answer the requester using allowed evidence",
            request_summary="customer asks for a product detail from a recent purchase",
            actor={"kind": "external_customer"},
            entities_or_references=[{"kind": "product_description", "value": "trail jacket"}],
            constraints=["only disclose requester-appropriate information"],
            evidence_requirements=[
                EvidenceRequirement(
                    "retrieve customer-scoped purchase evidence",
                    requirement_id="req_purchase",
                    evidence_type="order_history",
                    source="environment",
                    subject="current requester",
                ),
                EvidenceRequirement(
                    "retrieve public product catalog evidence",
                    requirement_id="req_product",
                    evidence_type="product_catalog",
                    source="environment",
                ),
            ],
            outcome_contract=OutcomeContract(
                "requested answer is supported by cited evidence",
                success_criteria=["all answer claims cite retrieved evidence"],
            ),
            response_contract=ResponseContract(
                "return only the requested product detail",
                format_hint="short factual answer",
            ),
        )

        encoded = json.dumps(frame.to_dict(), sort_keys=True)
        self.assertIn("external_customer", encoded)
        self.assertIn("order_history", encoded)
        self.assertNotIn("knowledge_qa", encoded)
        self.assertNotIn("named_entity_disambiguation", encoded)

    def test_execution_state_round_trips_and_validates_claim_support(self):
        state = ExecutionState(
            InstanceFrame(
                goal="answer direct lookup",
                evidence_requirements=[EvidenceRequirement("retrieve associated account")],
            )
        )
        state.add_observation(
            Observation("obs_1", "soqlQuery", {"records": [{"Id": "0031", "AccountId": "0011"}]})
        )
        state.add_evidence(
            EvidenceItem(
                "ev_1",
                "obs_1",
                {"Id": "0031", "AccountId": "0011"},
                source_tool="soqlQuery",
                source_object="Contact",
                record_id="0031",
                subject_scope="internal",
            )
        )
        state.add_claim(
            Claim(
                "cl_1",
                "The associated account is 0011.",
                status="supported",
                value="0011",
                supporting_evidence_ids=["ev_1"],
            )
        )
        state.add_claim(
            Claim("cl_bad", "Unsupported claim.", status="unsupported", supporting_evidence_ids=["missing"])
        )
        state.add_effect(
            Effect(
                "effect_1",
                action_id="step_1",
                operation="update",
                object_name="Contact",
                record_id="0031",
                status="confirmed",
                before={"Status__c": "New"},
                after={"Status__c": "Active"},
                changes={"Status__c": {"old": "New", "new": "Active"}},
                evidence_ids=["ev_1"],
                observation_id="obs_1",
            )
        )
        state.add_effect(
            Effect("effect_bad", operation="update", evidence_ids=["missing"], observation_id="missing_obs")
        )

        decoded = ExecutionState.from_dict(json.loads(state.to_json(sort_keys=True)))

        self.assertEqual(decoded.collected["evidence"][0].source_object, "Contact")
        self.assertEqual(decoded.derived["claims"][0].value, "0011")
        self.assertEqual(decoded.effects[0].operation, "update")
        self.assertEqual(decoded.effects[0].changes["Status__c"]["new"], "Active")
        self.assertEqual([claim.claim_id for claim in decoded.claims_with_invalid_support()], ["cl_bad"])
        self.assertEqual([effect.effect_id for effect in decoded.effects_with_invalid_support()], ["effect_bad"])

    def test_environment_ir_serializes_and_returns_shallow_reachability(self):
        env_ir = EnvironmentIR(
            objects={
                "Opportunity": ObjectSchema(
                    "Opportunity",
                    fields={"Id": {"type": "id"}, "AccountId": {"type": "reference"}},
                    relationships=[
                        RelationshipInfo(
                            "Opportunity",
                            "Account",
                            "Account",
                            field="AccountId",
                            direction="parent",
                        )
                    ],
                ),
                "Account": ObjectSchema("Account", fields={"Id": {"type": "id"}, "Name": {"type": "string"}}),
            },
            tool_schemas=[{"name": "soqlQuery"}, {"name": "getRelatedRecords"}],
        )
        state = ExecutionState()
        state.resolved["entities"].append({"object": "Opportunity", "id": "0061"})

        reachable = reachable_information(state, env_ir, depth=1)
        encoded = json.dumps([item.to_dict() for item in reachable], sort_keys=True)

        self.assertTrue(env_ir.has_tool("soqlQuery"))
        self.assertIn("Opportunity", encoded)
        self.assertIn("traverse_relationship", encoded)
        self.assertIn("0061", encoded)


if __name__ == "__main__":
    unittest.main()
