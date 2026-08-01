"""Unit tests for the shared external-facing router."""

import unittest

from dsl.external_facing.actions import (
    classify_external_request_prompt,
    evaluate_final_response,
    evaluate_intended_retrieval,
    render_refusal,
    render_unavailable_response,
    respond_to_user,
    should_fallback_to_ned_from_clarify,
)
from dsl.external_facing.actions import ExternalRequestRoute
from dsl.external_facing.harness import ExternalFacingRouter
from dsl.external_facing.parser import (
    ExternalFacingParseError,
    parse_external_request_route_json,
)


class ExternalFacingRouterTests(unittest.TestCase):
    def test_parse_knowledge_qa_route(self):
        route = parse_external_request_route_json(
            """
            <think>route public support question</think>
            {
              "request_type": "knowledge_qa",
              "route": "knowledge_qa",
              "expected_actions": ["query_public_knowledge_articles"],
              "evidence_required": [
                {"evidence_type": "public_product_support", "subject_scope": "public", "reason": "product care answer"}
              ],
              "subject_scope": "public",
              "clarification_needed": false,
              "missing_information": [],
              "disallowed_information": [],
              "reason": "The customer asks a public product care question."
            }
            """
        )

        self.assertEqual(route.route, "knowledge_qa")
        self.assertEqual(route.expected_actions, ["query_public_knowledge_articles"])
        self.assertEqual(route.evidence_required[0]["evidence_type"], "public_product_support")
        self.assertEqual(route.subject_scope, "public")
        self.assertFalse(route.clarification_needed)

    def test_parse_ned_route(self):
        route = parse_external_request_route_json(
            """
            {
              "request_type": "named_entity_disambiguation",
              "route": "named_entity_disambiguation",
              "expected_actions": ["query_purchase_history", "query_product_catalog"],
              "evidence_required": [
                {"evidence_type": "current_customer_purchase_history", "subject_scope": "current_customer", "reason": "match owned purchases"},
                {"evidence_type": "product_catalog", "subject_scope": "public", "reason": "resolve product names"}
              ],
              "subject_scope": "current_customer",
              "clarification_needed": false,
              "missing_information": [],
              "disallowed_information": [],
              "reason": "The customer asks to identify a product from their purchases."
            }
            """
        )

        self.assertEqual(route.route, "named_entity_disambiguation")
        self.assertIn("query_purchase_history", route.expected_actions)
        self.assertIn("product_catalog", [item["evidence_type"] for item in route.evidence_required])

    def test_parse_rejects_invented_evidence_class(self):
        with self.assertRaises(ExternalFacingParseError):
            parse_external_request_route_json(
                """
                {
                  "request_type": "knowledge_qa",
                  "route": "knowledge_qa",
                  "expected_actions": ["query_public_knowledge_articles"],
                  "evidence_required": [
                    {"evidence_type": "secret_article_search", "subject_scope": "public", "reason": "bad evidence"}
                  ],
                  "subject_scope": "public",
                  "clarification_needed": false,
                  "missing_information": [],
                  "disallowed_information": ["confidential_company_knowledge"],
                  "reason": "bad evidence class"
                }
                """
            )

    def test_parse_clarify_requires_missing_information(self):
        with self.assertRaises(ExternalFacingParseError):
            parse_external_request_route_json(
                """
                {
                  "request_type": "unknown",
                  "route": "clarify",
                  "expected_actions": ["ask_clarification"],
                  "evidence_required": [],
                  "subject_scope": "unknown",
                  "clarification_needed": true,
                  "missing_information": [],
                  "disallowed_information": [],
                  "reason": "too vague"
                }
                """
            )

    def test_parse_refuse_derives_disallowed_information_from_evidence(self):
        route = parse_external_request_route_json(
            """
            {
              "request_type": "confidential_request",
              "route": "refuse",
              "expected_actions": ["refuse"],
              "evidence_required": [
                {"evidence_type": "confidential_company_knowledge", "subject_scope": "internal_company", "reason": "internal policy"}
              ],
              "subject_scope": "internal_company",
              "clarification_needed": false,
              "missing_information": [],
              "disallowed_information": [],
              "reason": "needs internal policy"
            }
            """
        )

        self.assertEqual(route.route, "refuse")
        self.assertIn("confidential_company_knowledge", route.disallowed_information)

    def test_parse_refuse_requires_some_disallowed_evidence(self):
        with self.assertRaises(ExternalFacingParseError):
            parse_external_request_route_json(
                """
                {
                  "request_type": "confidential_request",
                  "route": "refuse",
                  "expected_actions": ["refuse"],
                  "evidence_required": [],
                  "subject_scope": "public",
                  "clarification_needed": false,
                  "missing_information": [],
                  "disallowed_information": [],
                  "reason": "no evidence to block"
                }
                """
            )

    def test_prompt_exposes_fixed_routes_and_evidence_classes(self):
        prompt = classify_external_request_prompt(
            "Can you tell me how to wash my jacket?",
            "Can you tell me how to wash my jacket?",
        )

        self.assertIn("knowledge_qa", prompt)
        self.assertIn("named_entity_disambiguation", prompt)
        self.assertIn("expected_actions", prompt)
        self.assertIn("evidence_required", prompt)
        self.assertIn("public_product_support", prompt)
        self.assertIn("confidential_company_knowledge", prompt)
        self.assertIn("Return JSON", prompt)

    def test_intended_retrieval_gate_allows_public_knowledge(self):
        decision = evaluate_intended_retrieval(
            [{"evidence_type": "public_product_support", "subject_scope": "public", "reason": "support"}],
            "public",
        )

        self.assertTrue(decision.allowed)

    def test_intended_retrieval_gate_blocks_internal_policy(self):
        decision = evaluate_intended_retrieval(
            [{"evidence_type": "case_routing_policy", "subject_scope": "internal_company", "reason": "routing rules"}],
            "internal_company",
        )

        self.assertFalse(decision.allowed)
        self.assertIn("case_routing_policy", decision.blocked_information)

    def test_final_response_gate_blocks_disallowed_evidence(self):
        decision = evaluate_final_response(
            "I cannot share that.",
            ["internal_agent_performance"],
        )

        self.assertFalse(decision.allowed)


    def test_intended_retrieval_gate_blocks_confidential_evidence_from_knowledge_action(self):
        decision = evaluate_intended_retrieval(
            [
                {
                    "evidence_type": "confidential_company_knowledge",
                    "subject_scope": "internal_company",
                    "reason": "answer would expose non-public company knowledge",
                }
            ],
            "internal_company",
        )

        self.assertFalse(decision.allowed)
        self.assertIn("confidential_company_knowledge", decision.blocked_information)

    def test_clarification_and_refusal_renderers_are_customer_facing(self):
        self.assertIn(
            "product type",
            respond_to_user(["product type", "purchase timeframe"]),
        )
        self.assertNotIn("JSON", render_refusal("requires internal policy"))
        self.assertIn("safe, customer-scoped request", render_unavailable_response())

    def test_direct_reference_clarification_asks_for_fallback_purchase_context(self):
        question = respond_to_user(["customer_identifier", "order_reference"])

        self.assertIn("product type", question)
        self.assertIn("when you purchased", question)
        self.assertNotIn("customer_identifier", question)
        self.assertNotIn("order_reference", question)

    def test_identifier_only_clarify_can_fallback_to_ned(self):
        route = ExternalRequestRoute(
            request_type="unknown",
            route="clarify",
            expected_actions=["query_purchase_history", "query_product_catalog"],
            evidence_required=[
                {"evidence_type": "current_customer_purchase_history", "subject_scope": "current_customer", "reason": "purchase lookup"},
                {"evidence_type": "product_catalog", "subject_scope": "public", "reason": "product matching"},
            ],
            subject_scope="current_customer",
            clarification_needed=True,
            missing_information=["customer_identifier", "order_reference"],
        )

        self.assertTrue(should_fallback_to_ned_from_clarify(route))

    def test_router_retries_then_returns_valid_route(self):
        outputs = iter(
            [
                "not json",
                """
                {
                  "request_type": "knowledge_qa",
                  "route": "knowledge_qa",
                  "expected_actions": ["query_public_knowledge_articles"],
                  "evidence_required": [
                    {"evidence_type": "public_product_support", "subject_scope": "public", "reason": "support question"}
                  ],
                  "subject_scope": "public",
                  "clarification_needed": false,
                  "missing_information": [],
                  "disallowed_information": [],
                  "reason": "public support question"
                }
                """,
            ]
        )
        router = ExternalFacingRouter(lambda _messages: next(outputs), max_retries=1)

        route = router.route(
            "How should I wash my jacket?",
            "How should I wash my jacket?",
        )

        self.assertEqual(route.route, "knowledge_qa")
        self.assertEqual(router.last_info["model_calls"], 2)
        self.assertEqual(len(router.last_info["router_parse_errors"]), 1)


if __name__ == "__main__":
    unittest.main()
