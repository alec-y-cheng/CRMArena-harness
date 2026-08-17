"""Internal workflow router for the generic symbolic runtime."""

import json
import re
from typing import Any, Callable, Dict, List, Optional


ModelExtractor = Callable[[List[Dict[str, str]]], str]

INTERNAL_WORKFLOW_ROUTES = (
    "wrong_stage_rectification",
    "policy_violation_identification",
    "clarify",
    "unsupported",
)

INTERNAL_ROUTER_SYSTEM_PROMPT = """\
Route an internal CRM user request to one supported WorkflowSpec.

Supported workflows:
- wrong_stage_rectification: verify whether an Opportunity stage is appropriate
  and return the correct stage label if needed.
- policy_violation_identification: verify whether a Case breaches or implicates
  a policy/solution article and return a Knowledge__kav article Id or None.
- clarify: the request is internal and likely supported, but the target record
  or task intent is not clear enough to choose one workflow.
- unsupported: the request is internal but does not fit either supported
  workflow.

Use only the user-visible conversation and request text. Do not write SOQL/SOSL.
Return exactly one JSON object and no prose.
"""


class InternalRouteParseError(ValueError):
    pass


class InternalWorkflowRoute:
    def __init__(
        self,
        route: str,
        confidence: str = "unknown",
        target_record_id: str = "",
        clarification_requirements: Optional[List[str]] = None,
        reason: str = "",
    ):
        self.route = route
        self.confidence = confidence
        self.target_record_id = target_record_id
        self.clarification_requirements = clarification_requirements or []
        self.reason = reason

    def as_dict(self) -> Dict[str, Any]:
        return {
            "route": self.route,
            "confidence": self.confidence,
            "target_record_id": self.target_record_id,
            "clarification_requirements": list(self.clarification_requirements),
            "reason": self.reason,
        }


class InternalWorkflowRouter:
    """LLM-backed router over the small internal WorkflowSpec menu."""

    def __init__(self, model_extractor: ModelExtractor, max_retries: int = 1):
        self.model_extractor = model_extractor
        self.max_retries = max_retries
        self.last_info: Dict[str, Any] = {}

    def route(self, task_query: str, conversation_text: str) -> InternalWorkflowRoute:
        self.last_info = {"router_outputs": [], "router_parse_errors": [], "model_calls": 0}
        messages = [
            {"role": "system", "content": INTERNAL_ROUTER_SYSTEM_PROMPT},
            {"role": "user", "content": build_internal_router_prompt(task_query, conversation_text)},
        ]
        last_error = None
        for attempt in range(self.max_retries + 1):
            output = self.model_extractor(messages)
            self.last_info["model_calls"] += 1
            self.last_info["router_outputs"].append({"attempt": attempt + 1, "output": output})
            try:
                route = parse_internal_workflow_route_json(output)
                route = _heuristic_internal_route_fallback(route, task_query, conversation_text)
                self.last_info["route"] = route.as_dict()
                return route
            except InternalRouteParseError as exc:
                last_error = str(exc)
                self.last_info["router_parse_errors"].append({"attempt": attempt + 1, "error": last_error})
                messages.append({"role": "assistant", "content": output})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Invalid internal route JSON: {}. Retry with exactly one JSON "
                            "object and no prose. Use only supported route and confidence labels."
                        ).format(last_error),
                    }
                )
        fallback = _heuristic_internal_route(task_query, conversation_text)
        fallback.reason = "Router failed to produce valid JSON: {}; {}".format(last_error or "unknown error", fallback.reason)
        self.last_info["route"] = fallback.as_dict()
        return fallback


def build_internal_router_prompt(task_query: str, conversation_text: str) -> str:
    return """\
Original task/request text:
{task_query}

User-visible conversation:
{conversation_text}

Return JSON:
{{
  "route": "wrong_stage_rectification|policy_violation_identification|clarify|unsupported",
  "confidence": "high|medium|low|unknown",
  "target_record_id": "Salesforce record Id if present, otherwise empty string",
  "clarification_requirements": [],
  "reason": "brief rationale"
}}
""".format(
        task_query=(task_query or "").strip(),
        conversation_text=(conversation_text or "").strip(),
    )


def parse_internal_workflow_route_json(text: str) -> InternalWorkflowRoute:
    data = _loads_object(text)
    _require_keys(data, ["route", "confidence", "target_record_id", "clarification_requirements", "reason"])
    route = _route(data["route"])
    confidence = _confidence(data["confidence"])
    target_record_id = _as_string(data["target_record_id"], "target_record_id")
    clarification_requirements = _string_list(data["clarification_requirements"], "clarification_requirements")
    if route == "clarify" and not clarification_requirements:
        raise InternalRouteParseError("route clarify requires clarification_requirements")
    return InternalWorkflowRoute(
        route=route,
        confidence=confidence,
        target_record_id=target_record_id,
        clarification_requirements=clarification_requirements,
        reason=_as_string(data["reason"], "reason"),
    )


def _heuristic_internal_route_fallback(
    route: InternalWorkflowRoute,
    task_query: str,
    conversation_text: str,
) -> InternalWorkflowRoute:
    if route.route in ("wrong_stage_rectification", "policy_violation_identification"):
        return route
    heuristic = _heuristic_internal_route(task_query, conversation_text)
    if heuristic.route in ("wrong_stage_rectification", "policy_violation_identification"):
        route.reason = "{}; heuristic fallback suggested {}".format(route.reason, heuristic.route)
        return heuristic
    return route


def _heuristic_internal_route(task_query: str, conversation_text: str) -> InternalWorkflowRoute:
    text = " ".join([task_query or "", conversation_text or ""]).lower()
    opportunity_id = _extract_salesforce_id(task_query + " " + conversation_text, "006")
    case_id = _extract_salesforce_id(task_query + " " + conversation_text, "500")
    if opportunity_id or any(term in text for term in ("opportunity", "stage name", "stage label", "current stage")):
        return InternalWorkflowRoute(
            route="wrong_stage_rectification",
            confidence="medium",
            target_record_id=opportunity_id,
            clarification_requirements=[] if opportunity_id else ["Opportunity ID"],
            reason="Request concerns Opportunity stage verification.",
        )
    if case_id or any(term in text for term in ("case id", "policy", "breach", "violation", "knowledge article", "contravened")):
        return InternalWorkflowRoute(
            route="policy_violation_identification",
            confidence="medium",
            target_record_id=case_id,
            clarification_requirements=[] if case_id else ["Case ID"],
            reason="Request concerns policy violation identification for a Case.",
        )
    return InternalWorkflowRoute(
        route="unsupported",
        confidence="low",
        target_record_id="",
        clarification_requirements=[],
        reason="Request does not match a supported internal workflow.",
    )


def _loads_object(text: str) -> Dict[str, Any]:
    try:
        value = json.loads(_extract_json_object(text))
    except ValueError as exc:
        raise InternalRouteParseError(str(exc))
    if not isinstance(value, dict):
        raise InternalRouteParseError("Expected JSON object")
    return value


def _extract_json_object(text: str) -> str:
    cleaned = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL | re.IGNORECASE)
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if fenced:
        return fenced.group(1)
    start = cleaned.find("{")
    if start < 0:
        raise InternalRouteParseError("No JSON object found")
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
    raise InternalRouteParseError("Unbalanced JSON object")


def _require_keys(data: Dict[str, Any], keys: List[str]) -> None:
    missing = [key for key in keys if key not in data]
    if missing:
        raise InternalRouteParseError("Missing required keys: {}".format(", ".join(missing)))


def _route(value: Any) -> str:
    route = _as_string(value, "route")
    if route not in INTERNAL_WORKFLOW_ROUTES:
        raise InternalRouteParseError("Invalid route: {}".format(value))
    return route


def _confidence(value: Any) -> str:
    confidence = _as_string(value, "confidence").lower()
    if confidence not in ("high", "medium", "low", "unknown"):
        raise InternalRouteParseError("Invalid confidence: {}".format(value))
    return confidence


def _as_string(value: Any, field: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise InternalRouteParseError("{} must be a string".format(field))
    return value.strip()


def _string_list(value: Any, field: str) -> List[str]:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            try:
                decoded = json.loads(stripped)
            except ValueError:
                decoded = None
            if isinstance(decoded, list):
                value = decoded
        elif not stripped:
            return []
    if not isinstance(value, list):
        raise InternalRouteParseError("{} must be a list".format(field))
    out = []
    for item in value:
        if not isinstance(item, str):
            raise InternalRouteParseError("{} items must be strings".format(field))
        text = item.strip()
        if text:
            out.append(text)
    return out


def _extract_salesforce_id(text: str, prefix: str = "") -> str:
    if not text:
        return ""
    pattern = r"\b{}[A-Za-z0-9]{{12}}(?:[A-Za-z0-9]{{3}})?\b".format(re.escape(prefix)) if prefix else r"\b[A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?\b"
    match = re.search(pattern, text)
    return match.group(0) if match else ""
