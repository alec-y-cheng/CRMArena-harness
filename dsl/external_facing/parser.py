"""Parsers for external-facing router and gate model outputs."""

import json
import re
from typing import Any, List, Optional

from dsl.external_facing.actions import (
    ALLOWED_EVIDENCE_TYPES,
    DISALLOWED_EVIDENCE_TYPES,
    EXPECTED_ACTIONS,
    EXTERNAL_ROUTES,
    SUBJECT_SCOPES,
    ExternalRequestRoute,
)


class ExternalFacingParseError(ValueError):
    pass


def parse_external_request_route_json(text: str) -> ExternalRequestRoute:
    """Parse strict router JSON into an ExternalRequestRoute."""
    data = _loads_object(text)
    _require_keys(
        data,
        [
            "request_type",
            "route",
            "expected_actions",
            "evidence_required",
            "subject_scope",
            "clarification_needed",
            "missing_information",
            "disallowed_information",
            "reason",
        ],
    )
    route = validate_route(data["route"])
    subject_scope = validate_subject_scope(data["subject_scope"])
    expected_actions = _action_list(data["expected_actions"], "expected_actions")
    evidence_required = _evidence_required_list(
        data["evidence_required"],
        "evidence_required",
    )
    disallowed_information = _evidence_list(
        data["disallowed_information"],
        "disallowed_information",
    )
    invalid_disallowed = [
        label for label in disallowed_information if label not in DISALLOWED_EVIDENCE_TYPES
    ]
    if invalid_disallowed:
        raise ExternalFacingParseError(
            "disallowed_information contains allowed evidence types: {}".format(
                ", ".join(invalid_disallowed)
            )
        )
    derived_disallowed = []
    for item in evidence_required:
        if item["evidence_type"] in DISALLOWED_EVIDENCE_TYPES:
            derived_disallowed.append(item["evidence_type"])
        elif item["subject_scope"] in ("other_customer", "internal_company"):
            derived_disallowed.append("unknown")
    derived_disallowed = sorted(set(derived_disallowed))
    if not disallowed_information:
        disallowed_information = derived_disallowed
    clarification_needed = _as_bool(
        data["clarification_needed"],
        "clarification_needed",
    )
    missing_information = _string_list(
        data["missing_information"],
        "missing_information",
    )
    if route == "clarify":
        if not clarification_needed:
            raise ExternalFacingParseError(
                "route clarify requires clarification_needed=true"
            )
        if not missing_information:
            raise ExternalFacingParseError(
                "route clarify requires missing_information"
            )
    if clarification_needed and route != "clarify":
        raise ExternalFacingParseError(
            "clarification_needed=true requires route clarify"
        )
    if route == "refuse" and not disallowed_information:
        raise ExternalFacingParseError("route refuse requires disallowed_information")
    if route in ("knowledge_qa", "named_entity_disambiguation") and disallowed_information:
        raise ExternalFacingParseError(
            "allowed task routes cannot include disallowed_information"
        )
    if derived_disallowed:
        if route != "refuse":
            raise ExternalFacingParseError(
                "evidence_required contains disallowed evidence but route is not refuse"
            )
    return ExternalRequestRoute(
        request_type=_as_string(data["request_type"], "request_type") or "unknown",
        route=route,
        expected_actions=expected_actions,
        evidence_required=evidence_required,
        subject_scope=subject_scope,
        clarification_needed=clarification_needed,
        missing_information=missing_information,
        disallowed_information=disallowed_information,
        reason=_as_string(data["reason"], "reason"),
    )


def extract_json_object(text: str) -> str:
    """Extract the largest JSON object from noisy model output."""
    cleaned = _strip_thinking(text or "")
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if fenced:
        return fenced.group(1)

    start = cleaned.find("{")
    if start < 0:
        raise ExternalFacingParseError("No JSON object found")

    depth = 0
    in_string = False
    escaped = False
    best = None
    for index in range(start, len(cleaned)):
        char = cleaned[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                best = cleaned[start : index + 1]
                break
            if depth < 0:
                break
    if not best:
        raise ExternalFacingParseError("Unbalanced JSON object")
    return best


def validate_evidence_class(value: Any) -> str:
    """Validate one fixed evidence taxonomy label."""
    if not isinstance(value, str):
        raise ExternalFacingParseError("evidence type must be a string")
    normalized = value.strip()
    allowed = set(ALLOWED_EVIDENCE_TYPES + DISALLOWED_EVIDENCE_TYPES)
    if normalized not in allowed:
        raise ExternalFacingParseError("Invalid evidence type: {}".format(value))
    return normalized


def validate_expected_action(value: Any) -> str:
    if not isinstance(value, str):
        raise ExternalFacingParseError("expected action must be a string")
    normalized = value.strip()
    if normalized not in EXPECTED_ACTIONS:
        raise ExternalFacingParseError("Invalid expected action: {}".format(value))
    return normalized


def validate_optional_route(value: Any) -> Optional[str]:
    """Validate one external route label or return None."""
    if value is None:
        return None
    return validate_route(value)


def validate_route(value: Any) -> str:
    if not isinstance(value, str):
        raise ExternalFacingParseError("route must be a string")
    normalized = value.strip()
    if normalized not in EXTERNAL_ROUTES:
        raise ExternalFacingParseError("Invalid route: {}".format(value))
    return normalized


def validate_subject_scope(value: Any) -> str:
    if not isinstance(value, str):
        raise ExternalFacingParseError("subject_scope must be a string")
    normalized = value.strip()
    if normalized not in SUBJECT_SCOPES:
        raise ExternalFacingParseError("Invalid subject_scope: {}".format(value))
    return normalized


def _loads_object(text: str) -> dict:
    try:
        parsed = json.loads(extract_json_object(text))
    except json.JSONDecodeError as exc:
        raise ExternalFacingParseError("Invalid JSON: {}".format(exc))
    if not isinstance(parsed, dict):
        raise ExternalFacingParseError("Expected a JSON object")
    return parsed


def _require_keys(data: dict, keys: List[str]) -> None:
    missing = [key for key in keys if key not in data]
    if missing:
        raise ExternalFacingParseError("Missing keys: {}".format(", ".join(missing)))


def _action_list(value: Any, field: str) -> List[str]:
    if not isinstance(value, list):
        raise ExternalFacingParseError("{} must be a list".format(field))
    return [validate_expected_action(item) for item in value]


def _evidence_required_list(value: Any, field: str) -> List[dict]:
    if not isinstance(value, list):
        raise ExternalFacingParseError("{} must be a list".format(field))
    out = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ExternalFacingParseError("{}[{}] must be an object".format(field, index))
        _require_keys(item, ["evidence_type", "subject_scope", "reason"])
        out.append(
            {
                "evidence_type": validate_evidence_class(item["evidence_type"]),
                "subject_scope": validate_subject_scope(item["subject_scope"]),
                "reason": _as_string(item["reason"], "{}[{}].reason".format(field, index)),
            }
        )
    return out


def _as_string(value: Any, field: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ExternalFacingParseError("{} must be a string".format(field))
    return value.strip()


def _as_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ExternalFacingParseError("{} must be a boolean".format(field))
    return value


def _string_list(value: Any, field: str) -> List[str]:
    if not isinstance(value, list):
        raise ExternalFacingParseError("{} must be a list".format(field))
    out = []
    for item in value:
        if not isinstance(item, str):
            raise ExternalFacingParseError("{} must contain only strings".format(field))
        cleaned = item.strip()
        if cleaned:
            out.append(cleaned)
    return out


def _evidence_list(value: Any, field: str) -> List[str]:
    if not isinstance(value, list):
        raise ExternalFacingParseError("{} must be a list".format(field))
    out = []
    for item in value:
        out.append(validate_evidence_class(item))
    return out


def _strip_thinking(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
