"""Unit tests for the named_entity_disambiguation DSL."""

import unittest

from dsl.named_entity_disambiguation.actions import (
    NEDCandidateSelection,
    NEDExtraction,
    normalize_purchase_date_window,
    query_current_customer,
    query_product_catalog,
    query_products_by_ids,
    query_purchase_history,
    render_ned_clarification_prompt,
    render_ned_response,
    sanitize_search_term,
)
from dsl.named_entity_disambiguation.harness import (
    _apply_required_slot_checks,
    _product_search_inputs,
    _task_metadata,
)
from dsl.named_entity_disambiguation.parser import (
    NamedEntityDisambiguationParseError,
    parse_ned_candidate_selection_json,
    parse_ned_clarification_json,
    parse_ned_extraction_json,
)


class NamedEntityDisambiguationDSLTests(unittest.TestCase):
    def test_parse_ned_extraction_json(self):
        parsed = parse_ned_extraction_json(
            """
            <think>extract slots</think>
            {
              "entity_phrase": "speed training jump rope",
              "product_terms": ["speed training jump rope"],
              "date_expression": "one week ago",
              "period": "week",
              "interval_count": 1,
              "exact_purchase_date": "",
              "attributes": ["speed training"],
              "clarification_needed": false,
              "missing_information": []
            }
            """
        )

        self.assertEqual(parsed.entity_phrase, "speed training jump rope")
        self.assertEqual(parsed.period, "week")
        self.assertEqual(parsed.interval_count, 1)
        self.assertFalse(parsed.clarification_needed)

    def test_task_metadata_parses_required_text(self):
        parsed = _task_metadata(
            {
                "required": (
                    "- Contact Id interacting: 003Ws000004FusQIAS\n"
                    "- Today's date: 2021-02-26"
                )
            }
        )

        self.assertEqual(parsed["customer_id"], "003Ws000004FusQIAS")
        self.assertEqual(parsed["today"], "2021-02-26")

    def test_normalize_purchase_date_window_relative_week(self):
        extraction = NEDExtraction(period="week", interval_count=1)

        self.assertEqual(
            normalize_purchase_date_window(extraction, "2020-09-10"),
            ("2020-09-03", "2020-09-03"),
        )

    def test_required_slot_checks_mark_generic_purchase_for_clarification(self):
        from dsl.named_entity_disambiguation.actions import NamedEntityDisambiguationState

        state = NamedEntityDisambiguationState()
        state.extraction = NEDExtraction(
            entity_phrase="purchase",
            product_terms=["purchase"],
            period="week",
            interval_count=2,
            clarification_needed=False,
        )
        state.date_window = ("2021-02-12", "2021-02-12")

        _apply_required_slot_checks(state)

        self.assertTrue(state.extraction.clarification_needed)
        self.assertIn(
            "product kind or distinguishing product attributes",
            state.extraction.missing_information,
        )

    def test_required_slot_checks_mark_missing_timeframe_for_clarification(self):
        from dsl.named_entity_disambiguation.actions import NamedEntityDisambiguationState

        state = NamedEntityDisambiguationState()
        state.extraction = NEDExtraction(
            entity_phrase="sports bra",
            product_terms=["sports bra"],
            period="unknown",
            interval_count=0,
            clarification_needed=False,
        )
        state.date_window = None

        _apply_required_slot_checks(state)

        self.assertTrue(state.extraction.clarification_needed)
        self.assertIn("purchase date or timeframe", state.extraction.missing_information)

    def test_normalize_purchase_date_window_relative_month_clamps_day(self):
        extraction = NEDExtraction(period="month", interval_count=1)

        self.assertEqual(
            normalize_purchase_date_window(extraction, "2021-03-31"),
            ("2021-02-28", "2021-02-28"),
        )

    def test_query_templates_are_customer_scoped_and_safe(self):
        self.assertEqual(
            query_current_customer("003Ws000004FvN4IAK"),
            "SELECT Id, AccountId FROM Contact WHERE Id = '003Ws000004FvN4IAK' LIMIT 1",
        )
        self.assertIn(
            "FIND {AI Training Rope}",
            query_product_catalog(["AI-Training", "{Rope?}"]),
        )
        purchase_query = query_purchase_history(
            "001Ws000004AcctAAE",
            ("2020-09-03", "2020-09-03"),
            ["01tWs000002wROTIA2"],
        )

        self.assertIn("FROM OrderItem WHERE", purchase_query)
        self.assertIn("AccountId = '001Ws000004AcctAAE'", purchase_query)
        self.assertIn("Status = 'Activated'", purchase_query)
        self.assertIn("EffectiveDate >= 2020-09-03", purchase_query)
        self.assertIn("Product2Id IN ('01tWs000002wROTIA2')", purchase_query)

    def test_query_products_by_ids(self):
        query = query_products_by_ids(["01tWs000002wROTIA2", "bad", "01tWs000002wROTIA2"])

        self.assertEqual(
            query,
            "SELECT Id, Name, Description FROM Product2 WHERE Id IN ('01tWs000002wROTIA2')",
        )

    def test_product_search_inputs_fan_out_specific_terms(self):
        extraction = NEDExtraction(
            entity_phrase="high support sports bra",
            product_terms=["sports bra"],
            attributes=["high support"],
        )

        self.assertEqual(
            _product_search_inputs(extraction),
            [
                ["sports bra"],
                ["high support sports bra"],
                ["high support", "high support sports bra"],
            ],
        )

    def test_sanitize_search_term_removes_sosl_punctuation(self):
        self.assertEqual(
            sanitize_search_term(["high-speed", "{racing?}", "suit"]),
            "high speed racing suit",
        )

    def test_parse_selection_accepts_allowed_product(self):
        parsed = parse_ned_candidate_selection_json(
            """
            {
              "selected_product_id": "01tWs000002wROTIA2",
              "evidence": "Purchased product appears in eligible order item.",
              "confidence": "high",
              "ambiguous": false,
              "missing_information": []
            }
            """,
            allowed_product_ids=["01tWs000002wROTIA2"],
        )

        self.assertEqual(parsed.selected_product_id, "01tWs000002wROTIA2")
        self.assertEqual(parsed.confidence, "high")

    def test_parse_selection_rejects_unpurchased_product(self):
        with self.assertRaises(NamedEntityDisambiguationParseError):
            parse_ned_candidate_selection_json(
                """
                {
                  "selected_product_id": "01tWs000002wMISSING",
                  "evidence": "Catalog match only.",
                  "confidence": "medium",
                  "ambiguous": false,
                  "missing_information": []
                }
                """,
                allowed_product_ids=["01tWs000002wROTIA2"],
            )

    def test_parse_clarification_json_accepts_question(self):
        self.assertEqual(
            parse_ned_clarification_json(
                '{"question": "What kind of product did you purchase?"}'
            ),
            "What kind of product did you purchase?",
        )

    def test_parse_clarification_json_rejects_internal_details(self):
        with self.assertRaises(NamedEntityDisambiguationParseError):
            parse_ned_clarification_json(
                '{"question": "Which Salesforce record should I query?"}'
            )

    def test_render_clarification_prompt_uses_missing_information(self):
        prompt = render_ned_clarification_prompt(
            NEDExtraction(
                entity_phrase="purchase",
                product_terms=["purchase"],
                clarification_needed=True,
                missing_information=["product kind or distinguishing product attributes"],
            ),
            ["product kind or distinguishing product attributes"],
            "I need help with my purchase.",
        )

        self.assertIn("product kind or distinguishing product attributes", prompt)
        self.assertIn("Return JSON", prompt)

    def test_render_ned_response(self):
        self.assertEqual(
            render_ned_response(NEDCandidateSelection(selected_product_id="01tWs000002wROTIA2")),
            "01tWs000002wROTIA2",
        )
        self.assertEqual(render_ned_response(NEDCandidateSelection()), "None")


if __name__ == "__main__":
    unittest.main()
