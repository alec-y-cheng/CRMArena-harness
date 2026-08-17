"""Tests for the generic symbolic runtime scaffold."""

import json
import unittest

from dsl.general_runtime.driver import CanonicalGeneralRuntimeDriver, _policy_search_terms_from_state, _prepare_extraction_evidence
from dsl.general_runtime.parser import RuntimeParseError, parse_answer_candidate_json, parse_disclosure_gate_json, parse_instance_frame_json
from dsl.general_runtime.prompts import build_disclosure_gate_prompt, build_generic_extraction_prompt
from dsl.general_runtime.state import EvidenceItem
from dsl.general_runtime.state import ExecutionState
from dsl.general_runtime.internal_router import InternalWorkflowRouter, parse_internal_workflow_route_json
from dsl.general_runtime.verifier import compute_enabled_actions, validate_instance_frame
from dsl.general_runtime.workflow_specs import list_workflow_specs, load_workflow_spec


class GeneralRuntimeTests(unittest.TestCase):
    def test_bundled_workflow_specs_validate(self):
        specs = list_workflow_specs()
        self.assertIn("external_knowledge_qa", specs)
        self.assertIn("lead_qualification", specs)
        self.assertIn("case_routing", specs)
        for workflow_id in specs:
            self.assertEqual(load_workflow_spec(workflow_id).workflow_id, workflow_id)

    def test_internal_router_parses_supported_workflow(self):
        route = parse_internal_workflow_route_json(json.dumps({
            "route": "policy_violation_identification",
            "confidence": "high",
            "target_record_id": "500Wt00000DDyznIAD",
            "clarification_requirements": [],
            "reason": "Case policy breach request",
        }))

        self.assertEqual(route.route, "policy_violation_identification")
        self.assertEqual(route.target_record_id, "500Wt00000DDyznIAD")

    def test_internal_router_accepts_stringified_empty_clarification_requirements(self):
        route = parse_internal_workflow_route_json(json.dumps({
            "route": "wrong_stage_rectification",
            "confidence": "high",
            "target_record_id": "006Wt000007BGGjIAO",
            "clarification_requirements": "[]",
            "reason": "Opportunity stage request",
        }))

        self.assertEqual(route.route, "wrong_stage_rectification")
        self.assertEqual(route.clarification_requirements, [])

    def test_internal_router_heuristic_fallback_routes_opportunity(self):
        router = InternalWorkflowRouter(lambda _messages: "{}")

        route = router.route(
            "Can you verify Opportunity Id 006Wt000007BGGjIAO stage?",
            "Can you verify Opportunity Id 006Wt000007BGGjIAO stage?",
        )

        self.assertEqual(route.route, "wrong_stage_rectification")
        self.assertEqual(route.target_record_id, "006Wt000007BGGjIAO")

    def test_instance_frame_validates_against_workflow_spec(self):
        spec = load_workflow_spec("external_knowledge_qa")
        payload = {
            "workflow_id": "external_knowledge_qa",
            "request_summary": "return policy question",
            "target_entities": [{"entity_type": "product_or_item", "surface_text": "shoes"}],
            "query_terms": ["return policy shoes"],
            "product_terms": ["shoes"],
            "constraints": [],
            "required_evidence_instances": [
                {
                    "requirement": "answer_public_customer_question",
                    "evidence_type": "public_warranty_or_returns",
                    "subject_scope": "public",
                    "reason": "return policy evidence",
                }
            ],
            "clarification_requirements": [],
        }
        frame = parse_instance_frame_json(json.dumps(payload))
        validate_instance_frame(frame, spec)

    def test_instance_frame_parser_normalizes_nested_instance_contract(self):
        payload = {
            "workflow_id": "external_named_entity_disambiguation",
            "customer_id": "003Ws000004Fo3qIAC",
            "instance_contract": {
                "product_terms": "women's trail jacket",
                "purchase_date_window": {
                    "start_date": "2020-06-01",
                    "end_date": "2020-06-15",
                    "source_text": "about two weeks ago",
                    "type": "purchase_date_window",
                },
                "target_entities": [
                    {
                        "description": "women's trail jacket",
                        "attributes": {"category": "apparel"},
                    }
                ],
            },
            "required_evidence_instances": [
                {
                    "requirement": "resolve_current_customer_product",
                    "evidence_type": "current_customer_purchase_history",
                    "subject_scope": "current_customer",
                    "reason": "need matching customer purchase",
                }
            ],
            "clarification_requirements": [],
            "request_summary": "Find the jacket purchased about two weeks ago.",
        }
        frame = parse_instance_frame_json(json.dumps(payload))

        self.assertEqual(frame.workflow_id, "external_named_entity_disambiguation")
        self.assertEqual(frame.product_terms, ["women's trail jacket"])
        self.assertEqual(frame.constraints[0]["start_date"], "2020-06-01")

    def test_instance_frame_parser_decodes_json_string_fields(self):
        payload = {
            "workflow_id": "external_named_entity_disambiguation",
            "request_summary": "Find the trail jacket I bought recently.",
            "target_entities": json.dumps([
                {"entity_type": "Product2", "surface_text": "trail jacket"}
            ]),
            "product_terms": json.dumps(["trail jacket", "jacket"]),
            "constraints": json.dumps([
                {
                    "type": "purchase_date_window",
                    "source_text": "recently",
                    "start_date": "2020-03-17",
                    "end_date": "2020-06-15",
                    "is_valid_for_retrieval": True,
                }
            ]),
            "required_evidence_instances": json.dumps([
                {
                    "requirement": "resolve_current_customer_product",
                    "evidence_type": "current_customer_purchase_history",
                    "subject_scope": "current_customer",
                    "reason": "match current customer purchase",
                }
            ]),
            "clarification_requirements": "[]",
        }

        frame = parse_instance_frame_json(json.dumps(payload))

        self.assertEqual(frame.product_terms, ["trail jacket", "jacket"])
        self.assertEqual(frame.target_entities[0]["surface_text"], "trail jacket")
        self.assertEqual(frame.constraints[0]["start_date"], "2020-03-17")
        self.assertEqual(frame.clarification_requirements, [])

    def test_answer_candidate_parser_decodes_json_string_candidate(self):
        spec = load_workflow_spec("external_knowledge_qa")
        state = ExecutionState(spec)
        state.evidence_items = [
            EvidenceItem(
                "ka0Return",
                "public_knowledge_article",
                "Knowledge__kav",
                {"Id": "ka0Return", "Title": "Returns"},
                "public",
            )
        ]
        candidate = {
            "answer": "Within 90 days of purchase.",
            "confidence": "high",
            "evidence": "Return article says 90 days.",
            "selected_evidence": [
                {
                    "evidence_id": "ka0Return",
                    "evidence_type": "public_warranty_or_returns",
                    "subject_scope": "public",
                    "safe_to_use": True,
                    "reason": "public return policy",
                }
            ],
            "clarification_requirements": [],
        }

        parsed = parse_answer_candidate_json(
            json.dumps({"answer_candidate": json.dumps(candidate)}),
            state,
        )

        self.assertEqual(parsed["answer"], "Within 90 days of purchase.")
        self.assertEqual(parsed["selected_evidence"][0]["evidence_id"], "ka0Return")

    def test_answer_candidate_parser_preserves_extra_structured_fields(self):
        spec = load_workflow_spec("external_knowledge_qa")
        state = ExecutionState(spec)
        state.evidence_items = [
            EvidenceItem(
                "ka0Return",
                "public_knowledge_article",
                "Knowledge__kav",
                {"Id": "ka0Return", "Title": "Returns"},
                "public",
            )
        ]
        parsed = parse_answer_candidate_json(
            json.dumps(
                {
                    "answer_candidate": {
                        "answer": "Within 90 days.",
                        "confidence": "high",
                        "evidence": "Return article says 90 days.",
                        "selected_evidence": [
                            {
                                "evidence_id": "ka0Return",
                                "evidence_type": "public_warranty_or_returns",
                                "subject_scope": "public",
                                "safe_to_use": True,
                                "reason": "public return policy",
                            }
                        ],
                        "clarification_requirements": [],
                        "candidate_records": [
                            {"evidence_id": "ka0Return", "match_status": "supports"}
                        ],
                    }
                }
            ),
            state,
        )

        self.assertEqual(parsed["candidate_records"][0]["match_status"], "supports")

    def test_policy_evidence_ranking_surfaces_relevant_article(self):
        spec = load_workflow_spec("policy_violation_identification")
        state = ExecutionState(spec)
        state.instance_frame = parse_instance_frame_json(json.dumps({
            "workflow_id": "policy_violation_identification",
            "request_summary": "Did Case 500Wt00000DDyznIAD breach any policy?",
            "target_entities": [{"case_id": "500Wt00000DDyznIAD"}],
            "query_terms": ["Scalability Problems", "QuantumPCB Modeler"],
            "product_terms": [],
            "constraints": [],
            "required_evidence_instances": [],
            "clarification_requirements": [],
        }))
        state.runtime_data = {"info": {}}
        state.retrieved_records["Case"] = [
            {
                "Id": "500Wt00000DDyznIAD",
                "Subject": "Scalability Problems",
                "Description": "QuantumPCB Modeler does not scale for growing needs.",
            }
        ]
        state.evidence_items = [
            EvidenceItem(
                "500Wt00000DDyznIAD",
                "case_record",
                "Case",
                state.retrieved_records["Case"][0],
                "internal_company",
            )
        ] + [
            EvidenceItem(
                "ka0Noise{}".format(index),
                "internal_policy_article",
                "Knowledge__kav",
                {"Id": "ka0Noise{}".format(index), "Title": "Unrelated Topic {}".format(index), "Summary": "billing renewal invoice"},
                "internal_company",
            )
            for index in range(50)
        ] + [
            EvidenceItem(
                "ka0Relevant",
                "internal_policy_article",
                "Knowledge__kav",
                {
                    "Id": "ka0Relevant",
                    "Title": "Addressing Scalability Challenges",
                    "Summary": "QuantumPCB Modeler scalability support for growing enterprise needs.",
                },
                "internal_company",
            )
        ]

        _prepare_extraction_evidence(state)

        ranked_ids = [item["evidence_id"] for item in state.runtime_data["extraction_evidence_items"]]
        self.assertIn("500Wt00000DDyznIAD", ranked_ids)
        self.assertIn("ka0Relevant", ranked_ids[:5])
        self.assertLessEqual(len(ranked_ids), 40)

    def test_policy_search_terms_prioritize_case_linked_context(self):
        spec = load_workflow_spec("policy_violation_identification")
        state = ExecutionState(spec)
        state.instance_frame = parse_instance_frame_json(json.dumps({
            "workflow_id": "policy_violation_identification",
            "request_summary": "Check policy violation for Case 500Wt00000DDyznIAD.",
            "target_entities": [
                {"type": "Case.Id", "value": "500Wt00000DDyznIAD", "role": "policy_violation_evaluation_target"}
            ],
            "query_terms": [],
            "product_terms": [],
            "constraints": [],
            "required_evidence_instances": [],
            "clarification_requirements": [],
        }))
        state.retrieved_records["Case"] = [
            {
                "Id": "500Wt00000DDyznIAD",
                "Subject": "Scalability Problems",
                "Description": "QuantumPCB Modeler does not scale for growing needs.",
            }
        ]
        state.retrieved_records["Issue__c"] = [{"Id": "a03Issue", "Name": "Scalability Problems"}]
        state.retrieved_records["Product2"] = [
            {"Id": "01tProduct", "Name": "QuantumPCB Modeler", "Description": "PCB modeling software"}
        ]

        terms = _policy_search_terms_from_state(state)

        self.assertEqual(terms[0], "Scalability Problems")
        self.assertIn("QuantumPCB Modeler does not scale for growing needs.", terms)
        self.assertIn("QuantumPCB Modeler", terms)
        self.assertNotIn("500Wt00000DDyznIAD", terms)
        self.assertNotIn("Case.Id", terms)
        self.assertNotIn("policy_violation_evaluation_target", terms)

    def test_case_linked_context_follows_order_item_to_order(self):
        class FakeEnv:
            def __init__(self):
                self.queries = []

            def step(self, action):
                query = action["content"]
                self.queries.append(query)
                if "FROM Issue__c" in query:
                    return ([{"Id": "a03Wt00000JqmX6IAJ", "Name": "Customization Issue"}], 0, False, {"end_reason": {}})
                if "FROM OrderItem" in query:
                    return (
                        [
                            {
                                "Id": "802Wt00000797eCIAQ",
                                "OrderId": "801Wt00000PGc9QIAT",
                                "Product2Id": "01tWt000006hTUkIAM",
                                "Quantity": 10,
                                "UnitPrice": 100,
                            }
                        ],
                        0,
                        False,
                        {"end_reason": {}},
                    )
                if "FROM Order WHERE" in query:
                    return (
                        [
                            {
                                "Id": "801Wt00000PGc9QIAT",
                                "AccountId": "001Wt00000PGSwYIAX",
                                "Status": "Activated",
                                "EffectiveDate": "2021-10-01",
                                "CreatedDate": "2021-09-30T00:00:00.000+0000",
                            }
                        ],
                        0,
                        False,
                        {"end_reason": {}},
                    )
                if "FROM Product2" in query:
                    return (
                        [
                            {
                                "Id": "01tWt000006hTUkIAM",
                                "Name": "CloudLink Designer",
                                "Description": "Cloud design collaboration",
                                "IsActive": True,
                            }
                        ],
                        0,
                        False,
                        {"end_reason": {}},
                    )
                raise AssertionError("unexpected query: {}".format(query))

        spec = load_workflow_spec("policy_violation_identification")
        state = ExecutionState(spec)
        state.retrieved_records["Case"] = [
            {
                "Id": "500Case000000001",
                "IssueId__c": "a03Wt00000JqmX6IAJ",
                "OrderItemId__c": "802Wt00000797eCIAQ",
            }
        ]
        state.runtime_data = {
            "env": FakeEnv(),
            "messages": [],
            "info": {"env_steps": 0, "retrieved_objects": {}, "query_errors": []},
        }
        driver = CanonicalGeneralRuntimeDriver("policy_violation_identification", lambda _messages: "{}")

        driver._handle_query_case_linked_context(state, {})

        self.assertIn("Order", state.retrieved_records)
        self.assertEqual(state.retrieved_records["Order"][0]["EffectiveDate"], "2021-10-01")
        evidence_types = [item.evidence_type for item in state.evidence_items]
        self.assertIn("case_order_record", evidence_types)
        self.assertEqual(state.runtime_data["info"]["case_linked_context"]["order_count"], 1)

    def test_instance_frame_parser_uses_nested_date_window_when_constraints_is_metadata(self):
        payload = {
            "workflow_id": "external_named_entity_disambiguation",
            "request_summary": "Find the bra purchased last week.",
            "instance_data": {
                "product_terms": "high-tech fitness bra",
                "target_entities": [
                    {
                        "description": "high-tech fitness bra",
                        "attributes": {"category": "fitness"},
                    }
                ],
                "purchase_date_window": {
                    "source_text": "last week",
                    "start_date": "2020-12-21",
                    "end_date": "2020-12-27",
                    "is_valid_for_retrieval": True,
                },
                "clarification_requirements": [],
            },
            "required_evidence_instances": [],
            "constraints": {
                "allowed_actions": ["query_current_customer", "query_purchase_history"],
            },
        }
        frame = parse_instance_frame_json(json.dumps(payload))

        self.assertEqual(frame.constraints[0]["type"], "purchase_date_window")
        self.assertEqual(frame.constraints[0]["start_date"], "2020-12-21")
        self.assertEqual(frame.constraints[0]["end_date"], "2020-12-27")
        self.assertTrue(frame.constraints[0]["is_valid_for_retrieval"])

    def test_instance_frame_parser_uses_action_plan_query_terms(self):
        payload = {
            "workflow_id": "external_knowledge_qa",
            "request_summary": "Customer asks how swim goggles avoid fogging.",
            "target_entities": [],
            "action_plan": {
                "next_action": "retrieve_knowledge",
                "action_params": {
                    "query": "swim goggles fogging anti fog care",
                },
            },
            "required_evidence_instances": [],
            "clarification_requirements": [],
        }

        frame = parse_instance_frame_json(json.dumps(payload))

        self.assertEqual(frame.query_terms, ["swim goggles fogging anti fog care"])

    def test_enabled_actions_use_preconditions(self):
        spec = load_workflow_spec("external_knowledge_qa")
        state = ExecutionState(spec)
        self.assertEqual(compute_enabled_actions(state), [])
        payload = {
            "workflow_id": "external_knowledge_qa",
            "request_summary": "care question",
            "target_entities": [],
            "query_terms": ["wash jacket"],
            "product_terms": [],
            "constraints": [],
            "required_evidence_instances": [
                {
                    "requirement": "answer_public_customer_question",
                    "evidence_type": "public_product_support",
                    "subject_scope": "public",
                    "reason": "support evidence",
                }
            ],
            "clarification_requirements": [],
        }
        state.instance_frame = parse_instance_frame_json(json.dumps(payload))
        enabled = [item.action for item in compute_enabled_actions(state)]
        self.assertIn("retrieve_knowledge", enabled)

    def test_kqa_extraction_prompt_surfaces_narrow_answer_guidance(self):
        spec = load_workflow_spec("external_knowledge_qa")
        state = ExecutionState(spec)
        state.instance_frame = parse_instance_frame_json(json.dumps({
            "workflow_id": "external_knowledge_qa",
            "request_summary": "Why replace running shoes?",
            "target_entities": [],
            "query_terms": ["running shoes replacement"],
            "product_terms": ["running shoes"],
            "constraints": [],
            "required_evidence_instances": [],
            "clarification_requirements": [],
        }))
        state.evidence_items = [
            EvidenceItem(
                "ka0Known",
                "public_knowledge_article",
                "Knowledge__kav",
                {
                    "Id": "ka0Known",
                    "FAQ_Answer__c": "Replace shoes to maintain support and prevent injuries.",
                },
                "public",
            )
        ]

        prompt = build_generic_extraction_prompt(state)

        self.assertIn("Answer guidance:", prompt)
        self.assertIn("requested slot", prompt)
        self.assertIn("causal mechanism or purpose", prompt)

    def test_kqa_instance_prompt_surfaces_search_term_guidance(self):
        spec = load_workflow_spec("external_knowledge_qa")
        from dsl.general_runtime.prompts import build_instance_frame_prompt

        prompt = build_instance_frame_prompt(
            spec,
            "How do swim goggles avoid fogging?",
            metadata={},
            conversation_history=[],
        )

        self.assertIn("2-5 concise Knowledge__kav search phrases", prompt)
        self.assertIn("Do not include filler", prompt)

    def test_ned_extraction_prompt_surfaces_material_match_guidance(self):
        spec = load_workflow_spec("external_named_entity_disambiguation")
        state = ExecutionState(spec)
        state.instance_frame = parse_instance_frame_json(json.dumps({
            "workflow_id": "external_named_entity_disambiguation",
            "request_summary": "Find the basketball tank top purchased five days ago.",
            "target_entities": [{"surface_text": "basketball tank top"}],
            "query_terms": [],
            "product_terms": ["basketball tank top"],
            "constraints": [],
            "required_evidence_instances": [],
            "clarification_requirements": [],
        }))

        prompt = build_generic_extraction_prompt(state)

        self.assertIn("materially matches", prompt)
        self.assertIn("broad category", prompt)

    def test_disclosure_gate_parser_rejects_unselected_evidence_ids(self):
        spec = load_workflow_spec("external_knowledge_qa")
        state = ExecutionState(spec)
        state.selected_evidence = [
            {
                "evidence_id": "ka0Allowed",
                "evidence_type": "public_product_support",
                "subject_scope": "public",
                "safe_to_use": True,
                "reason": "selected",
            }
        ]

        with self.assertRaises(RuntimeParseError):
            parse_disclosure_gate_json(
                json.dumps(
                    {
                        "safe_to_disclose": False,
                        "recommended_action": "refuse",
                        "blocked_evidence_ids": ["ka0Other"],
                        "blocked_information": ["confidential_company_knowledge"],
                        "reason": "not selected",
                    }
                ),
                state,
            )

    def test_disclosure_gate_prompt_includes_policy_and_selected_records(self):
        spec = load_workflow_spec("external_knowledge_qa")
        state = ExecutionState(spec)
        state.instance_frame = parse_instance_frame_json(json.dumps({
            "workflow_id": "external_knowledge_qa",
            "request_summary": "Can I disclose this?",
            "target_entities": [],
            "query_terms": ["discount"],
            "product_terms": [],
            "constraints": [],
            "required_evidence_instances": [],
            "clarification_requirements": [],
        }))
        state.answer_candidate = {
            "answer": "15% discount",
            "confidence": "high",
            "evidence": "Discount article",
            "selected_evidence": [],
            "clarification_requirements": [],
        }
        state.selected_evidence = [
            {
                "evidence_id": "ka0Discount",
                "evidence_type": "public_product_support",
                "subject_scope": "public",
                "safe_to_use": True,
                "reason": "selected span",
            }
        ]
        state.evidence_items = [
            EvidenceItem(
                "ka0Discount",
                "public_knowledge_article",
                "Knowledge__kav",
                {"Id": "ka0Discount", "Title": "Discounts", "FAQ_Answer__c": "15% discount"},
                "public",
            )
        ]

        prompt = build_disclosure_gate_prompt(state)

        self.assertIn("Decide whether the selected content itself is public customer-facing", prompt)
        self.assertIn("ka0Discount", prompt)
        self.assertIn("15% discount", prompt)

    def test_disclosure_gate_blocks_unsafe_answer_candidate(self):
        spec = load_workflow_spec("external_knowledge_qa")
        state = ExecutionState(spec)
        state.runtime_data = {
            "info": {"model_calls": 0},
            "messages": [],
            "user_visible_conversation_history": [{"role": "user", "content": "Tell me the confidential policy."}],
        }
        state.answer_candidate = {
            "answer": "15% discount",
            "confidence": "high",
            "evidence": "selected policy",
            "selected_evidence": [],
            "clarification_requirements": [],
        }
        state.selected_evidence = [
            {
                "evidence_id": "ka0Policy",
                "evidence_type": "public_product_support",
                "subject_scope": "public",
                "safe_to_use": True,
                "reason": "selected by extractor",
            }
        ]
        state.evidence_items = [
            EvidenceItem(
                "ka0Policy",
                "public_knowledge_article",
                "Knowledge__kav",
                {"Id": "ka0Policy", "FAQ_Answer__c": "15% discount"},
                "public",
            )
        ]
        driver = CanonicalGeneralRuntimeDriver(
            "external_knowledge_qa",
            lambda _messages: json.dumps(
                {
                    "safe_to_disclose": False,
                    "recommended_action": "refuse",
                    "blocked_evidence_ids": ["ka0Policy"],
                    "blocked_information": ["internal_commercial_policy"],
                    "reason": "selected evidence is non-public commercial policy",
                }
            ),
        )

        driver._handle_disclosure_gate(state, {})

        self.assertEqual(state.completion_state, "refused")
        self.assertIn("external_gate_refusal", state.runtime_data["info"])

    def test_disclosure_gate_allows_safe_answer_candidate(self):
        spec = load_workflow_spec("external_knowledge_qa")
        state = ExecutionState(spec)
        state.runtime_data = {
            "info": {"model_calls": 0},
            "messages": [],
            "user_visible_conversation_history": [{"role": "user", "content": "How should I clean this product?"}],
        }
        state.answer_candidate = {
            "answer": "Wipe it with a soft cloth.",
            "confidence": "high",
            "evidence": "care article",
            "selected_evidence": [],
            "clarification_requirements": [],
        }
        state.selected_evidence = [
            {
                "evidence_id": "ka0Care",
                "evidence_type": "public_product_support",
                "subject_scope": "public",
                "safe_to_use": True,
                "reason": "public care guidance",
            }
        ]
        driver = CanonicalGeneralRuntimeDriver(
            "external_knowledge_qa",
            lambda _messages: json.dumps(
                {
                    "safe_to_disclose": True,
                    "recommended_action": "answer",
                    "blocked_evidence_ids": [],
                    "blocked_information": [],
                    "reason": "ordinary public support guidance",
                }
            ),
        )

        driver._handle_disclosure_gate(state, {})

        self.assertNotIn("external_gate_refusal", state.runtime_data["info"])
        self.assertNotEqual(state.completion_state, "refused")


if __name__ == "__main__":
    unittest.main()
