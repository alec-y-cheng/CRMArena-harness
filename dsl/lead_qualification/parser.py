"""Parsers and validators for lead qualification DSL outputs."""

from decimal import Decimal, InvalidOperation
import json
import re
from typing import Any, Dict, Mapping, Optional

from dsl.lead_qualification.actions import (
    BANT_FACTORS,
    BANT_STATUSES,
    BANTState,
    FactorEvidence,
    SELLER_TIMELINE_COMMITMENT_STRENGTHS,
    TimelinePolicyJudgment,
)


class BANTParseError(ValueError):
    pass


def parse_bant_json(text: str) -> BANTState:
    """Parse strict BANT extraction JSON into a validated BANTState."""

    content = _extract_json_text(text or "")
    if not content:
        raise BANTParseError("No JSON object found in extractor output")

    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise BANTParseError(f"Malformed JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise BANTParseError("Extractor output must be a JSON object")

    state = BANTState()
    for factor in BANT_FACTORS:
        raw_factor = payload.get(factor)
        if not isinstance(raw_factor, Mapping):
            raise BANTParseError(f"Missing or invalid factor object: {factor}")
        status = raw_factor.get("status")
        if status not in BANT_STATUSES:
            raise BANTParseError(f"Invalid status for {factor}: {status}")
        evidence = raw_factor.get("evidence", "")
        if evidence is None:
            evidence = ""
        if not isinstance(evidence, str):
            raise BANTParseError(f"Invalid evidence for {factor}: expected string")
        state.factors[factor] = FactorEvidence(status=status, evidence=evidence)

    state.product_names = _string_list(payload.get("product_names", []), "product_names")
    state.quantities = _quantity_map(payload.get("quantities", {}))
    state.budget_amount = _optional_decimal(payload.get("budget_amount"), "budget_amount")
    state.requested_timeline_days = _optional_int(
        payload.get("requested_timeline_days"),
        "requested_timeline_days",
    )
    state.client_timeline = _optional_string(payload.get("client_timeline"), "client_timeline")
    state.seller_timeline_feasibility = _optional_string(
        payload.get("seller_timeline_feasibility"),
        "seller_timeline_feasibility",
    )
    state.seller_timeline_commitment_strength = _optional_enum(
        payload.get("seller_timeline_commitment_strength"),
        "seller_timeline_commitment_strength",
        SELLER_TIMELINE_COMMITMENT_STRENGTHS,
        default="unknown",
    )
    state.total_requested_units = _infer_total_requested_units(
        state.product_names,
        state.quantities,
    )
    return state


def parse_timeline_policy_judgment_json(text: str) -> TimelinePolicyJudgment:
    """Parse strict policy/timeline judgment JSON into a validated object."""

    content = _extract_json_text(text or "")
    if not content:
        raise BANTParseError("No JSON object found in timeline policy output")

    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise BANTParseError(f"Malformed timeline policy JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise BANTParseError("Timeline policy output must be a JSON object")
    if "required_installation_days" not in payload:
        raise BANTParseError("Missing required_installation_days")
    if "policy_evidence" not in payload:
        raise BANTParseError("Missing policy_evidence")

    raw_timeline = payload.get("Timeline")
    if not isinstance(raw_timeline, Mapping):
        raise BANTParseError("Missing or invalid Timeline object")
    status = raw_timeline.get("status")
    if status not in BANT_STATUSES:
        raise BANTParseError(f"Invalid Timeline status: {status}")
    evidence = raw_timeline.get("evidence", "")
    if evidence is None:
        evidence = ""
    if not isinstance(evidence, str):
        raise BANTParseError("Invalid Timeline evidence: expected string")

    return TimelinePolicyJudgment(
        required_installation_days=_optional_int(
            payload.get("required_installation_days"),
            "required_installation_days",
        ),
        policy_evidence=_optional_string(payload.get("policy_evidence"), "policy_evidence"),
        timeline_status=status,
        timeline_evidence=evidence,
    )


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


def _string_list(value: Any, field_name: str):
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise BANTParseError(f"{field_name} must be a list")
    result = []
    for item in value:
        if not isinstance(item, str):
            raise BANTParseError(f"{field_name} items must be strings")
        cleaned = " ".join(item.split())
        if cleaned:
            result.append(cleaned)
    return result


def _quantity_map(value: Any) -> Dict[str, int]:
    if value in (None, ""):
        return {}
    if not isinstance(value, Mapping):
        raise BANTParseError("quantities must be an object")
    result = {}
    for name, quantity in value.items():
        if not isinstance(name, str):
            raise BANTParseError("quantity names must be strings")
        try:
            parsed_quantity = int(quantity)
        except (TypeError, ValueError) as exc:
            raise BANTParseError(f"Invalid quantity for {name}: {quantity}") from exc
        if parsed_quantity <= 0:
            raise BANTParseError(f"Invalid quantity for {name}: {quantity}")
        result[" ".join(name.split())] = parsed_quantity
    return result


def _optional_decimal(value: Any, field_name: str) -> Optional[Decimal]:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace("$", "").replace(",", ""))
    except (InvalidOperation, ValueError) as exc:
        raise BANTParseError(f"Invalid decimal {field_name}: {value}") from exc


def _optional_int(value: Any, field_name: str) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise BANTParseError(f"Invalid integer {field_name}: {value}") from exc
    if parsed <= 0:
        raise BANTParseError(f"Invalid integer {field_name}: {value}")
    return parsed


def _optional_string(value: Any, field_name: str) -> str:
    if value in (None, ""):
        return ""
    if not isinstance(value, str):
        raise BANTParseError(f"{field_name} must be a string")
    return " ".join(value.split())


def _optional_enum(
    value: Any,
    field_name: str,
    allowed_values: Any,
    default: str = "unknown",
) -> str:
    if value in (None, ""):
        return default
    if not isinstance(value, str):
        raise BANTParseError(f"{field_name} must be a string")
    normalized = value.strip().lower()
    if normalized not in allowed_values:
        raise BANTParseError(f"Invalid {field_name}: {value}")
    return normalized


def _infer_total_requested_units(product_names, quantities: Mapping[str, int]) -> Optional[int]:
    if quantities:
        return sum(int(quantity) for quantity in quantities.values())
    if len(product_names) > 1:
        return len(product_names)
    return None
