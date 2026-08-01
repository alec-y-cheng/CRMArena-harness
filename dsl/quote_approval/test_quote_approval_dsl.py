import unittest

from dsl.quote_approval.actions import (
    ArticleExtraction,
    ArticlePolicyJudgment,
    PolicySearchIntent,
    QuoteApprovalState,
    apply_article_policy_judgment,
    article_extraction_from_discount_evaluation,
    default_policy_searches,
    derive_quote_facts,
    evaluate_discount_policy_structure,
    evaluate_discount_policy,
    extract_target_quote_id,
    has_discount_or_volume_facts,
    is_discount_policy_article,
    query_knowledge_articles,
    query_line_items,
    query_pricebook_entries_by_ids,
    query_products_by_ids,
    query_quote,
    render_failed_quote_response,
    sanitize_search_term,
)
from dsl.quote_approval.parser import (
    QuoteApprovalParseError,
    parse_article_json,
    parse_discount_policy_structure_json,
    parse_policy_search_plan_json,
)


QUOTE_ID = "0Q0Wt0000008abcMAA"
ARTICLE_ID = "ka0Wt000000EpSUIA0"


class QuoteApprovalDSLTest(unittest.TestCase):
    def test_extract_target_quote_id(self):
        self.assertEqual(
            extract_target_quote_id("Please review quote 0Q0Wt0000008abcMAA."),
            QUOTE_ID,
        )
        self.assertIsNone(extract_target_quote_id("Please review this quote."))

    def test_query_templates_are_fixed(self):
        quote_query = query_quote(QUOTE_ID)
        self.assertIn("FROM Quote WHERE Id = '{}'".format(QUOTE_ID), quote_query)
        self.assertIn("ExpirationDate", quote_query)

        line_query = query_line_items(QUOTE_ID)
        self.assertIn("FROM QuoteLineItem WHERE QuoteId = '{}'".format(QUOTE_ID), line_query)
        self.assertIn("Product2Id", line_query)
        self.assertIn("TotalPrice", line_query)

        product_query = query_products_by_ids(["01tWt000006hUgwIAE"])
        self.assertIn("FROM Product2 WHERE Id IN ('01tWt000006hUgwIAE')", product_query)

        price_query = query_pricebook_entries_by_ids(["01uWt0000027Q34IAE"])
        self.assertIn("FROM PricebookEntry WHERE Id IN ('01uWt0000027Q34IAE')", price_query)

    def test_knowledge_query_sanitizes_terms(self):
        self.assertEqual(
            sanitize_search_term(["AI-VeriSim", "{bundle}", "approval?"]),
            "AI VeriSim bundle approval",
        )
        query = query_knowledge_articles(["AI-VeriSim", "bundle", "approval"])
        self.assertIn("FIND {AI VeriSim bundle approval}", query)
        self.assertIn("Knowledge__kav(Id, Title, Summary, FAQ_Answer__c)", query)
        self.assertNotIn("WHERE FAQ_Answer__c", query)

    def test_derive_quote_facts(self):
        quote = [
            {
                "Id": QUOTE_ID,
                "Name": "Quote A",
                "Status": "Needs Review",
                "ExpirationDate": "2026-08-01T00:00:00Z",
                "OpportunityId": "006Wt000001abcDMAA",
            }
        ]
        lines = [
            {
                "Id": "0QLWt0000000001MAA",
                "QuoteId": QUOTE_ID,
                "Product2Id": "01tWt000006hUgwIAE",
                "PricebookEntryId": "01uWt0000027Q34IAE",
                "Quantity": 2,
                "UnitPrice": 100,
                "Discount": 10,
                "TotalPrice": 180,
            },
            {
                "Id": "0QLWt0000000002MAA",
                "QuoteId": QUOTE_ID,
                "Product2Id": "01tWt000006hUsEIAU",
                "Quantity": 1,
                "UnitPrice": 50,
                "Discount": 0,
            },
        ]
        products = [
            {"Id": "01tWt000006hUgwIAE", "Name": "AI DesignShift"},
            {"Id": "01tWt000006hUsEIAU", "Name": "SimuCheck Ultra"},
        ]
        facts = derive_quote_facts(quote, lines, products, [])
        self.assertEqual(facts["quote_total"], 230)
        self.assertEqual(facts["max_discount_percent"], 10)
        self.assertEqual(facts["total_quantity"], 3)
        self.assertEqual(facts["product_names"], ["AI DesignShift", "SimuCheck Ultra"])

    def test_default_policy_searches_are_fact_driven(self):
        state = QuoteApprovalState()
        state.quote_facts = {
            "max_discount_percent": 12,
            "expiration_date": "2026-08-01T00:00:00Z",
            "status": "Needs Review",
            "quote_total": 230,
            "total_quantity": 3,
            "product_names": ["AI DesignShift"],
        }
        searches = default_policy_searches(state)
        dimensions = [search.dimension for search in searches]
        self.assertIn("discount", dimensions)
        self.assertIn("product_bundle", dimensions)
        self.assertIn("expiration", dimensions)
        self.assertEqual(dimensions[0], "discount")
        self.assertTrue(has_discount_or_volume_facts(state))

    def test_discount_policy_article_detection(self):
        self.assertTrue(
            is_discount_policy_article(
                {
                    "Title": "Volume-Based Discounts",
                    "FAQ_Answer__c": "Discount tiers apply by purchase volume.",
                }
            )
        )
        self.assertFalse(
            is_discount_policy_article(
                {
                    "Title": "Mandatory Bundles for Quotes",
                    "FAQ_Answer__c": "PulseSim Pro must include other products.",
                }
            )
        )

    def test_evaluate_discount_policy_flags_tier_mismatch(self):
        state = QuoteApprovalState()
        state.quote_facts = {
            "quote_total": 10089.79,
            "line_items": [
                {"product_name": "CloudLink Designer", "quantity": 8, "discount_percent": 5},
                {"product_name": "SecureData Nexus", "quantity": 5, "discount_percent": 15},
                {"product_name": "PulseSim Pro", "quantity": 10, "discount_percent": 10},
            ],
        }
        article = {
            "Id": ARTICLE_ID,
            "Title": "Volume-Based Discounts",
            "Summary": "Volume-Based Discounts",
            "FAQ_Answer__c": (
                "1. **5% Discount for Purchases Over $5**\n"
                "2. **10% Discount for Purchases Over $10**\n"
                "3. **15% Discount for Purchases Over $20**"
            ),
        }
        evaluation = evaluate_discount_policy(state, [article])
        self.assertTrue(evaluation.violated)
        self.assertEqual(evaluation.article_id, ARTICLE_ID)
        self.assertIn("SecureData Nexus", evaluation.evidence)

    def test_evaluate_discount_policy_flags_excessive_discount(self):
        state = QuoteApprovalState()
        state.quote_facts = {
            "quote_total": 18981.61,
            "line_items": [
                {"product_name": "AI Cirku-Tech", "quantity": 15, "discount_percent": 20},
                {"product_name": "OptiPower Max", "quantity": 12, "discount_percent": 10},
            ],
        }
        article = {
            "Id": ARTICLE_ID,
            "Title": "Volume-Based Discounts",
            "Summary": "Volume-Based Discounts",
            "FAQ_Answer__c": (
                "5% Discount for Purchases Over $5. "
                "10% Discount for Purchases Over $10. "
                "15% Discount for Purchases Over $20."
            ),
        }
        evaluation = evaluate_discount_policy(state, [article])
        self.assertTrue(evaluation.violated)
        self.assertIn("exceeding", evaluation.evidence)

    def test_parse_and_evaluate_discount_policy_structure_json(self):
        payload = """{
          "article_id": "ka0Wt000000EpSUIA0",
          "policy_type": "volume_discount",
          "basis": "quote_total",
          "application": "expected",
          "scope": "line_item",
          "tiers": [
            {"threshold": 5, "operator": ">", "discount_percent": 5},
            {"threshold": 10, "operator": ">", "discount_percent": 10},
            {"threshold": 20, "operator": ">", "discount_percent": 15}
          ],
          "rule_confidence": "high",
          "notes": "Discounts are automatically applied at checkout."
        }"""
        structure = parse_discount_policy_structure_json(payload, [ARTICLE_ID])
        self.assertEqual(structure.application, "expected")
        self.assertEqual(len(structure.tiers), 3)

        state = QuoteApprovalState()
        state.quote_facts = {
            "quote_total": 6039.89,
            "line_items": [
                {"product_name": "QuantumPCB Modeler", "quantity": 8, "discount_percent": 10},
                {"product_name": "PulseSim Pro", "quantity": 3, "discount_percent": 0},
            ],
        }
        evaluation = evaluate_discount_policy_structure(state, structure)
        self.assertTrue(evaluation.violated)
        self.assertEqual(evaluation.article_id, ARTICLE_ID)

    def test_line_quantity_discount_policy_marks_task_1781_shape_compliant(self):
        payload = """{
          "article_id": "ka0Wt000000EpSUIA0",
          "policy_type": "volume_discount",
          "basis": "quote_total",
          "application": "expected",
          "scope": "quote",
          "tiers": [
            {"threshold": 5, "operator": ">=", "discount_percent": 5},
            {"threshold": 10, "operator": ">=", "discount_percent": 10},
            {"threshold": 20, "operator": ">=", "discount_percent": 15}
          ],
          "rule_confidence": "high",
          "notes": "Extractor may say quote_total, but the symbolic layer uses line quantity for volume discounts."
        }"""
        structure = parse_discount_policy_structure_json(payload, [ARTICLE_ID])
        state = QuoteApprovalState()
        state.quote_facts = {
            "quote_total": 30726.8925,
            "line_items": [
                {"product_name": "OptiEnergy Suite", "quantity": 10, "discount_percent": 10},
                {"product_name": "CloudLink Designer", "quantity": 20, "discount_percent": 15},
                {"product_name": "CircuitAI Innovator", "quantity": 25, "discount_percent": 15},
                {"product_name": "SecureFlow Suite", "quantity": 15, "discount_percent": 10},
            ],
        }
        evaluation = evaluate_discount_policy_structure(state, structure)
        self.assertFalse(evaluation.violated)
        extraction = article_extraction_from_discount_evaluation(evaluation)
        self.assertIsNone(extraction.selected_article_id)
        self.assertEqual(extraction.judgments[0].status, "not_violated")

    def test_parse_policy_search_plan_json(self):
        text = """<think>one line</think>
        {
          "searches": [
            {
              "dimension": "discount",
              "terms": ["discount", "approval", "threshold"],
              "reason": "line has discount"
            }
          ]
        }
        """
        searches = parse_policy_search_plan_json(text)
        self.assertEqual(len(searches), 1)
        self.assertEqual(searches[0].dimension, "discount")
        self.assertEqual(searches[0].terms, ["discount", "approval", "threshold"])

    def test_parse_article_json_validates_candidate_ids(self):
        payload = """{
          "selected_article_id": "ka0Wt000000EpSUIA0",
          "judgments": [
            {
              "article_id": "ka0Wt000000EpSUIA0",
              "dimension": "discount",
              "status": "violated",
              "rule_summary": "Discounts above 10 require approval.",
              "evidence": "Quote has 12 percent discount."
            }
          ],
          "additional_searches": []
        }"""
        extraction = parse_article_json(payload, allowed_article_ids=[ARTICLE_ID])
        self.assertEqual(extraction.selected_article_id, ARTICLE_ID)
        with self.assertRaises(QuoteApprovalParseError):
            parse_article_json(payload, allowed_article_ids=["ka0Wt000000OtherA0"])

    def test_render_failed_quote_response(self):
        state = QuoteApprovalState()
        state.knowledge_articles = [{"Id": ARTICLE_ID}]
        extraction = ArticleExtraction(
            judgments=[
                ArticlePolicyJudgment(
                    article_id=ARTICLE_ID,
                    dimension="discount",
                    status="violated",
                )
            ]
        )
        apply_article_policy_judgment(state, extraction)
        self.assertEqual(render_failed_quote_response(state), ARTICLE_ID)
        self.assertEqual(render_failed_quote_response({}), "None")


if __name__ == "__main__":
    unittest.main()
