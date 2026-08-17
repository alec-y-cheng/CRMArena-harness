"""Structured-output schemas for the knowledge_qa DSL."""

from typing import Any, Dict

from dsl.external_facing.schemas import EXTERNAL_EVIDENCE_VALUES
from dsl.external_facing.actions import SUBJECT_SCOPES


KNOWLEDGE_QA_SEARCH_PLAN_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "normalized_question": {"type": "string"},
        "search_terms": {"type": "array", "items": {"type": "string"}},
        "product_terms": {"type": "array", "items": {"type": "string"}},
        "clarification_needed": {"type": "boolean"},
        "clarification_requirements": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "normalized_question",
        "search_terms",
        "product_terms",
        "clarification_needed",
        "clarification_requirements",
    ],
    "additionalProperties": False,
}


KNOWLEDGE_QA_ANSWER_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "question_type": {
            "type": "string",
            "enum": [
                "yes_no",
                "number",
                "single_option",
                "short_list",
                "procedure",
                "reason",
                "description",
            ],
        },
        "asked_focus": {"type": "string"},
        "candidate_answer_spans": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "span": {"type": "string"},
                    "relevance": {
                        "type": "string",
                        "enum": [
                            "direct",
                            "supporting_context",
                            "related_but_unasked",
                            "contradicts",
                        ],
                    },
                    "include": {"type": "boolean"},
                    "article_id": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": [
                    "span",
                    "relevance",
                    "include",
                    "article_id",
                    "reason",
                ],
                "additionalProperties": False,
            },
        },
        "answer": {"type": "string"},
        "selected_article_ids": {"type": "array", "items": {"type": "string"}},
        "evidence": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low", "unknown"]},
    },
    "required": [
        "question_type",
        "asked_focus",
        "candidate_answer_spans",
        "answer",
        "selected_article_ids",
        "evidence",
        "confidence",
    ],
    "additionalProperties": False,
}


KNOWLEDGE_QA_ARTICLE_EVIDENCE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "article_evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "article_id": {"type": "string"},
                    "evidence_type": {"type": "string", "enum": EXTERNAL_EVIDENCE_VALUES},
                    "subject_scope": {"type": "string", "enum": list(SUBJECT_SCOPES)},
                    "safe_to_use": {"type": "boolean"},
                    "reason": {"type": "string"},
                },
                "required": [
                    "article_id",
                    "evidence_type",
                    "subject_scope",
                    "safe_to_use",
                    "reason",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["article_evidence"],
    "additionalProperties": False,
}
