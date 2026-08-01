"""Structured-output schemas for the quote-approval DSL."""

from typing import Any, Dict

from dsl.quote_approval.prompts import QUOTE_POLICY_DIMENSIONS


QUOTE_POLICY_DIMENSION_VALUES = list(QUOTE_POLICY_DIMENSIONS)


QUOTE_POLICY_SEARCH_PLAN_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "searches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "dimension": {"type": "string", "enum": QUOTE_POLICY_DIMENSION_VALUES},
                    "terms": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string"},
                },
                "required": ["dimension", "terms", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["searches"],
    "additionalProperties": False,
}


QUOTE_ARTICLE_EVIDENCE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "selected_article_id": {"type": ["string", "null"]},
        "judgments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "article_id": {"type": "string"},
                    "dimension": {"type": "string", "enum": QUOTE_POLICY_DIMENSION_VALUES},
                    "status": {"type": "string", "enum": ["violated", "not_violated", "unknown"]},
                    "rule_summary": {"type": "string"},
                    "evidence": {"type": "string"},
                },
                "required": [
                    "article_id",
                    "dimension",
                    "status",
                    "rule_summary",
                    "evidence",
                ],
                "additionalProperties": False,
            },
        },
        "additional_searches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "dimension": {"type": "string", "enum": QUOTE_POLICY_DIMENSION_VALUES},
                    "terms": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string"},
                },
                "required": ["dimension", "terms", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["selected_article_id", "judgments", "additional_searches"],
    "additionalProperties": False,
}


QUOTE_DISCOUNT_POLICY_STRUCTURE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "article_id": {"type": "string"},
        "policy_type": {
            "type": "string",
            "enum": [
                "volume_discount",
                "discount_approval",
                "not_discount_policy",
                "unknown",
            ],
        },
        "basis": {
            "type": "string",
            "enum": ["quote_total", "total_quantity", "line_quantity", "unknown"],
        },
        "application": {
            "type": "string",
            "enum": ["expected", "maximum", "minimum", "unknown"],
        },
        "scope": {
            "type": "string",
            "enum": ["quote", "line_item", "product", "unknown"],
        },
        "tiers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "threshold": {"type": "number"},
                    "operator": {"type": "string", "enum": [">", ">=", "=", "<", "<="]},
                    "discount_percent": {"type": "number"},
                },
                "required": ["threshold", "operator", "discount_percent"],
                "additionalProperties": False,
            },
        },
        "rule_confidence": {
            "type": "string",
            "enum": ["high", "medium", "low", "unknown"],
        },
        "notes": {"type": "string"},
    },
    "required": [
        "article_id",
        "policy_type",
        "basis",
        "application",
        "scope",
        "tiers",
        "rule_confidence",
        "notes",
    ],
    "additionalProperties": False,
}
