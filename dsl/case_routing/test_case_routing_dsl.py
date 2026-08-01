import unittest

from dsl.case_routing.actions import (
    agents_with_max_count,
    agents_with_min_count,
    count_cases_by_owner,
    filter_counts_to_agents,
    query_closed_cases_by_issue,
    query_closed_cases_by_order_items,
    query_issues,
    query_open_cases_by_agents,
    query_order_items_by_product,
    query_products_by_terms,
    render_agent_id_response,
    sanitize_search_term,
)
from dsl.case_routing.parser import (
    CaseRoutingParseError,
    parse_candidate_selection_json,
    parse_case_routing_slots_json,
)


ISSUE_ID = "a01Wt0000000001IAA"
PRODUCT_ID = "01tWt000006hUgwIAE"
ORDER_ITEM_ID = "802Wt0000000001IAA"
AGENT_A = "005Wt0000000001IAA"
AGENT_B = "005Wt0000000002IAA"


class CaseRoutingDSLTest(unittest.TestCase):
    def test_parse_slots(self):
        slots = parse_case_routing_slots_json(
            """
            {
              "case_subject": "Difficulty Accessing Training Modules for VerifySim Elite",
              "case_description": "The customer cannot access online training modules.",
              "issue_summary": "difficulty accessing training modules",
              "issue_search_terms": ["accessing training modules"],
              "product_search_terms": ["VerifySim Elite"]
            }
            """
        )
        self.assertEqual(slots.case_subject, "Difficulty Accessing Training Modules for VerifySim Elite")
        self.assertEqual(slots.issue_search_terms, ["accessing training modules"])
        self.assertEqual(slots.product_search_terms, ["VerifySim Elite"])

    def test_parse_slots_rejects_malformed_lists(self):
        with self.assertRaises(CaseRoutingParseError):
            parse_case_routing_slots_json(
                """
                {
                  "case_subject": "",
                  "case_description": "",
                  "issue_summary": "",
                  "issue_search_terms": "access",
                  "product_search_terms": []
                }
                """
            )

    def test_selection_must_be_allowed_candidate(self):
        selection = parse_candidate_selection_json(
            '{"selected_id": "a01Wt0000000001IAA", "confidence": "high", "rationale": "closest"}',
            allowed_ids=[ISSUE_ID],
        )
        self.assertEqual(selection.selected_id, ISSUE_ID)
        with self.assertRaises(CaseRoutingParseError):
            parse_candidate_selection_json(
                '{"selected_id": "a01Wt0000000999IAA", "confidence": "high", "rationale": "closest"}',
                allowed_ids=[ISSUE_ID],
            )

    def test_query_templates(self):
        self.assertEqual(query_issues(), "SELECT Id, Name FROM Issue__c")
        self.assertIn("FROM Case WHERE IssueId__c = '{}'".format(ISSUE_ID), query_closed_cases_by_issue(ISSUE_ID))
        self.assertIn("Status = 'Closed'", query_closed_cases_by_issue(ISSUE_ID))
        product_query = query_products_by_terms(["VerifySim Elite"])
        self.assertIn("FIND {VerifySim Elite}", product_query)
        self.assertIn("RETURNING Product2", product_query)
        hyphenated_query = query_products_by_terms(["AI Cirku-Tech platform"])
        self.assertIn("FIND {AI Cirku Tech platform}", hyphenated_query)
        self.assertNotIn("AI Cirku-Tech", hyphenated_query)
        self.assertIn("FROM OrderItem WHERE Product2Id = '{}'".format(PRODUCT_ID), query_order_items_by_product(PRODUCT_ID))
        case_query = query_closed_cases_by_order_items([ORDER_ITEM_ID])
        self.assertIn("OrderItemId__c IN ('{}')".format(ORDER_ITEM_ID), case_query)
        workload_query = query_open_cases_by_agents([AGENT_A, AGENT_B])
        self.assertIn("OwnerId IN ('{}', '{}')".format(AGENT_A, AGENT_B), workload_query)
        self.assertIn("Status != 'Closed'", workload_query)

    def test_owner_counts_and_ties(self):
        cases = [{"OwnerId": AGENT_A}, {"OwnerId": AGENT_A}, {"OwnerId": AGENT_B}]
        counts = count_cases_by_owner(cases)
        self.assertEqual(counts, {AGENT_A: 2, AGENT_B: 1})
        self.assertEqual(agents_with_max_count(counts), [AGENT_A])
        self.assertEqual(agents_with_max_count({AGENT_A: 1, AGENT_B: 1}), [AGENT_A, AGENT_B])

    def test_product_counts_include_zero_for_issue_tied_agents(self):
        counts = filter_counts_to_agents({AGENT_A: 3}, [AGENT_A, AGENT_B])
        self.assertEqual(counts, {AGENT_A: 3, AGENT_B: 0})
        self.assertEqual(agents_with_max_count(counts), [AGENT_A])

    def test_workload_chooses_min_open_cases(self):
        counts = {AGENT_A: 2, AGENT_B: 0}
        self.assertEqual(agents_with_min_count(counts, [AGENT_A, AGENT_B]), [AGENT_B])

    def test_sanitize_search_term_splits_hyphenated_products(self):
        self.assertEqual(sanitize_search_term(["AI Cirku-Tech"]), "AI Cirku Tech")

    def test_renderer(self):
        self.assertEqual(render_agent_id_response(AGENT_A), AGENT_A)
        self.assertEqual(render_agent_id_response(None), "None")


if __name__ == "__main__":
    unittest.main()
