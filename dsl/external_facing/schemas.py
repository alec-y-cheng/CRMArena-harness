"""Structured-output schemas for external-facing router prompts."""

from typing import Any, Dict

from dsl.external_facing.actions import (
    ALLOWED_EVIDENCE_TYPES,
    DISALLOWED_EVIDENCE_TYPES,
    EXPECTED_ACTIONS,
    EXTERNAL_ROUTES,
    SUBJECT_SCOPES,
)


EXTERNAL_EVIDENCE_VALUES = list(ALLOWED_EVIDENCE_TYPES + DISALLOWED_EVIDENCE_TYPES)


EXTERNAL_REQUEST_ROUTE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "request_type": {"type": "string"},
        "route": {"type": "string", "enum": list(EXTERNAL_ROUTES)},
        "expected_actions": {"type": "array", "items": {"type": "string", "enum": list(EXPECTED_ACTIONS)}},
        "evidence_required": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "evidence_type": {"type": "string", "enum": EXTERNAL_EVIDENCE_VALUES},
                    "subject_scope": {"type": "string", "enum": list(SUBJECT_SCOPES)},
                    "reason": {"type": "string"},
                },
                "required": ["evidence_type", "subject_scope", "reason"],
                "additionalProperties": False,
            },
        },
        "subject_scope": {"type": "string", "enum": list(SUBJECT_SCOPES)},
        "clarification_needed": {"type": "boolean"},
        "clarification_requirements": {"type": "array", "items": {"type": "string"}},
        "disallowed_information": {"type": "array", "items": {"type": "string", "enum": list(DISALLOWED_EVIDENCE_TYPES)}},
        "reason": {"type": "string"},
    },
    "required": [
        "request_type",
        "route",
        "expected_actions",
        "evidence_required",
        "subject_scope",
        "clarification_needed",
        "clarification_requirements",
        "disallowed_information",
        "reason",
    ],
    "additionalProperties": False,
}
