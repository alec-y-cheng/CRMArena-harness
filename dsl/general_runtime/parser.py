"""Strict parsers for generic runtime model outputs."""

import json
import re
from typing import Any, Dict, List

from dsl.external_facing.actions import ALLOWED_EVIDENCE_TYPES, DISALLOWED_EVIDENCE_TYPES, SUBJECT_SCOPES
from dsl.general_runtime.state import InstanceFrame


class RuntimeParseError(ValueError):
    pass


def parse_instance_frame_json(text: str) -> InstanceFrame:
    data = _normalize_instance_frame_data(_loads_object(text))
    _require_keys(data, ["workflow_id", "request_summary", "target_entities", "required_evidence_instances", "clarification_requirements"])
    return InstanceFrame(
        workflow_id=_as_string(data["workflow_id"], "workflow_id"),
        request_summary=_as_string(data["request_summary"], "request_summary"),
        target_entities=_object_list(data["target_entities"], "target_entities"),
        query_terms=_loose_string_list(data.get("query_terms", []), "query_terms"),
        product_terms=_loose_string_list(data.get("product_terms", []), "product_terms"),
        constraints=_loose_object_list(data.get("constraints", []), "constraints"),
        required_evidence_instances=_evidence_instances(data["required_evidence_instances"]),
        clarification_requirements=_loose_string_list(data["clarification_requirements"], "clarification_requirements"),
    )


def parse_answer_candidate_json(text: str, state) -> Dict[str, Any]:
    data = _loads_object(text)
    _require_keys(data, ["answer_candidate"])
    candidate = _decode_json_string(data["answer_candidate"])
    if not isinstance(candidate, dict):
        raise RuntimeParseError("answer_candidate must be an object")
    _require_keys(candidate, ["answer", "confidence", "evidence", "selected_evidence", "clarification_requirements"])
    answer = candidate.get("answer")
    if answer is None:
        answer = "None"
    if not isinstance(answer, str):
        raise RuntimeParseError("answer must be a string or null")
    confidence = _as_string(candidate["confidence"], "confidence").lower()
    if confidence not in ("high", "medium", "low", "unknown"):
        raise RuntimeParseError("Invalid confidence: {}".format(confidence))
    selected_evidence = _selected_evidence(candidate["selected_evidence"], state)
    clarification_requirements = _string_list(candidate["clarification_requirements"], "clarification_requirements")
    parsed = {
        "answer": answer.strip() or "None",
        "confidence": confidence,
        "evidence": _as_string(candidate["evidence"], "evidence"),
        "selected_evidence": selected_evidence,
        "clarification_requirements": clarification_requirements,
    }
    for key, value in candidate.items():
        if key not in parsed:
            parsed[key] = _decode_json_string(value)
    return parsed


def parse_disclosure_gate_json(text: str, state) -> Dict[str, Any]:
    data = _loads_object(text)
    _require_keys(
        data,
        [
            "safe_to_disclose",
            "recommended_action",
            "blocked_evidence_ids",
            "blocked_information",
            "reason",
        ],
    )
    safe_to_disclose = data["safe_to_disclose"]
    if not isinstance(safe_to_disclose, bool):
        raise RuntimeParseError("safe_to_disclose must be boolean")
    recommended_action = _as_string(data["recommended_action"], "recommended_action").lower()
    if recommended_action not in ("answer", "refuse"):
        raise RuntimeParseError("recommended_action must be answer or refuse")
    allowed_selected_ids = set()
    for item in state.selected_evidence:
        evidence_id = str(item.get("evidence_id") or "")
        if evidence_id:
            allowed_selected_ids.add(evidence_id)
    blocked_evidence_ids = _string_list(data["blocked_evidence_ids"], "blocked_evidence_ids")
    unknown = [evidence_id for evidence_id in blocked_evidence_ids if evidence_id not in allowed_selected_ids]
    if unknown:
        raise RuntimeParseError(
            "blocked_evidence_ids references unselected evidence_id: {}".format(
                ", ".join(unknown)
            )
        )
    return {
        "safe_to_disclose": safe_to_disclose,
        "recommended_action": recommended_action,
        "blocked_evidence_ids": blocked_evidence_ids,
        "blocked_information": _string_list(data["blocked_information"], "blocked_information"),
        "reason": _as_string(data["reason"], "reason"),
    }


def extract_json_object(text: str) -> str:
    cleaned = _strip_thinking(text or "")
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if fenced:
        return fenced.group(1)
    start = cleaned.find("{")
    if start < 0:
        raise RuntimeParseError("No JSON object found")
    depth = 0
    in_string = False
    escaped = False
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
                return cleaned[start:index + 1]
    raise RuntimeParseError("Unbalanced JSON object")


def _loads_object(text: str) -> Dict[str, Any]:
    try:
        value = json.loads(extract_json_object(text))
    except ValueError as exc:
        raise RuntimeParseError(str(exc))
    if not isinstance(value, dict):
        raise RuntimeParseError("Expected JSON object")
    return value


def _require_keys(data: Dict[str, Any], keys: List[str]) -> None:
    missing = [key for key in keys if key not in data]
    if missing:
        raise RuntimeParseError("Missing required keys: {}".format(", ".join(missing)))


def _normalize_instance_frame_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Accept common equivalent frame shapes and normalize to InstanceFrame."""
    normalized = dict(data)
    nested_sources = []
    for key in ("instance_data", "instance_frame", "instance_contract", "input", "action_input", "state", "response", "payload", "data"):
        value = _decode_json_string(data.get(key))
        if isinstance(value, dict):
            nested_sources.append(value)
    action_plan = _decode_json_string(data.get("action_plan"))
    if isinstance(action_plan, dict):
        action_params = _decode_json_string(
            action_plan.get("action_params") or action_plan.get("arguments") or action_plan.get("parameters")
        )
        if isinstance(action_params, dict):
            nested_sources.append(action_params)

    def first_value(*keys):
        for key in keys:
            if key in normalized and normalized[key] not in (None, "", [], {}):
                return normalized[key]
        for source in nested_sources:
            for key in keys:
                if key in source and source[key] not in (None, "", [], {}):
                    return source[key]
        return None

    workflow_id = first_value("workflow_id")
    if workflow_id is not None:
        normalized["workflow_id"] = str(workflow_id)

    request_summary = first_value("request_summary", "summary", "user_intent", "query")
    if request_summary is not None:
        normalized["request_summary"] = str(request_summary)

    target_entities = _decode_json_string(first_value("target_entities", "entities"))
    if target_entities is None:
        target_entities = _entities_from_terms(first_value("product_terms", "query_terms", "search_terms"))
    if isinstance(target_entities, list):
        normalized["target_entities"] = [
            dict(item) if isinstance(item, dict) else {"surface_text": str(item)}
            for item in target_entities
            if isinstance(item, dict) or str(item or "").strip()
        ]
    else:
        normalized["target_entities"] = []

    product_terms = _decode_json_string(first_value("product_terms", "product_term", "product_name", "item_description"))
    if product_terms is not None:
        normalized["product_terms"] = product_terms

    query_terms = _decode_json_string(first_value("query_terms", "search_terms", "query"))
    if query_terms is not None:
        normalized["query_terms"] = query_terms

    constraints = _decode_json_string(first_value("constraints"))
    if not isinstance(constraints, list):
        purchase_window = _decode_json_string(first_value("purchase_date_window", "date_window"))
        constraints = []
        if isinstance(purchase_window, dict):
            window = dict(purchase_window)
            window.setdefault("type", "purchase_date_window")
            constraints.append(window)
    normalized["constraints"] = constraints if isinstance(constraints, list) else []

    required_evidence_instances = _decode_json_string(first_value("required_evidence_instances", "evidence_required"))
    normalized["required_evidence_instances"] = (
        required_evidence_instances if isinstance(required_evidence_instances, list) else []
    )

    clarification_requirements = _decode_json_string(first_value("clarification_requirements", "missing_fields"))
    normalized["clarification_requirements"] = clarification_requirements if clarification_requirements is not None else []
    return normalized


def _entities_from_terms(value: Any) -> List[Dict[str, Any]]:
    terms = _coerce_string_values(value)
    return [{"surface_text": term} for term in terms]


def _as_string(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise RuntimeParseError("{} must be a string".format(field))
    return value.strip()


def _string_list(value: Any, field: str) -> List[str]:
    value = _decode_json_string(value)
    if not isinstance(value, list):
        raise RuntimeParseError("{} must be a list".format(field))
    out = []
    for item in value:
        if not isinstance(item, str):
            raise RuntimeParseError("{} items must be strings".format(field))
        text = item.strip()
        if text:
            out.append(text)
    return out


def _loose_string_list(value: Any, field: str) -> List[str]:
    value = _decode_json_string(value)
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        raise RuntimeParseError("{} must be a list or string".format(field))
    return _coerce_string_values(value)


def _coerce_string_values(value: Any) -> List[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        return []
    out = []
    for item in value:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = str(
                item.get("surface_text")
                or item.get("name")
                or item.get("description")
                or item.get("reference")
                or ""
            ).strip()
        else:
            text = str(item or "").strip()
        if text:
            out.append(text)
    return out


def _object_list(value: Any, field: str) -> List[Dict[str, Any]]:
    value = _decode_json_string(value)
    if not isinstance(value, list):
        raise RuntimeParseError("{} must be a list".format(field))
    out = []
    for item in value:
        if not isinstance(item, dict):
            raise RuntimeParseError("{} items must be objects".format(field))
        out.append(dict(item))
    return out


def _loose_object_list(value: Any, field: str) -> List[Dict[str, Any]]:
    value = _decode_json_string(value)
    if not isinstance(value, list):
        raise RuntimeParseError("{} must be a list".format(field))
    out = []
    for item in value:
        if isinstance(item, dict):
            out.append(dict(item))
        elif isinstance(item, str) and item.strip():
            out.append({"value": item.strip()})
    return out


def _evidence_instances(value: Any) -> List[Dict[str, Any]]:
    items = _object_list(value, "required_evidence_instances")
    allowed = set(ALLOWED_EVIDENCE_TYPES + DISALLOWED_EVIDENCE_TYPES)
    out = []
    for item in items:
        if "reason" not in item:
            item["reason"] = "selected by instance framing"
        required = [key for key in ("requirement", "evidence_type", "subject_scope") if key not in item]
        if required:
            continue
        if item["evidence_type"] not in allowed:
            continue
        if item["subject_scope"] not in SUBJECT_SCOPES:
            continue
        out.append(item)
    return out


def _selected_evidence(value: Any, state) -> List[Dict[str, Any]]:
    items = _object_list(value, "selected_evidence")
    allowed_ids = set()
    for item in state.evidence_items:
        if item.evidence_id:
            allowed_ids.add(item.evidence_id)
    allowed_types = set(ALLOWED_EVIDENCE_TYPES + DISALLOWED_EVIDENCE_TYPES)
    out = []
    for item in items:
        _require_keys(item, ["evidence_id", "evidence_type", "subject_scope", "safe_to_use", "reason"])
        evidence_id = _as_string(item["evidence_id"], "evidence_id")
        if evidence_id and evidence_id not in allowed_ids:
            raise RuntimeParseError("selected_evidence references unknown evidence_id: {}".format(evidence_id))
        evidence_type = _as_string(item["evidence_type"], "evidence_type")
        if evidence_type not in allowed_types:
            raise RuntimeParseError("Invalid selected evidence_type: {}".format(evidence_type))
        subject_scope = _as_string(item["subject_scope"], "subject_scope")
        if subject_scope not in SUBJECT_SCOPES:
            raise RuntimeParseError("Invalid selected subject_scope: {}".format(subject_scope))
        safe_to_use = item["safe_to_use"]
        if not isinstance(safe_to_use, bool):
            raise RuntimeParseError("safe_to_use must be boolean")
        out.append(
            {
                "evidence_id": evidence_id,
                "evidence_type": evidence_type,
                "subject_scope": subject_scope,
                "safe_to_use": safe_to_use,
                "reason": _as_string(item["reason"], "reason"),
            }
        )
    return out


def _strip_thinking(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)


def _decode_json_string(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or text[0] not in "[{":
        return value
    try:
        return json.loads(text)
    except ValueError:
        return value
