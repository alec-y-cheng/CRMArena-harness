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
                            "expected action, evidence, and subject_scope labels."
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
