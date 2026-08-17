"""Generic workflow driver for the EWM runtime."""

from typing import Any, Callable, Dict, List, Optional

from ewm.ir.environment import EnvironmentIR, reachable_information
from ewm.ir.base import ensure_dict
from ewm.ir.frame import InstanceFrame
from ewm.ir.frame import infer_instance_frame
from ewm.ir.state import Claim, CompletionState, Effect, ExecutionState
from ewm.mcp.normalizer import normalize_observation, to_observation
from ewm.mcp.salesforce_reads import execute_mcp_call

from .action_selector import DecisionSelector, WorkflowDecision, select_workflow_decision
from .completion import evaluate_completion
from .renderer import render_response
from .verifier import CompletionVerifierSuite, validate_mcp_call

FrameInferer = Callable[[List[Dict[str, Any]], Dict[str, Any]], InstanceFrame]
ClaimExtractor = Callable[[InstanceFrame, ExecutionState], List[Claim]]


class WorkflowDriver:
    """Generic workflow loop.

    The current connected backend may expose only read actions, but the driver
    is not read-specific. Future MCP/action providers can add mutation,
    approval, notification, or other enterprise actions to the same loop.
    """

    def __init__(
        self,
        mcp_client: Any,
        env_ir: EnvironmentIR,
        frame_inferer: FrameInferer = infer_instance_frame,
        decision_selector: DecisionSelector = select_workflow_decision,
        claim_extractor: Optional[ClaimExtractor] = None,
        completion_verifier_suite: Optional[CompletionVerifierSuite] = None,
        max_steps: int = 8,
    ) -> None:
        self.mcp_client = mcp_client
        self.env_ir = env_ir
        self.frame_inferer = frame_inferer
        self.decision_selector = decision_selector
        self.claim_extractor = claim_extractor
        self.completion_verifier_suite = completion_verifier_suite or CompletionVerifierSuite()
        self.max_steps = max_steps

    def initialize_state(self, messages: List[Dict[str, Any]], env_summary: Dict[str, Any]) -> ExecutionState:
        # Pipeline stage: user request -> LLM-inferred InstanceFrame.
        frame = self.frame_inferer(messages, env_summary)
        state = ExecutionState(frame=frame)
        state.history.extend(dict(message) for message in messages)
        return state

    def run(
        self,
        messages: List[Dict[str, Any]],
        env_summary: Optional[Dict[str, Any]] = None,
        initial_state: Optional[ExecutionState] = None,
    ) -> ExecutionState:
        """Run until completion, clarification, blocked state, or step budget."""

        state = initial_state or self.initialize_state(messages, env_summary or {})
        if initial_state is not None:
            _integrate_new_history(state, messages)
        for _ in range(self.max_steps):
            state = self.step(state)
            if self._should_pause_or_stop(state):
                return state
        state.completion_state.ready = False
        state.completion_state.status = "needs_action"
        state.completion_state.reason = "Step budget exhausted before the workflow reached completion."
        state.metrics["errors"].append({"type": "step_budget_exhausted", "max_steps": self.max_steps})
        return state

    def step(self, state: ExecutionState) -> ExecutionState:
        # Pipeline stage: expose current MCP tool schemas to the controller.
        tools = self.mcp_client.list_tools()

        # Pipeline stage: compute graph-grounded reachable information from
        # EnvironmentIR and the current resolved entities in ExecutionState.
        reachable = reachable_information(state, self.env_ir)

        # Pipeline stage: LLM/controller chooses backend_action, frontend_action,
        # or complete from the constrained menu. The driver does not decide the
        # task-specific semantics here.
        decision = self.decision_selector(state.frame, state, reachable, tools)
        state.record_action_planned(decision.to_dict())
        self._apply_decision_state_updates(state, decision)

        if decision.decision_type == "backend_action":
            return self._execute_backend_action(state, decision, tools)

        if decision.decision_type == "complete":
            state.candidates["outcome"] = decision.candidate_outcome
            state.candidates["response"] = decision.candidate_response
            # Pipeline stage: completion proposals are not trusted directly.
            # The verifier suite runs structural checks plus optional LLM
            # semantic verifiers over frame/state/constraints/evidence.
            suite_result = self.completion_verifier_suite.run(state.frame, state, self.env_ir)
            state.completion_state = evaluate_completion(state.frame, state, suite_result=suite_result)
            if not state.completion_state.ready:
                self._record_verifier_feedback(state, suite_result)
            return state

        if decision.decision_type == "frontend_action":
            state.completion_state.ready = False
            state.completion_state.status = "needs_action"
            state.completion_state.needed = [
                {
                    "source": "user",
                    "description": decision.frontend_message or decision.reason,
                }
            ]
            state.completion_state.reason = decision.reason
            return state

        state.record_action_failed(decision.to_dict(), "unknown workflow decision type")
        return state

    def _execute_backend_action(
        self,
        state: ExecutionState,
        decision: WorkflowDecision,
        tools: List[Any],
    ) -> ExecutionState:
        call = decision.backend_action
        if call is None:
            state.record_action_failed(decision.to_dict(), "backend_action decision missing backend_action")
            self._mark_needs_action(state, "Backend action decision did not include a tool call.")
            return state
        tool_schema = next((tool for tool in tools if tool.name == call.name), None)
        if tool_schema is None:
            state.record_action_failed(call.to_dict(), "unknown tool")
            self._mark_needs_action(state, "Controller selected an unknown MCP tool.")
            return state

        # Pipeline stage: symbolic validation before execution. The LLM can
        # propose a call, but schema/tool validation owns whether it can run.
        validation = validate_mcp_call(call, state, self.env_ir, tool_schema)
        if not validation.valid:
            state.record_action_failed(call.to_dict(), validation.reason)
            self._mark_needs_action(state, validation.reason)
            return state

        # Pipeline stage: execute the validated MCP call against the backend.
        observation = execute_mcp_call(self.mcp_client, call)
        state.record_action_executed(call.to_dict())
        state.metrics["env_calls"] = int(state.metrics.get("env_calls", 0)) + 1

        # Pipeline stage: preserve raw MCP output as an Observation for replay.
        state.add_observation(to_observation(call, observation))

        # Pipeline stage: deterministically normalize records/schema/user
        # context into citable EvidenceItems with stable provenance.
        for evidence in normalize_observation(call, observation):
            state.add_evidence(evidence)

        if not observation.ok:
            state.metrics["errors"].append({"type": "mcp_error", "call": call.to_dict(), "error": observation.error})
            state.record_action_failed(call.to_dict(), str(observation.error))

        # Pipeline stage: optional semantic extraction. The runtime owns
        # evidence IDs; the extractor may add Claims that cite those IDs.
        if self.claim_extractor is not None:
            for claim in self.claim_extractor(state.frame, state):
                state.upsert_claim(claim)
        return state

    def render(self, state: ExecutionState) -> str:
        return render_response(state.frame, state, state.completion_state)

    def _should_pause_or_stop(self, state: ExecutionState) -> bool:
        if state.completion_state.ready:
            return True
        if state.completion_state.status == "needs_action":
            return _needed_source(state) == "user"
        return False

    def _mark_needs_action(self, state: ExecutionState, reason: str) -> None:
        state.completion_state.ready = False
        state.completion_state.status = "needs_action"
        state.completion_state.needed = [{"source": "action", "description": reason}]
        state.completion_state.reason = reason

    def _apply_decision_state_updates(self, state: ExecutionState, decision: WorkflowDecision) -> None:
        updates = ensure_dict(decision.state_updates)
        frame_updates = ensure_dict(updates.get("frame"))
        if frame_updates:
            current = state.frame.to_dict()
            merged = _merge_non_empty(current, frame_updates)
            state.update_frame(InstanceFrame.from_dict(merged))
        _extend_unique_objects(state.resolved["entities"], updates.get("resolved_entities"))
        _extend_unique_objects(state.resolved["facts"], updates.get("resolved_facts"))
        _extend_unique_objects(state.resolved["unresolved"], updates.get("unresolved"))
        _extend_unique_objects(state.derived["summaries"], updates.get("summaries"))
        self._extend_effects(state, updates.get("effects"))
        valid_ids = set(state.evidence_ids())
        for claim in decision.claims:
            claim.supporting_evidence_ids = [
                evidence_id for evidence_id in claim.supporting_evidence_ids
                if evidence_id in valid_ids
            ]
            if claim.claim_text:
                state.upsert_claim(claim)

    def _extend_effects(self, state: ExecutionState, items: Any) -> None:
        if not isinstance(items, list):
            return
        existing_ids = {effect.effect_id for effect in state.effects}
        valid_evidence_ids = set(state.evidence_ids())
        observation_ids = {
            observation.observation_id
            for observation in state.collected.get("observations", [])
        }
        for item in items:
            if item in (None, "", {}, []):
                continue
            effect = Effect.from_dict(ensure_dict(item))
            if not effect.effect_id:
                effect.effect_id = "effect_{}".format(len(state.effects) + 1)
            if effect.effect_id in existing_ids:
                continue
            effect.evidence_ids = [
                evidence_id
                for evidence_id in effect.evidence_ids
                if evidence_id in valid_evidence_ids
            ]
            if effect.observation_id and effect.observation_id not in observation_ids:
                effect.observation_id = ""
            state.add_effect(effect)
            existing_ids.add(effect.effect_id)

    def _record_verifier_feedback(self, state: ExecutionState, suite_result: Any) -> None:
        if getattr(suite_result, "valid", False):
            return
        reason = str(getattr(suite_result, "reason", "") or state.completion_state.reason or "").strip()
        checks = [
            check.to_dict() if hasattr(check, "to_dict") else ensure_dict(check)
            for check in getattr(suite_result, "checks", []) or []
            if not getattr(check, "valid", False)
        ]
        feedback = {
            "source": "completion_verifier",
            "description": reason or "Completion verifier rejected the candidate response.",
            "candidate_outcome": _truncate_text(str(state.candidates.get("outcome") or ""), 500),
            "candidate_response_preview": _truncate_text(str(state.candidates.get("response") or ""), 500),
            "failed_checks": [
                {
                    "valid": check.get("valid"),
                    "reason": _truncate_text(str(check.get("reason") or ""), 500),
                }
                for check in checks[:5]
            ],
        }
        _extend_unique_objects(state.resolved["unresolved"], [feedback])
        _extend_unique_objects(
            state.derived["summaries"],
            [
                {
                    "source": "completion_verifier",
                    "description": (
                        "Previous completion attempt was rejected: "
                        + (reason or "candidate response was not ready.")
                    ),
                }
            ],
        )


def _needed_source(state: ExecutionState) -> str:
    needed = state.completion_state.needed
    if not needed:
        return ""
    first = needed[0]
    if not isinstance(first, dict):
        return ""
    return str(first.get("source") or "")


def _merge_non_empty(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in updates.items():
        if value is None or value == "" or value == [] or value == {}:
            continue
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_non_empty(dict(merged[key]), value)
        elif key == "constraints" and isinstance(value, list) and isinstance(merged.get(key), list):
            merged[key] = _extend_list_preserving_order(list(merged[key]), value)
        else:
            merged[key] = value
    return merged


def _extend_list_preserving_order(base: List[Any], updates: List[Any]) -> List[Any]:
    merged = list(base)
    existing = [item for item in merged]
    for item in updates:
        if item in (None, "", {}, []):
            continue
        if item not in existing:
            merged.append(item)
            existing.append(item)
    return merged


def _extend_unique_objects(target: List[Any], items: Any) -> None:
    if not isinstance(items, list):
        return
    existing = [item for item in target]
    for item in items:
        if item in (None, "", {}, []):
            continue
        if item not in existing:
            target.append(item)
            existing.append(item)


def _integrate_new_history(state: ExecutionState, messages: List[Dict[str, Any]]) -> None:
    existing = [dict(message) for message in state.history]
    new_user_messages: List[Dict[str, Any]] = []
    for message in messages:
        item = dict(message)
        if item not in existing:
            state.history.append(item)
            existing.append(item)
            if item.get("role") == "user":
                new_user_messages.append(item)
    if new_user_messages:
        _focus_latest_user_turn(state, new_user_messages[-1])


def _focus_latest_user_turn(state: ExecutionState, message: Dict[str, Any]) -> None:
    latest = str(message.get("content") or "").strip()
    if not latest:
        return
    previous_goal = state.frame.goal
    previous_summary = state.frame.request_summary
    state.frame.metadata["latest_user_message"] = latest
    if previous_goal:
        _append_metadata_list(state.frame.metadata, "previous_goals", previous_goal)
    if previous_summary:
        _append_metadata_list(state.frame.metadata, "previous_request_summaries", previous_summary)
    state.candidates = {"outcome": None, "response": None}
    state.completion_state = CompletionState(
        ready=False,
        status="running",
        reason="New user turn received; previous candidate response must be re-evaluated.",
    )
    _extend_unique_objects(
        state.resolved["unresolved"],
        [
            {
                "source": "user_followup",
                "description": "Latest user turn needs a response: {}".format(latest),
            }
        ],
    )
    _extend_unique_objects(
        state.derived["summaries"],
        [
            {
                "source": "user_followup",
                "description": (
                    "The user added a follow-up. Re-answer the latest turn using "
                    "existing claims/evidence when sufficient; query or ask only "
                    "if the current state cannot support the response. Latest "
                    "turn: {}".format(latest)
                ),
            }
        ],
    )


def _append_metadata_list(metadata: Dict[str, Any], key: str, value: Any) -> None:
    current = metadata.get(key)
    if not isinstance(current, list):
        current = [] if current in (None, "", {}, []) else [current]
        metadata[key] = current
    if value not in current:
        current.append(value)


def _truncate_text(text: str, max_chars: int) -> str:
    text = str(text or "")
    return text if len(text) <= max_chars else text[:max_chars] + "...[truncated]"
