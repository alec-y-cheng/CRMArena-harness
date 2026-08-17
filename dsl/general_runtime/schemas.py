"""JSON-schema contracts for the generic symbolic runtime."""

from typing import Any, Dict

from dsl.external_facing.actions import ALLOWED_EVIDENCE_TYPES, DISALLOWED_EVIDENCE_TYPES, SUBJECT_SCOPES
from dsl.general_runtime.actions import ALL_ACTIONS

EVIDENCE_TYPES = list(ALLOWED_EVIDENCE_TYPES + DISALLOWED_EVIDENCE_TYPES)

INSTANCE_FRAME_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "workflow_id": {"type": "string"},
        "request_summary": {"type": "string"},
        "target_entities": {"type": "array", "items": {"type": "object"}},
        "query_terms": {"type": "array", "items": {"type": "string"}},
        "product_terms": {"type": "array", "items": {"type": "string"}},
        "constraints": {"type": "array", "items": {"type": "object"}},
        "required_evidence_instances": {"type": "array", "items": {"type": "object"}},
        "clarification_requirements": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["workflow_id", "request_summary", "target_entities", "required_evidence_instances", "clarification_requirements"],
    "additionalProperties": False,
}

ACTION_SELECTION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": list(ALL_ACTIONS)},
        "arguments": {"type": "object"},
        "reason": {"type": "string"},
    },
    "required": ["action", "arguments", "reason"],
    "additionalProperties": False,
}

DISCLOSURE_GATE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "safe_to_disclose": {"type": "boolean"},
        "recommended_action": {"type": "string", "enum": ["answer", "refuse"]},
        "blocked_evidence_ids": {"type": "array", "items": {"type": "string"}},
        "blocked_information": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
    },
    "required": [
        "safe_to_disclose",
        "recommended_action",
        "blocked_evidence_ids",
        "blocked_information",
        "reason",
    ],
    "additionalProperties": False,
}
