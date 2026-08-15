"""Unit tests for the knowledge_qa DSL."""

import json
import unittest

from dsl.knowledge_qa.actions import (
    KnowledgeQAAnswer,
    KnowledgeQAAnswerSpan,
    KnowledgeQASearchPlan,
    answer_snippet_terms,
    classify_knowledge_selected_evidence_prompt,
    compact_article,
    extract_knowledge_answer_prompt,
    query_public_knowledge_articles,
    render_knowledge_answer_response,
    sanitize_search_term,
)
from dsl.knowledge_qa.parser import (
    KnowledgeQAParseError,
    parse_knowledge_answer_json,
    parse_knowledge_article_evidence_json,
    parse_knowledge_search_plan_json,
)


def _json(data):
    return json.dumps(data)


class KnowledgeQADSLTests(unittest.TestCase):
    def test_search_query_uses_sosl_and_does_not_filter_faq_answer(self):
        query = query_public_knowledge_articles(["AI-VeriSim", "{security?}"])
        self.assertIn("FIND {AI VeriSim security}", query)
        self.assertIn("RETURNING Knowledge__kav(Id, Title, Summary, FAQ_Answer__c)", query)
        self.assertNotIn("WHERE FAQ_Answer__c", query)

    def test_sanitize_search_term_removes_sosl_punctuation(self):
        self.assertEqual(
            sanitize_search_term(["IoT-Duo", "{GDPR}", "security?"]),
            "IoT Duo GDPR security",
        )

    def test_compact_article_uses_search_aware_late_snippet(self):
        prefix = "General introduction. " * 220
        target = (
            "Regular calibration and software updates of your training simulator "
            "will ensure it continues to provide accurate data."
        )
        suffix = " Maintenance appendix. " * 220
        plan = KnowledgeQASearchPlan(
            normalized_question="How to ensure a training simulator provides accurate data",
            search_terms=["simulator calibration steps"],
            product_terms=["training simulator"],
        )
        compacted = compact_article(
            {"Id": "ka0Known", "FAQ_Answer__c": prefix + target + suffix},
            snippet_terms=answer_snippet_terms(plan),
            max_content_chars=700,
            window_chars=180,
        )
        self.assertIn("Regular calibration and software updates", compacted["FAQ_Answer__c"])
        self.assertLess(len(compacted["FAQ_Answer__c"]), 760)

    def test_answer_prompt_requests_minimal_reference_answer(self):
        plan = KnowledgeQASearchPlan(
            normalized_question="What steps keep the simulator accurate?",
            search_terms=["simulator calibration"],
            product_terms=["training simulator"],
        )
        prompt = extract_knowledge_answer_prompt(
            plan,
            [
                {
                    "Id": "ka0Known",
                    "Title": "Training Simulator Care",
                    "Summary": "Care tips for simulator accuracy.",
                    "FAQ_Answer__c": "Regular calibration and software updates keep the simulator accurate.",
                }
            ],
        )
        normalized_prompt = " ".join(prompt.split())
        self.assertIn("shortest grounded reference answer", normalized_prompt)
        self.assertIn("smallest exact article phrase", normalized_prompt)
        self.assertIn("not writing a full customer-service reply", normalized_prompt)

    def test_selected_evidence_prompt_uses_external_taxonomy(self):
        plan = KnowledgeQASearchPlan(
            normalized_question="How do I reset the device?",
            search_terms=["device reset"],
            product_terms=[],
        )
        answer = KnowledgeQAAnswer(
            answer="Hold the reset button for ten seconds.",
            selected_article_ids=["ka0Known"],
            candidate_answer_spans=[
                KnowledgeQAAnswerSpan(
                    span="Hold the reset button for ten seconds.",
                    relevance="direct",
                    include=True,
                    article_id="ka0Known",
                    reason="direct reset instruction",
                )
            ],
        )
        prompt = classify_knowledge_selected_evidence_prompt(
            plan,
            answer,
            [
                {
                    "Id": "ka0Known",
                    "Title": "Device Reset",
                    "Summary": "Reset instructions.",
                    "FAQ_Answer__c": "Hold the reset button for ten seconds.",
                }
            ],
        )
        self.assertIn("Selected evidence", prompt)
        self.assertIn("public_troubleshooting", prompt)
        self.assertIn("confidential_company_knowledge", prompt)
        self.assertIn("Be stricter here than the initial router", prompt)
        self.assertIn("safe_to_use=false", prompt)
        self.assertIn("ka0Known", prompt)
        self.assertIn("Hold the reset button", prompt)

    def test_parse_search_plan_json(self):
        parsed = parse_knowledge_search_plan_json(_json({
            "normalized_question": "What security features does InnovateMax provide?",
            "search_terms": ["InnovateMax security features"],
            "product_terms": ["InnovateMax"],
            "clarification_needed": False,
            "missing_information": [],
        }))
        self.assertEqual(parsed.normalized_question, "What security features does InnovateMax provide?")
        self.assertEqual(parsed.search_terms, ["InnovateMax security features"])
        self.assertFalse(parsed.clarification_needed)

    def test_parse_article_evidence_json_accepts_retrieved_ids(self):
        parsed = parse_knowledge_article_evidence_json(_json({
            "article_evidence": [
                {
                    "article_id": "ka0Known",
                    "evidence_type": "public_troubleshooting",
                    "subject_scope": "public",
                    "safe_to_use": True,
                    "reason": "Customer-facing troubleshooting steps.",
                }
            ]
        }), allowed_article_ids=["ka0Known"])
        self.assertEqual(parsed[0].article_id, "ka0Known")
        self.assertEqual(parsed[0].evidence_type, "public_troubleshooting")
        self.assertTrue(parsed[0].safe_to_use)

    def test_parse_article_evidence_json_allows_partial_classification(self):
        parsed = parse_knowledge_article_evidence_json(_json({
            "article_evidence": [
                {
                    "article_id": "ka0Known",
                    "evidence_type": "public_troubleshooting",
                    "subject_scope": "public",
                    "safe_to_use": True,
                    "reason": "Customer-facing troubleshooting steps.",
                }
            ]
        }), allowed_article_ids=["ka0Known", "ka0Other"])
        self.assertEqual([item.article_id for item in parsed], ["ka0Known"])

    def test_parse_article_evidence_json_accepts_disallowed_commercial_label(self):
        parsed = parse_knowledge_article_evidence_json(_json({
            "article_evidence": [
                {
                    "article_id": "ka0Known",
                    "evidence_type": "internal_commercial_policy",
                    "subject_scope": "internal_company",
                    "safe_to_use": False,
                    "reason": "Discount thresholds are commercial policy evidence.",
                }
            ]
        }), allowed_article_ids=["ka0Known"])
        self.assertEqual(parsed[0].evidence_type, "internal_commercial_policy")
        self.assertFalse(parsed[0].safe_to_use)

    def test_parse_article_evidence_json_rejects_invalid_type(self):
        with self.assertRaises(KnowledgeQAParseError):
            parse_knowledge_article_evidence_json(_json({
                "article_evidence": [
                    {
                        "article_id": "ka0Known",
                        "evidence_type": "marketing_secret",
                        "subject_scope": "public",
                        "safe_to_use": True,
                        "reason": "Invalid label.",
                    }
                ]
            }), allowed_article_ids=["ka0Known"])

    def test_parse_answer_rejects_unretrieved_article_id(self):
        with self.assertRaises(KnowledgeQAParseError):
            parse_knowledge_answer_json(_json({
                "question_type": "description",
                "asked_focus": "security features",
                "candidate_answer_spans": [
                    {
                        "span": "Use advanced encryption.",
                        "relevance": "direct",
                        "include": True,
                        "article_id": "ka0missing",
                        "reason": "answers the security feature question",
                    }
                ],
                "answer": "Use advanced encryption.",
                "selected_article_ids": ["ka0missing"],
                "evidence": "Article says advanced encryption.",
                "confidence": "high",
            }), allowed_article_ids=["ka0Wt000000Known"])

    def test_parse_answer_accepts_retrieved_article_id(self):
        parsed = parse_knowledge_answer_json(_json({
            "question_type": "short_list",
            "asked_focus": "security features",
            "candidate_answer_spans": [
                {
                    "span": "Advanced encryption and multi-factor authentication",
                    "relevance": "direct",
                    "include": True,
                    "article_id": "ka0Wt000000Known",
                    "reason": "directly lists the security features",
                },
                {
                    "span": "The platform also includes onboarding support.",
                    "relevance": "related_but_unasked",
                    "include": False,
                    "article_id": "ka0Wt000000Known",
                    "reason": "not part of the security feature answer",
                },
            ],
            "answer": "Advanced encryption and multi-factor authentication",
            "selected_article_ids": ["ka0Wt000000Known"],
            "evidence": "The article lists encryption and MFA.",
            "confidence": "high",
        }), allowed_article_ids=["ka0Wt000000Known"])
        self.assertEqual(parsed.answer, "Advanced encryption and multi-factor authentication")
        self.assertEqual(parsed.question_type, "short_list")
        self.assertEqual(len(parsed.candidate_answer_spans), 2)

    def test_parse_answer_rejects_none_when_direct_span_is_included(self):
        with self.assertRaises(KnowledgeQAParseError):
            parse_knowledge_answer_json(_json({
                "question_type": "number",
                "asked_focus": "trial length",
                "candidate_answer_spans": [
                    {
                        "span": "The trial lasts 30 days.",
                        "relevance": "direct",
                        "include": True,
                        "article_id": "ka0Wt000000Known",
                        "reason": "directly states the trial length",
                    }
                ],
                "answer": "None",
                "selected_article_ids": [],
                "evidence": "No answer.",
                "confidence": "unknown",
            }), allowed_article_ids=["ka0Wt000000Known"])

    def test_parse_answer_rejects_included_supporting_span(self):
        with self.assertRaises(KnowledgeQAParseError):
            parse_knowledge_answer_json(_json({
                "question_type": "description",
                "asked_focus": "setup requirement",
                "candidate_answer_spans": [
                    {
                        "span": "The product supports guided onboarding.",
                        "relevance": "supporting_context",
                        "include": True,
                        "article_id": "ka0Wt000000Known",
                        "reason": "helpful context",
                    }
                ],
                "answer": "The product supports guided onboarding.",
                "selected_article_ids": ["ka0Wt000000Known"],
                "evidence": "Article mentions onboarding.",
                "confidence": "medium",
            }), allowed_article_ids=["ka0Wt000000Known"])

    def test_parse_answer_rejects_answer_without_direct_span(self):
        with self.assertRaises(KnowledgeQAParseError):
            parse_knowledge_answer_json(_json({
                "question_type": "description",
                "asked_focus": "setup requirement",
                "candidate_answer_spans": [
                    {
                        "span": "The product supports guided onboarding.",
                        "relevance": "related_but_unasked",
                        "include": False,
                        "article_id": "ka0Wt000000Known",
                        "reason": "nearby but not the requested setup requirement",
                    }
                ],
                "answer": "The product supports guided onboarding.",
                "selected_article_ids": ["ka0Wt000000Known"],
                "evidence": "Article mentions onboarding.",
                "confidence": "medium",
            }), allowed_article_ids=["ka0Wt000000Known"])

    def test_parse_answer_rejects_bare_yes_no_with_condition_evidence(self):
        with self.assertRaises(KnowledgeQAParseError):
            parse_knowledge_answer_json(_json({
                "question_type": "yes_no",
                "asked_focus": "refund eligibility after 30 days",
                "candidate_answer_spans": [
                    {
                        "span": "Refund requests must be submitted within 30 days of purchase.",
                        "relevance": "direct",
                        "include": True,
                        "article_id": "ka0Wt000000Known",
                        "reason": "directly gives the deadline condition",
                    }
                ],
                "answer": "No",
                "selected_article_ids": ["ka0Wt000000Known"],
                "evidence": "Article gives a 30-day deadline.",
                "confidence": "high",
            }), allowed_article_ids=["ka0Wt000000Known"])

    def test_renderer_returns_answer_or_none(self):
        self.assertEqual(
            render_knowledge_answer_response(KnowledgeQAAnswer(answer="Every 300-500 miles")),
            "Every 300-500 miles",
        )
        self.assertEqual(render_knowledge_answer_response(KnowledgeQAAnswer(answer="")), "None")

    def test_renderer_falls_back_to_included_direct_span(self):
        answer = KnowledgeQAAnswer(
            answer="None",
            candidate_answer_spans=[
                KnowledgeQAAnswerSpan(
                    span="Within 10 business days",
                    relevance="direct",
                    include=True,
                    article_id="ka0Wt000000Known",
                    reason="direct answer",
                )
            ],
        )
        self.assertEqual(render_knowledge_answer_response(answer), "Within 10 business days")


if __name__ == "__main__":
    unittest.main()
