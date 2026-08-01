"""Parsers and validators for case-routing DSL model outputs."""

import json
import re
from typing import Any, List, Mapping, Optional

from dsl.case_routing.actions import CaseRoutingSlots, CandidateSelection


SELECTION_CONFIDENCES = ("high", "medium", "low", "unknown")


class CaseRoutingParseError(ValueError):
    pass


def parse_case_routing_slots_json(text: str) -> CaseRoutingSlots:
    payload = _load_json_object(text, "case routing slots")
    return CaseRoutingSlots(
        case_subject=_optional_string(payload.get("case_subject"), "case_subject"),
        case_description=_optional_string(payload.get("case_description"), "case_description"),
        issue_summary=_optional_string(payload.get("issue_summary"), "issue_summary"),
        issue_search_terms=_string_list(payload.get("issue_search_terms"), "issue_search_terms"),
        product_search_terms=_string_list(
            payload.get("product_search_terms"),
            "product_search_terms",
        ),
    )


def parse_candidate_selection_json(
    text: str,
    allowed_ids: Optional[Any] = None,
) -> CandidateSelection:
    payload = _load_json_object(text, "candidate selection")
    allowed = set(allowed_ids or [])
    selected = _optional_id(payload.get("selected_id"), "selected_id")
    if selected and allowed and selected not in allowed:
        raise CaseRoutingParseError("selected_id was not in candidate ids")
    confidence = _enum(payload.get("confidence"), "confidence", SELECTION_CONFIDENCES)
    rationale = _optional_string(payload.get("rationale"), "rationale")
    return CandidateSelection(selected, confidence, rationale)


def _load_json_object(text: str, label: str) -> Mapping[str, Any]:
    content = _extract_json_text(text or "")
    if not content:
        raise CaseRoutingParseError("No JSON object found in {}".format(label))
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise CaseRoutingParseError("Malformed {} JSON: {}".format(label, exc)) from exc
    if not isinstance(payload, Mapping):
        raise CaseRoutingParseError("{} output must be a JSON object".format(label))
    return payload


def _extract_json_text(text: str) -> str:
    stripped = _strip_think_blocks(text).strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    decoder = json.JSONDecoder()
    candidates = []
    for match in re.finditer(r"\{", stripped):
        try:
            payload, end = decoder.raw_decode(stripped[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            candidates.append(stripped[match.start() : match.start() + end])
    if not candidates:
        return ""
    return max(candidates, key=len)


def _strip_think_blocks(text: str) -> str:
    return re.sub(r"<think\b[^>]*>.*?</think>", "", text or "", flags=re.IGNORECASE | re.DOTALL)


def _string_list(value: Any, field_name: str) -> List[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise CaseRoutingParseError("{} must be a list".format(field_name))
    result = []
    for item in value:
        if not isinstance(item, str):
            raise CaseRoutingParseError("{} items must be strings".format(field_name))
        cleaned = " ".join(item.split())
        if cleaned:
            result.append(cleaned)
    return result


def _optional_string(value: Any, field_name: str) -> str:
    if value in (None, ""):
        return ""
    if not isinstance(value, str):
        raise CaseRoutingParseError("{} must be a string".format(field_name))
    return " ".join(value.split())


def _optional_id(value: Any, field_name: str) -> Optional[str]:
    if value in (None, "", "None"):
        return None
    if not isinstance(value, str):
        raise CaseRoutingParseError("{} must be a string or null".format(field_name))
    return value.strip()


def _enum(value: Any, field_name: str, allowed: Any) -> str:
    if not isinstance(value, str):
        raise CaseRoutingParseError("{} must be a string".format(field_name))
    if value not in allowed:
        raise CaseRoutingParseError("{} must be one of {}".format(field_name, allowed))
    return value
