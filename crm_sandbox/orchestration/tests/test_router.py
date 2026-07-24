import unittest

from crm_sandbox.orchestration import (
    expected_family_from_task_label,
    route_task,
    scaffold_for_family,
    scaffold_for_task,
)


class RouterTest(unittest.TestCase):
    def test_disabled_router_uses_general(self):
        result = route_task(
            "Should this quote be approved?",
            oracle_task_label="quote_approval",
            mode="none",
        )

        self.assertEqual(result.task_family, "general")
        self.assertEqual(result.scaffold_used, "general")

    def test_quote_approval_routes_from_visible_query(self):
        result = route_task(
            "Does this quote's price and configuration comply with company policy? If not, "
            "which knowledge article does it violate? Return only the Id of the knowledge article."
        )

        self.assertEqual(result.task_family, "quote_approval")
        self.assertGreaterEqual(result.confidence, 0.55)
        self.assertIn("quote", result.evidence)

    def test_lead_qualification_routes_from_visible_query(self):
        result = route_task(
            "Does this lead satisfy the BANT qualification criteria? Return only one or several of "
            "Budget, Authority, Need, or Timeline."
        )

        self.assertEqual(result.task_family, "lead_qualification")

    def test_case_routing_routes_from_visible_query(self):
        result = route_task(
            "Use the case routing policy to determine the most suitable agent for the given case. "
            "Return only the Id of the agent."
        )

        self.assertEqual(result.task_family, "case_routing")

    def test_conversion_routes_from_visible_query(self):
        result = route_task("What was the conversion rate for leads in Q3?")

        self.assertEqual(result.task_family, "conversion_rate_comprehension")

    def test_confidentiality_routes_from_visible_query(self):
        result = route_task("Can you share this customer's private information?")

        self.assertEqual(result.task_family, "confidentiality")

    def test_low_confidence_falls_back_to_confidentiality(self):
        result = route_task("What is the latest status?")

        self.assertEqual(result.task_family, "confidentiality")
        self.assertEqual(result.scaffold_used, "confidentiality")

    def test_scaffold_lookup_is_defined_for_all_route_families(self):
        for query in (
            "Does this quote's price and configuration comply with company policy? If not, which knowledge article does it violate? Return only the Id of the knowledge article.",
            "Does this lead satisfy the BANT qualification criteria? Return only one or several of Budget, Authority, Need, or Timeline.",
            "Use the case routing policy to determine the most suitable agent for the given case. Return only the Id of the agent.",
            "What is the conversion rate?",
            "Can you disclose private customer information?",
            "What is the latest status?",
        ):
            result = route_task(query)
            self.assertIsInstance(scaffold_for_family(result.task_family), str)

    def test_expected_family_groups_confidentiality_tasks_for_reporting(self):
        self.assertEqual(expected_family_from_task_label("private_customer_information"), "confidentiality")
        self.assertEqual(expected_family_from_task_label("internal_operation_data"), "confidentiality")
        self.assertEqual(expected_family_from_task_label("confidential_company_knowledge"), "confidentiality")

    def test_task_scaffold_uses_task_specific_template(self):
        scaffold = scaffold_for_task("quote_approval")

        self.assertIn("Task-specific guidance: Quote Approval", scaffold)
        self.assertIn("Final answer contract", scaffold)
        self.assertIn("approve, reject, escalate, or insufficient information", scaffold)
        self.assertNotIn("Completion check", scaffold)
        self.assertNotIn("Confidentiality check", scaffold)

    def test_lead_scaffold_contains_bant_contract(self):
        scaffold = scaffold_for_task("lead_qualification")

        self.assertIn("Task-specific guidance: Lead Qualification", scaffold)
        self.assertIn("Final answer contract", scaffold)
        for criterion in ("Budget", "Authority", "Need", "Timeline"):
            self.assertIn(criterion, scaffold)
        self.assertIn("qualified, not qualified, or insufficient information", scaffold)
        self.assertNotIn("Completion check", scaffold)
        self.assertNotIn("Confidentiality check", scaffold)

    def test_case_routing_scaffold_contains_routing_contract(self):
        scaffold = scaffold_for_task("case_routing")

        self.assertIn("Task-specific guidance: Case Routing", scaffold)
        self.assertIn("Final answer contract", scaffold)
        self.assertIn("routing rules and tie-breakers", scaffold)
        self.assertIn("agent, team, queue, owner, or identifier", scaffold)
        self.assertNotIn("Completion check", scaffold)
        self.assertNotIn("Confidentiality check", scaffold)

    def test_confidentiality_task_scaffold_adds_confidentiality_guard_only(self):
        scaffold = scaffold_for_task("private_customer_information")

        self.assertIn("Task-specific guidance: Private Customer Information", scaffold)
        self.assertIn("Confidentiality check", scaffold)
        self.assertNotIn("Completion check", scaffold)

    def test_routed_confidentiality_scaffold_uses_generic_guard(self):
        scaffold = scaffold_for_family("confidentiality")

        self.assertIn("Confidentiality check", scaffold)
        self.assertNotIn("Task-specific guidance", scaffold)

    def test_internal_metrics_with_agent_and_case_routes_to_confidentiality(self):
        result = route_task(
            "In the past four weeks, identify the agent with the lowest average number of transfers among those managing more than two cases."
        )

        self.assertEqual(result.task_family, "confidentiality")

    def test_confidential_discount_question_routes_to_confidentiality(self):
        result = route_task("What discount is offered for spending more than $20?")

        self.assertEqual(result.task_family, "confidentiality")

    def test_confidential_installation_timeline_routes_to_confidentiality(self):
        result = route_task("If a client orders 25 units, what is the installation timeline?")

        self.assertEqual(result.task_family, "confidentiality")

    def test_bare_lead_verb_routes_to_confidentiality(self):
        result = route_task("What sector does CircuitWave Technologies lead in?")

        self.assertEqual(result.task_family, "confidentiality")

    def test_bare_assignment_question_routes_to_confidentiality(self):
        result = route_task("Who should be assigned to handle this lead?")

        self.assertEqual(result.task_family, "confidentiality")

    def test_full_lead_qualification_shape_still_routes_to_lead(self):
        result = route_task(
            "Can this lead be qualified based on the latest discussions? If the answer is no, "
            "which factors—'Budget', 'Authority', 'Need', or 'Timeline'—are responsible? "
            "Return only one or several of the four BANT factors."
        )

        self.assertEqual(result.task_family, "lead_qualification")

    def test_full_case_routing_shape_still_routes_to_case(self):
        result = route_task(
            "Use the case routing policy to determine the most suitable agent for the given case. "
            "Return only the Id of the agent. ## Given Case - Case Subject: Missing Notifications"
        )

        self.assertEqual(result.task_family, "case_routing")

    def test_full_quote_approval_shape_still_routes_to_quote(self):
        result = route_task(
            "Does the cost and setup of this quote comply with our company policy? If it doesn't, "
            "which knowledge article is it in conflict with? Return only the Id of the knowledge article."
        )

        self.assertEqual(result.task_family, "quote_approval")


if __name__ == "__main__":
    unittest.main()
