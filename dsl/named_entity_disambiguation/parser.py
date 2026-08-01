"""Parsers for named_entity_disambiguation DSL outputs."""

import json
import re
from typing import Any, List

from dsl.named_entity_disambiguation.actions import (
    PERIOD_UNITS,
    NEDCandidateSelection,
    NEDExtraction,
    sanitize_id,
)


class NamedEntityDisambiguationParseError(ValueError):
    pass


def parse_ned_extraction_json(text: str) -> NEDExtraction:
    """Parse strict entity/date/product slot JSON."""
    data = _loads_object(text)
    _require_keys(
        data,
        [
            "entity_phrase",
            "product_terms",
            "date_expression",
            "period",
            "interval_count",
            "exact_purchase_date",
            "attributes",
            "clarification_needed",
            "missing_information",
        ],
    )
    return NEDExtraction(
        entity_phrase=_as_string(data["entity_phrase"], "entity_phrase"),
        product_terms=_string_list(data["product_terms"], "product_terms"),
        date_expression=_as_string(data["date_expression"], "date_expression"),
        period=validate_period(data["period"]),
        interval_count=_as_int(data["interval_count"], "interval_count"),
        exact_purchase_date=_as_string(data["exact_purchase_date"], "exact_purchase_date"),
        attributes=_string_list(data["attributes"], "attributes"),
        clarification_needed=_as_bool(data["clarification_needed"], "clarification_needed"),
        missing_information=_string_list(data["missing_information"], "missing_information"),
    )


def parse_ned_candidate_selection_json(
    text: str,
    allowed_product_ids: List[str],
) -> NEDCandidateSelection:
    """Parse selected Product2.Id and validate against eligible purchases."""
    data = _loads_object(text)
    _require_keys(
        data,
        ["selected_product_id", "evidence", "confidence", "ambiguous", "missing_information"],
    )
    selected_product_id = _optional_product_id(data["selected_product_id"])
    allowed = set(allowed_product_ids)
    if selected_product_id and selected_product_id not in allowed:
        raise NamedEntityDisambiguationParseError(
            "selected_product_id was not in eligible purchase records: {}".format(
                selected_product_id
            )
        )
    ambiguous = _as_bool(data["ambiguous"], "ambiguous")
    missing_information = _string_list(data["missing_information"], "missing_information")
    if ambiguous and selected_product_id:
        raise NamedEntityDisambiguationParseError(
            "selected_product_id must be null when ambiguous is true"
        )
    return NEDCandidateSelection(
        selected_product_id=selected_product_id,
        evidence=_as_string(data["evidence"], "evidence"),
        confidence=validate_confidence(data["confidence"]),
        ambiguous=ambiguous,
        missing_information=missing_information,
    )


def parse_ned_clarification_json(text: str) -> str:
    """Parse one customer-facing clarification question."""
    data = _loads_object(text)
    _require_keys(data, ["question"])
    question = _as_string(data["question"], "question")
    if not question:
        raise NamedEntityDisambiguationParseError("question cannot be empty")
    if "\n" in question:
        raise NamedEntityDisambiguationParseError("question must be one line")
    if not question.endswith("?"):
        raise NamedEntityDisambiguationParseError("question must end with a question mark")
    lowered = question.lower()
    forbidden = ("salesforce", "json", "schema", "deterministic", "internal system")
    if any(term in lowered for term in forbidden):
        raise NamedEntityDisambiguationParseError(
            "question mentions internal implementation details"
        )
    return question


def extract_json_object(text: str) -> str:
    """Extract the largest JSON object from noisy model output."""
    cleaned = _strip_thinking(text or "")
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if fenced:
        return fenced.group(1)

    start = cleaned.find("{")
    if start < 0:
        raise NamedEntityDisambiguationParseError("No JSON object found")

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
        raise NamedEntityDisambiguationParseError("Unbalanced JSON object")
    return best


def validate_confidence(value: Any) -> str:
    """Validate selection confidence label."""
    if not isinstance(value, str):
        raise NamedEntityDisambiguationParseError("confidence must be a string")
    normalized = value.strip().lower()
    if normalized not in ("high", "medium", "low", "unknown"):
        raise NamedEntityDisambiguationParseError("Invalid confidence: {}".format(value))
    return normalized


def validate_period(value: Any) -> str:
    if not isinstance(value, str):
        raise NamedEntityDisambiguationParseError("period must be a string")
    normalized = value.strip().lower()
    if normalized not in PERIOD_UNITS:
        raise NamedEntityDisambiguationParseError("Invalid period: {}".format(value))
    return normalized


def _loads_object(text: str) -> dict:
    try:
        parsed = json.loads(extract_json_object(text))
    except json.JSONDecodeError as exc:
        raise NamedEntityDisambiguationParseError("Invalid JSON: {}".format(exc))
    if not isinstance(parsed, dict):
        raise NamedEntityDisambiguationParseError("Expected a JSON object")
    return parsed


def _require_keys(data: dict, keys: List[str]) -> None:
    missing = [key for key in keys if key not in data]
    if missing:
        raise NamedEntityDisambiguationParseError("Missing keys: {}".format(", ".join(missing)))


def _as_string(value: Any, field: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise NamedEntityDisambiguationParseError("{} must be a string".format(field))
    return value.strip()


def _as_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise NamedEntityDisambiguationParseError("{} must be a boolean".format(field))
    return value


def _as_int(value: Any, field: str) -> int:
    if not isinstance(value, int):
        raise NamedEntityDisambiguationParseError("{} must be an integer".format(field))
    if value < 0:
        raise NamedEntityDisambiguationParseError("{} must be non-negative".format(field))
    return value


def _string_list(value: Any, field: str) -> List[str]:
    if not isinstance(value, list):
        raise NamedEntityDisambiguationParseError("{} must be a list".format(field))
    out = []
    for item in value:
        if not isinstance(item, str):
            raise NamedEntityDisambiguationParseError(
                "{} must contain only strings".format(field)
            )
        cleaned = item.strip()
        if cleaned:
            out.append(cleaned)
    return out


def _optional_product_id(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise NamedEntityDisambiguationParseError("selected_product_id must be a string or null")
    cleaned = value.strip()
    if not cleaned or cleaned.lower() == "none":
        return ""
    safe = sanitize_id(cleaned)
    if not safe:
        raise NamedEntityDisambiguationParseError(
            "selected_product_id is not a Salesforce id: {}".format(cleaned)
        )
    return safe


def _strip_thinking(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
