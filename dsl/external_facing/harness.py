"""Shared external-facing router harness skeleton."""

from typing import Any, Callable, Dict, List, Optional

from dsl.external_facing.actions import (
    ExternalRequestRoute,
    GateDecision,
    classify_external_request_prompt,
    evaluate_intended_retrieval,
    render_refusal,
    respond_to_user,
)
from dsl.external_facing.parser import (
    ExternalFacingParseError,
    parse_external_request_route_json,
)
from dsl.external_facing.prompts import EXTERNAL_REQUEST_ROUTER_SYSTEM_PROMPT


ModelExtractor = Callable[[List[Dict[str, str]]], str]


class ExternalFacingRouter:
    """Routes external-facing requests before task-specific DSL delegation."""

    def __init__(self, model_extractor: ModelExtractor, max_retries: int = 1):
        self.model_extractor = model_extractor
        self.max_retries = max_retries
        self.last_info: Dict[str, Any] = {}

    def route(self, task_query: str, conversation_text: str) -> ExternalRequestRoute:
        """Return a strict route decision over the fixed evidence/action taxonomy."""
        self.last_info = {
            "router_outputs": [],
            "router_parse_errors": [],
            "model_calls": 0,
        }
        prompt = classify_external_request_prompt(task_query, conversation_text)
        messages = [
            {"role": "system", "content": EXTERNAL_REQUEST_ROUTER_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        last_error = None
        for attempt in range(self.max_retries + 1):
            output = self.model_extractor(messages)
            self.last_info["model_calls"] += 1
            self.last_info["router_outputs"].append(
                {"attempt": attempt + 1, "output": output}
            )
            try:
                route = parse_external_request_route_json(output)
                original_route = route
                route = _route_low_confidence_to_supported_workflow(route)
                if route is not original_route:
                    self.last_info["route_before_confidence_fallback"] = original_route.as_dict()
                    self.last_info["confidence_fallback_route"] = route.as_dict()
                self.last_info["route"] = route.as_dict()
                return route
            except ExternalFacingParseError as exc:
                last_error = str(exc)
                self.last_info["router_parse_errors"].append(
                    {"attempt": attempt + 1, "error": last_error}
                )
                messages.append({"role": "assistant", "content": output})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Invalid external route JSON: {}. Retry with exactly one "
                            "JSON object and no prose. Use only the allowed route, "
                            "expected action, evidence, subject_scope, threat_confidence, "
                            "and candidate_route labels."
                        ).format(last_error),
                    }
                )
        fallback = ExternalRequestRoute(
            request_type="unknown",
            route="clarify",
            expected_actions=["ask_clarification"],
            evidence_required=[],
            subject_scope="unknown",
            clarification_needed=True,
            missing_information=["what you need help with"],
            disallowed_information=[],
            threat_confidence="low",
            candidate_route=None,
            reason="Router failed to produce valid JSON: {}".format(last_error or "unknown error"),
        )
        self.last_info["route"] = fallback.as_dict()
        return fallback

    def gate_intended_retrieval(self, route: ExternalRequestRoute) -> GateDecision:
        """Gate a planned retrieval before the downstream DSL executes it."""
        decision = evaluate_intended_retrieval(
            route.evidence_required,
            route.subject_scope,
        )
        self.last_info["pre_retrieval_gate"] = decision.as_dict()
        return decision

    def build_clarification(self, route: ExternalRequestRoute) -> str:
        """Build a clarification question for missing external-facing information."""
        return respond_to_user(route.missing_information)

    def build_refusal(self, route: ExternalRequestRoute) -> str:
        """Build a refusal when requested evidence is disallowed."""
        return render_refusal(route.reason)


def _route_low_confidence_to_supported_workflow(route: ExternalRequestRoute) -> ExternalRequestRoute:
    """Prefer retrieval when a refusal/unsupported route is not high confidence."""
    if route.threat_confidence == "high":
        return route
    if route.route not in ("refuse", "unsupported"):
        return route
    candidate_route = best_supported_route(route)
    if candidate_route:
        return route_as_supported_workflow(route, candidate_route, "Low-confidence external route normalized for gated retrieval")
    return route


def best_supported_route(route: ExternalRequestRoute) -> Optional[str]:
    """Return the best supported downstream workflow from router output."""
    if route.candidate_route in ("knowledge_qa", "named_entity_disambiguation"):
        return route.candidate_route
    if route.route in ("knowledge_qa", "named_entity_disambiguation"):
        return route.route
    actions = set(route.expected_actions or [])
    if actions.intersection({"query_current_customer", "query_purchase_history", "query_order_history"}):
        return "named_entity_disambiguation"
    if "query_public_knowledge_articles" in actions:
        return "knowledge_qa"
    evidence_types = {
        str(item.get("evidence_type") or "")
        for item in route.evidence_required
        if isinstance(item, dict)
    }
    if evidence_types.intersection({"current_customer_purchase_history", "current_customer_order_history", "product_catalog"}):
        return "named_entity_disambiguation"
    if evidence_types.intersection({"public_product_support", "public_warranty_or_returns", "public_service_channel", "public_troubleshooting"}):
        return "knowledge_qa"
    return None


def route_as_supported_workflow(route: ExternalRequestRoute, candidate_route: str, reason_prefix: str) -> ExternalRequestRoute:
    """Convert a safe coarse route into the chosen downstream workflow route."""
    if candidate_route == "named_entity_disambiguation":
        return ExternalRequestRoute(
            request_type="named_entity_disambiguation",
            route="named_entity_disambiguation",
            expected_actions=["query_current_customer", "query_purchase_history", "query_product_catalog"],
            evidence_required=[
                {
                    "evidence_type": "current_customer_purchase_history",
                    "subject_scope": "current_customer",
                    "reason": "Candidate workflow can check scoped current-customer purchase evidence.",
                },
                {
                    "evidence_type": "product_catalog",
                    "subject_scope": "public",
                    "reason": "Public catalog evidence can support entity resolution.",
                },
            ],
            subject_scope="current_customer",
            threat_confidence=route.threat_confidence,
            candidate_route=candidate_route,
            reason="{}: {}".format(reason_prefix, route.reason),
        )
    return ExternalRequestRoute(
        request_type="knowledge_qa",
        route="knowledge_qa",
        expected_actions=["query_public_knowledge_articles"],
        evidence_required=[
            {
                "evidence_type": "public_product_support",
                "subject_scope": "public",
                "reason": "Candidate workflow can check public knowledge evidence.",
            }
        ],
        subject_scope="public",
        threat_confidence=route.threat_confidence,
        candidate_route=candidate_route,
        reason="{}: {}".format(reason_prefix, route.reason),
    )


class ExternalFacingDSLRunResult:
    """Common result object for external-facing DSL drivers."""

    def __init__(
        self,
        reward: float,
        done: bool,
        messages: List[Dict[str, str]],
        info: Optional[Dict[str, Any]] = None,
    ):
        self.reward = reward
        self.done = done
        self.messages = messages
        self.info = info or {}
