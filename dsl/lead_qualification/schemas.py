"""Structured-output schemas for the lead-qualification DSL."""

from typing import Any, Dict


BANT_EXTRACTION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "Budget": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["supported", "failed", "unknown"]},
                "evidence": {"type": "string"},
            },
            "required": ["status", "evidence"],
            "additionalProperties": False,
        },
        "Authority": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["supported", "failed", "unknown"]},
                "evidence": {"type": "string"},
            },
            "required": ["status", "evidence"],
            "additionalProperties": False,
        },
        "Need": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["supported", "failed", "unknown"]},
                "evidence": {"type": "string"},
            },
            "required": ["status", "evidence"],
            "additionalProperties": False,
        },
        "Timeline": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["supported", "failed", "unknown"]},
                "evidence": {"type": "string"},
            },
            "required": ["status", "evidence"],
            "additionalProperties": False,
        },
        "product_names": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Product names explicitly discussed for the lead.",
        },
        "quantities": {
            "type": "object",
            "additionalProperties": {"type": "integer"},
            "description": "Map each product name to the explicitly requested unit count.",
        },
        "budget_amount": {
            "type": ["number", "string", "null"],
            "description": "The customer's stated budget, if explicit.",
        },
        "requested_timeline_days": {
            "type": ["integer", "null"],
            "description": (
                "Concrete duration or deadline from the customer's own timeline request. "
                "Use null when only the seller provides an installation estimate."
            ),
        },
        "client_timeline": {
            "type": "string",
            "description": "Quote or concise summary of the customer's requested timing only.",
        },
        "seller_timeline_feasibility": {
            "type": "string",
            "description": "Quote or concise summary of the seller's response about feasibility.",
        },
        "seller_timeline_commitment_strength": {
            "type": "string",
            "enum": ["strong", "generic", "none", "unknown"],
            "description": (
                "Strength of the seller's timeline feasibility statement. Use strong only for "
                "a concrete commitment to this customer's requested deadline; use generic for "
                "capability/process language or effortful but non-committal statements."
            ),
        },
    },
    "required": ["Budget", "Authority", "Need", "Timeline"],
    "additionalProperties": False,
}


TIMELINE_POLICY_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "required_installation_days": {"type": ["integer", "null"]},
        "policy_evidence": {"type": "string"},
        "Timeline": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["supported", "failed", "unknown"]},
                "evidence": {"type": "string"},
            },
            "required": ["status", "evidence"],
            "additionalProperties": False,
        },
    },
    "required": ["required_installation_days", "policy_evidence", "Timeline"],
    "additionalProperties": False,
}
