"""Structured-output schemas for the case-routing DSL."""

from typing import Any, Dict


CASE_ROUTING_SLOT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "case_subject": {"type": "string"},
        "case_description": {"type": "string"},
        "issue_summary": {"type": "string"},
        "issue_search_terms": {"type": "array", "items": {"type": "string"}},
        "product_search_terms": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "case_subject",
        "case_description",
        "issue_summary",
        "issue_search_terms",
        "product_search_terms",
    ],
    "additionalProperties": False,
}


CASE_ROUTING_SELECTION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "selected_id": {"type": ["string", "null"]},
        "confidence": {"type": "string", "enum": ["high", "medium", "low", "unknown"]},
        "rationale": {"type": "string"},
    },
    "required": ["selected_id", "confidence", "rationale"],
    "additionalProperties": False,
}
