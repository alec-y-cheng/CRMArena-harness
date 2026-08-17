"""Structured-output schemas for named_entity_disambiguation."""

from typing import Any, Dict


NED_EXTRACTION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "entity_phrase": {"type": "string"},
        "product_terms": {"type": "array", "items": {"type": "string"}},
        "date_expression": {"type": "string"},
        "period": {
            "type": "string",
            "enum": ["day", "week", "month", "quarter", "unknown"],
        },
        "interval_count": {"type": "integer"},
        "exact_purchase_date": {"type": "string"},
        "attributes": {"type": "array", "items": {"type": "string"}},
        "clarification_needed": {"type": "boolean"},
        "clarification_requirements": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "entity_phrase",
        "product_terms",
        "date_expression",
        "period",
        "interval_count",
        "exact_purchase_date",
        "attributes",
        "clarification_needed",
        "clarification_requirements",
    ],
    "additionalProperties": False,
}


NED_CANDIDATE_SELECTION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "selected_product_id": {"type": ["string", "null"]},
        "evidence": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low", "unknown"]},
        "ambiguous": {"type": "boolean"},
        "clarification_requirements": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "selected_product_id",
        "evidence",
        "confidence",
        "ambiguous",
        "clarification_requirements",
    ],
    "additionalProperties": False,
}


NED_CLARIFICATION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "question": {"type": "string"},
    },
    "required": ["question"],
    "additionalProperties": False,
}
