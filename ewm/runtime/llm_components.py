"""LLM-backed components for the generic EWM workflow driver."""

import json
import os
import re
from typing import Any, Callable, Dict, List, Mapping, Optional

from ewm.ir.base import ensure_dict, to_plain
from ewm.ir.environment import EnvironmentIR, ReachableInfo
from ewm.ir.frame import InstanceFrame
from ewm.ir.state import Claim, ExecutionState
from ewm.mcp.client import MCPCall, MCPToolSchema
from ewm.runtime.action_selector import WorkflowDecision

ModelCall = Callable[[List[Dict[str, str]], Optional[int]], str]


class LLMRuntimeComponents:
    """Generic LLM implementations for frame, decision, claims, and completion.

    The components only ask the model to fill structured JSON. Tool execution,
    MCP call validation, evidence IDs, and completion-state control stay in the
    symbolic runtime.
    """

    def __init__(
        self,
        model_call: ModelCall,
        max_retries: int = 2,
        frame_max_tokens: int = 1200,
        decision_max_tokens: int = 1400,
        claim_max_tokens: int = 1200,
        verifier_max_tokens: int = 900,
    ) -> None:
        self.model_call = model_call
        self.max_retries = max(0, int(max_retries))
        self.frame_max_tokens = frame_max_tokens
        self.decision_max_tokens = decision_max_tokens
        self.claim_max_tokens = claim_max_tokens
        self.verifier_max_tokens = verifier_max_tokens
        self.debug: Dict[str, List[Dict[str, Any]]] = {
            "frame_calls": [],
            "decision_calls": [],
            "claim_calls": [],
            "completion_verifier_calls": [],
        }

    def infer_frame(self, messages: List[Dict[str, Any]], env_summary: Dict[str, Any]) -> InstanceFrame:
        prompt = _frame_prompt(messages, env_summary)
        data = self._json_call("frame", prompt, self.frame_max_tokens)
        frame = InstanceFrame.from_dict(data)
        frame.metadata.setdefault("raw_llm_frame", data)
        return frame

    def select_decision(
        self,
        frame: InstanceFrame,
        state: ExecutionState,
        reachable: List[ReachableInfo],
        tools: List[MCPToolSchema],
        ) -> WorkflowDecision:
        model_state = _compact_state(state)
        presented_evidence_ids = _one_step_evidence_ids(state)
        presented_summary_count = _current_summary_count(state)
        prompt = _decision_prompt(frame, model_state, reachable, tools)
        data = self._json_call("decision", prompt, self.decision_max_tokens)
        _mark_presented_evidence_ids(state, presented_evidence_ids)
        _mark_presented_summary_count(state, presented_summary_count)
        decision_type = str(data.get("decision_type") or "").strip()
        backend_action = None
        action_data = data.get("backend_action")
        if isinstance(action_data, Mapping):
            name = str(action_data.get("name") or "").strip()
            arguments = action_data.get("arguments") if isinstance(action_data.get("arguments"), Mapping) else {}
            if name:
                backend_action = MCPCall(
                    name=name,
                    arguments=dict(arguments),
                    call_id="step_{}".format(len(state.actions.get("planned", [])) + 1),
                    metadata={"source": "llm_decision"},
                )
        return WorkflowDecision(
            decision_type=decision_type,
            backend_action=backend_action,
            frontend_message=data.get("frontend_message"),
            candidate_outcome=data.get("candidate_outcome"),
            candidate_response=data.get("candidate_response"),
            state_updates=data.get("state_updates") if isinstance(data.get("state_updates"), Mapping) else {},
            claims=self._claims_from_data(data, state),
            reason=str(data.get("reason") or ""),
            metadata={"raw_llm_decision": data},
        )

    def extract_claims(self, frame: InstanceFrame, state: ExecutionState) -> List[Claim]:
        if not state.collected.get("evidence"):
            return []
        prompt = _claim_prompt(frame, state)
        data = self._json_call("claims", prompt, self.claim_max_tokens)
        return self._claims_from_data(data, state)

    def _claims_from_data(self, data: Mapping[str, Any], state: ExecutionState) -> List[Claim]:
        claims = []
        valid_evidence_ids = set(state.evidence_ids())
        for index, item in enumerate(data.get("claims", []) or []):
            if not isinstance(item, Mapping):
                continue
            item_data = dict(item)
            item_data.setdefault("claim_id", "claim_{}".format(len(state.derived.get("claims", [])) + index + 1))
            claim = Claim.from_dict(item_data)
            claim.supporting_evidence_ids = [
                evidence_id for evidence_id in claim.supporting_evidence_ids
                if evidence_id in valid_evidence_ids
            ]
            if claim.claim_text:
                claims.append(claim)
        return claims

    def verify_completion_payload(self, payload: Dict[str, Any]) -> Mapping[str, Any]:
        prompt = _completion_verifier_prompt(payload)
        data = self._json_call("completion_verifier", prompt, self.verifier_max_tokens)
        return {
            "valid": bool(data.get("valid", data.get("ready", False))),
            "reason": str(data.get("reason") or ""),
            "issues": data.get("issues") or [],
            "raw": data,
        }

    def _json_call(self, stage: str, prompt: str, max_tokens: int) -> Dict[str, Any]:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a structured CRM workflow component. Return exactly "
                    "one JSON object. Do not include prose outside JSON."
                ),
            },
            {"role": "user", "content": prompt},
        ]
        attempts = []
        for attempt in range(self.max_retries + 1):
            text = self.model_call(messages, max_tokens)
            attempts.append({"attempt": attempt + 1, "output": text})
            try:
                parsed = parse_json_object(text)
                self.debug.setdefault("{}_calls".format(stage), []).append(
                    {"prompt": prompt, "attempts": attempts, "parsed": parsed}
                )
                return parsed
            except ValueError as exc:
                messages.append({"role": "assistant", "content": text})
                messages.append(
                    {
                        "role": "user",
                        "content": "Invalid JSON: {}. Retry with exactly one JSON object.".format(exc),
                    }
                )
        self.debug.setdefault("{}_calls".format(stage), []).append(
            {"prompt": prompt, "attempts": attempts, "parsed": {}, "error": "json_parse_failed"}
        )
        return {}


def parse_json_object(text: str) -> Dict[str, Any]:
    cleaned = _strip_think_blocks(str(text or "")).strip()
    cleaned = _strip_code_fence(cleaned)
    candidates = [cleaned]
    extracted = _extract_first_json_object(cleaned)
    if extracted and extracted != cleaned:
        candidates.append(extracted)
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
        raise ValueError("expected JSON object")
    raise ValueError("could not parse JSON object")


def _frame_prompt(messages: List[Dict[str, Any]], env_summary: Dict[str, Any]) -> str:
    return json.dumps(
        {
            "task": (
                "Compile an InstanceFrame for the current CRM request from the "
                "conversation and benchmark-visible instruction surface. Capture "
                "the goal, user-visible/system-visible constraints, referenced "
                "entities, evidence requirements, outcome contract, and response "
                "contract. Preserve all requirements that appear in the benchmark "
                "instructions or metadata, and do not add policies or task rules "
                "beyond those inputs. Store a constraint only if it would still "
                "govern task execution or the user-visible outcome under a "
                "different runtime. Exclude protocol instructions about JSON, "
                "action tags, ReAct formatting, system observations, or this "
                "compilation step itself. For constraints and final-answer rules, "
                "copy exact wording from the prompt whenever possible instead of "
                "paraphrasing. Do not solve the task yet."
            ),
            "conversation": _compact_messages(messages),
            "environment_summary": _truncate(to_plain(env_summary), 30000),
            "output_schema": {
                "frame_id": "short id",
                "goal": "what the user wants",
                "request_summary": "brief summary",
                "actor": {"kind": "internal_user|external_customer|unknown"},
                "entities_or_references": [{"type": "object or concept", "value": "visible reference"}],
                "constraints": ["explicit or inferred constraints from user/system context"],
                "evidence_requirements": [
                    {
                        "requirement_id": "req_1",
                        "description": "information needed",
                        "evidence_type": "generic evidence label",
                        "source": "user|environment|model",
                        "subject": "entity/concept",
                        "required": True,
                    }
                ],
                "outcome_contract": {
                    "description": "what must be true before completion",
                    "success_criteria": ["criteria"],
                    "required_claims": ["claim types if known"],
                    "requires_verification": True,
                },
                "response_contract": {
                    "description": "how to answer the user",
                    "format_hint": "format constraints explicitly implied by the request or system context, if any",
                    "constraints": ["response constraints"],
                    "allowed_audience": "who may receive the answer if relevant",
                },
                "final_answer_contract": {
                    "exact_instruction": "exact prompt wording for final answer format, if any",
                    "strict": False,
                    "allowed_answer_types": ["record_id|literal|natural_language|boolean|number"],
                    "allowed_literals": ["None"],
                    "separator": "comma if multiple answers are explicitly allowed",
                    "metadata": {},
                },
                "metadata": {},
            },
        },
        indent=2,
        sort_keys=True,
    )


def _decision_prompt(
    frame: InstanceFrame,
    model_state: Dict[str, Any],
    reachable: List[ReachableInfo],
    tools: List[MCPToolSchema],
) -> str:
    return json.dumps(
        {
            "task": (
                "Choose the next generic workflow decision. Use backend_action "
                "when more Salesforce evidence is needed, frontend_action when "
                "you choose to ask or tell the user something, and complete only when you can propose a "
                "candidate outcome and candidate response supported by state. "
                "In the same JSON object, propose bounded ExecutionState updates "
                "from the current conversation/state, and extract any useful "
                "claims from new readable evidence or existing claims. Claims are "
                "persistent semantic memory; raw evidence content is transient "
                "and may only be visible for small retrieval batches. If a large "
                "retrieval only exposes headers, choose a narrower/direct backend "
                "query for specific records if more detail is needed. If InstanceFrame.metadata contains "
                "a latest_user_message, treat it as the active user turn. Update "
                "semantic frame fields such as goal, request_summary, entities, "
                "evidence_requirements, outcome_contract, and response_contract "
                "only when the latest turn changes what must be answered."
                " Preserve exact wording for constraints and final-answer rules; "
                "do not replace a strict final answer rule with a looser paraphrase."
            ),
            "allowed_decision_types": ["backend_action", "frontend_action", "complete"],
            "instance_frame": frame.to_dict(),
            "execution_state": model_state,
            "reachable_information": _truncate([item.to_dict() for item in reachable], 12000),
            "available_tools": [tool.to_dict() for tool in tools],
            "backend_action_rules": [
                "Only select tools from available_tools.",
                "Use tool argument names exactly as shown in the tool input schema.",
                "Read-only SOQL must start with SELECT.",
                "Use find/SOSL for keyword or text search when the exact record ID or structured field filter is not known.",
                "Do not repeat failed tool calls or equivalent query shapes; use the failure reason to choose a different strategy.",
                "Respect documented query capabilities exposed by the tool schemas, schema metadata, and prior backend errors.",
                "Prefer small, targeted queries with LIMIT when possible.",
                "Use Salesforce IDs or terms from the conversation/evidence when available.",
            ],
            "output_schema": {
                "state_updates": {
                    "frame": {
                        "goal": "updated goal if clearer",
                        "request_summary": "updated request summary if clearer",
                        "actor": {"kind": "internal_user|external_customer|unknown"},
                        "entities_or_references": [{"type": "object or concept", "value": "visible reference"}],
                        "constraints": ["explicit or inferred constraints"],
                        "evidence_requirements": [
                            {
                                "requirement_id": "req_1",
                                "description": "information needed",
                                "evidence_type": "generic evidence label",
                                "source": "user|environment|model",
                                "subject": "entity/concept",
                                "required": True,
                            }
                        ],
                        "outcome_contract": {
                            "description": "what must be true before completion",
                            "success_criteria": ["criteria"],
                            "required_claims": ["claim types if known"],
                            "requires_verification": True,
                        },
                        "response_contract": {
                            "description": "how to answer the user",
                            "format_hint": "format constraints explicitly implied by the request or system context, if any",
                            "constraints": ["response constraints"],
                            "allowed_audience": "who may receive the answer if relevant",
                        },
                        "final_answer_contract": {
                            "exact_instruction": "exact prompt wording for final answer format, if any",
                            "strict": False,
                            "allowed_answer_types": ["record_id|literal|natural_language|boolean|number"],
                            "allowed_literals": ["None"],
                            "separator": "comma if multiple answers are explicitly allowed",
                            "metadata": {},
                        },
                        "metadata": {},
                    },
                    "resolved_entities": [{"object": "optional object type", "id": "optional record id", "description": "resolved entity"}],
                    "resolved_facts": [{"description": "non-citable working fact", "value": "optional value"}],
                    "unresolved": [{"description": "remaining ambiguity or missing information"}],
                    "effects": [
                        {
                            "effect_id": "stable short id",
                            "action_id": "related action id if known",
                            "operation": "query|create|update|delete|approve|notify|other",
                            "object_name": "affected object if any",
                            "record_id": "affected record id if any",
                            "status": "confirmed|attempted|failed|unknown",
                            "before": {},
                            "after": {},
                            "changes": {},
                            "evidence_ids": ["ev_id if supporting evidence exists"],
                            "observation_id": "source observation id if any",
                            "reason": "brief effect summary",
                            "metadata": {},
                        }
                    ],
                    "summaries": [{"description": "brief state summary"}],
                },
                "claims": [
                    {
                        "claim_id": "stable short id",
                        "claim_text": "one concise atomic supported claim",
                        "status": "supported|unknown|contradicted",
                        "value": "optional extracted value",
                        "supporting_evidence_ids": ["existing ev_id only"],
                        "confidence": 0.0,
                        "reason": "brief reason",
                        "metadata": {},
                    }
                ],
                "claim_update_rules": [
                    "Append new claims when new evidence supports a new useful interpretation.",
                    "Reuse an existing claim_id when newer evidence should replace that claim.",
                    "When new_evidence_items include readable content, extract any task-relevant claims from them now; readable content may not be shown again.",
                    "When new_evidence_items are headers-only, do not invent claims from unseen bodies; query specific promising record IDs or narrower terms if the headers are insufficient.",
                    "Do not omit a direct answer span from retrieved evidence in favor of a broader related claim.",
                    "Keep claim_text and reason concise. Claims should be atomic facts, not multi-paragraph reports.",
                ],
                "decision_type": "backend_action|frontend_action|complete",
                "backend_action": {"name": "tool name or empty", "arguments": {}},
                "frontend_message": "clarification question if decision_type is frontend_action",
                "candidate_outcome": "structured result if complete",
                "candidate_response": "user-facing response if complete",
                "reason": "brief rationale",
            },
        },
        indent=2,
        sort_keys=True,
    )


def _claim_prompt(frame: InstanceFrame, state: ExecutionState) -> str:
    return json.dumps(
        {
            "task": (
                "Extract concise claims from the collected evidence that are useful "
                "for satisfying the InstanceFrame. Claims must cite existing "
                "evidence IDs only. Reuse an existing claim_id when newer "
                "evidence should replace that claim. Keep each claim atomic and "
                "concise; do not summarize entire articles or trajectories in a "
                "single claim."
            ),
            "instance_frame": frame.to_dict(),
            "evidence": _compact_evidence(state, max_items=30),
            "existing_claims": [claim.to_dict() for claim in state.derived.get("claims", [])][-20:],
            "output_schema": {
                "claims": [
                    {
                        "claim_id": "stable short id",
                        "claim_text": "one concise atomic supported claim",
                        "status": "supported|unknown|contradicted",
                        "value": "optional extracted value",
                        "supporting_evidence_ids": ["ev_id"],
                        "confidence": 0.0,
                        "reason": "brief reason",
                        "metadata": {},
                    }
                ]
            },
        },
        indent=2,
        sort_keys=True,
    )


def _completion_verifier_prompt(payload: Dict[str, Any]) -> str:
    return json.dumps(
        {
            "task": (
                "Verify whether the candidate response is ready to send. Check "
                "the InstanceFrame goal, constraints, evidence requirements, "
                "outcome contract, and response contract against the ExecutionState. "
            ),
            "payload": _shallow_compact_verifier_payload(payload),
            "output_schema": {
                "valid": True,
                "reason": "brief verifier judgment",
                "issues": ["missing or violated constraints, if any"],
            },
        },
        indent=2,
        sort_keys=True,
    )


def _compact_messages(messages: List[Dict[str, Any]], max_messages: int = 12) -> List[Dict[str, str]]:
    out = []
    for message in messages[-max_messages:]:
        out.append(
            {
                "role": str(message.get("role") or ""),
                "content": _truncate_text(str(message.get("content") or ""), 2500),
            }
        )
    return out


def _compact_state(state: ExecutionState) -> Dict[str, Any]:
    """Return the model-facing execution state.

    Raw observations are retained in ExecutionState for replay, but controller
    calls only need a compact view: what was tried, whether it worked, what
    evidence IDs exist, and the current claims/summaries. This prevents full
    article/search payloads from being resent on every decision call.
    """

    return {
        "history": [_compact_message(message) for message in state.history[-8:]],
            "collected": {
                "observations": _compact_observations(state, max_items=8),
                "evidence_inventory": _evidence_inventory(state, max_items=100),
                "new_evidence_items": _one_step_evidence_items(state),
                "new_evidence_inbox": _one_step_evidence_inbox_summary(state),
            },
            "resolved": _truncate(state.resolved, 7000),
            "derived": {
                "claims": [claim.to_dict() for claim in state.derived.get("claims", [])],
                "summaries": _one_step_summaries(state),
            },
        "effects": [effect.to_dict() for effect in state.effects[-10:]],
        "actions": {
            "planned": _compact_actions(state.actions.get("planned", [])[-6:]),
            "executed": _compact_actions(state.actions.get("executed", [])[-6:]),
            "failed": _compact_actions(state.actions.get("failed", [])[-6:]),
        },
        "verifier_results": _compact_verifier_results(state, max_items=5),
        "candidates": _truncate(state.candidates, 5000),
        "completion_state": _compact_completion_state(state),
        "metrics": state.metrics,
    }


def _one_step_evidence_ids(state: ExecutionState) -> List[str]:
    claimed_ids = _claimed_evidence_ids(state)
    presented_ids = set(str(item) for item in state.metrics.get("presented_evidence_item_ids", []) or [])
    out = []
    for item in state.collected.get("evidence", []):
        if item.evidence_id in claimed_ids or item.evidence_id in presented_ids:
            continue
        out.append(item.evidence_id)
    return out


def _one_step_evidence_inbox_summary(state: ExecutionState) -> Dict[str, Any]:
    ids = _one_step_evidence_ids(state)
    threshold = _evidence_content_item_threshold()
    readable = len(ids) <= threshold
    return {
        "evidence_ids_available_this_decision": ids,
        "mode": "readable_content" if readable else "headers_only_due_context_budget",
        "content_item_threshold": threshold,
        "total_new_evidence": len(ids),
        "readable_content_count": len(ids) if readable else 0,
        "header_only_count": 0 if readable else len(ids),
        "instruction": _one_step_inbox_instruction(readable),
    }


def _mark_presented_evidence_ids(state: ExecutionState, evidence_ids: List[str]) -> None:
    if not evidence_ids:
        return
    current = state.metrics.get("presented_evidence_item_ids")
    if not isinstance(current, list):
        current = []
        state.metrics["presented_evidence_item_ids"] = current
    for evidence_id in evidence_ids:
        if evidence_id not in current:
            current.append(evidence_id)


def _current_summary_count(state: ExecutionState) -> int:
    return len(state.derived.get("summaries", []) or [])


def _mark_presented_summary_count(state: ExecutionState, count: int) -> None:
    state.metrics["presented_summary_count"] = max(
        int(state.metrics.get("presented_summary_count", 0) or 0),
        int(count),
    )


def _one_step_summaries(state: ExecutionState) -> List[Dict[str, Any]]:
    presented = int(state.metrics.get("presented_summary_count", 0) or 0)
    summaries = state.derived.get("summaries", []) or []
    return _compact_summaries(summaries[presented:])


def _compact_evidence(state: ExecutionState, max_items: int) -> List[Dict[str, Any]]:
    evidence = []
    for item in state.collected.get("evidence", [])[-max_items:]:
        data = item.to_dict()
        data["content"] = _compact_evidence_content(data.get("content"))
        evidence.append(data)
    return evidence


def _one_step_evidence_items(state: ExecutionState) -> List[Dict[str, Any]]:
    claimed_ids = _claimed_evidence_ids(state)
    presented_ids = set(str(item) for item in state.metrics.get("presented_evidence_item_ids", []) or [])
    candidates = [
        item
        for item in state.collected.get("evidence", [])
        if item.evidence_id not in claimed_ids and item.evidence_id not in presented_ids
    ]
    readable = len(candidates) <= _evidence_content_item_threshold()
    items = []
    for item in candidates:
        model_item = {
            "evidence_id": item.evidence_id,
            "source_observation_id": item.source_observation_id,
            "source_tool": item.source_tool,
            "source_object": item.source_object,
            "record_id": item.record_id,
            "subject_scope": item.subject_scope,
            "content_header": _evidence_content_header(item.content),
            "content_available": readable,
            "visibility": {
                "mode": "one_step_inbox",
                "instruction": (
                    "Readable content is transient. Extract claims now when content_available=true; "
                    "when content_available=false, query narrower terms or specific record IDs if detail is needed."
                ),
            },
        }
        if readable:
            model_item["content"] = _one_step_readable_evidence_content(item.content)
        items.append(model_item)
    return items


def _compact_actions(actions: List[Any]) -> List[Dict[str, Any]]:
    """Summarize action history without replaying raw model state updates.

    Workflow decisions can carry a raw_llm_decision copy for audit/debug. That
    object often repeats claims, summaries, and candidate responses from prior
    turns. The controller only needs to know what was tried and why.
    """

    out = []
    for action in actions:
        data = action.to_dict() if hasattr(action, "to_dict") else to_plain(action)
        if not isinstance(data, Mapping):
            out.append({"value": _truncate_text(str(data), 400)})
            continue
        backend = data.get("backend_action")
        if hasattr(backend, "to_dict"):
            backend = backend.to_dict()
        compact = {
            "decision_type": data.get("decision_type"),
            "reason": _truncate_text(str(data.get("reason") or ""), 500),
            "candidate_outcome": _truncate_text(str(data.get("candidate_outcome") or ""), 500),
            "candidate_response": _truncate_text(str(data.get("candidate_response") or ""), 500),
        }
        if isinstance(backend, Mapping):
            compact["backend_action"] = {
                "name": backend.get("name"),
                "call_id": backend.get("call_id"),
                "arguments": _truncate(backend.get("arguments") or {}, 2000),
            }
        elif isinstance(data.get("name"), str):
            compact["backend_action"] = {
                "name": data.get("name"),
                "call_id": data.get("call_id"),
                "arguments": _truncate(data.get("arguments") or {}, 2000),
            }
        if data.get("frontend_message"):
            compact["frontend_message"] = _truncate_text(str(data.get("frontend_message") or ""), 500)
        if data.get("error"):
            compact["error"] = _truncate_text(str(data.get("error") or ""), 500)
        if data.get("observation_id"):
            compact["observation_id"] = data.get("observation_id")
        out.append(compact)
    return out


def _compact_summaries(summaries: List[Any]) -> List[Dict[str, Any]]:
    out = []
    for item in summaries:
        data = ensure_dict(item)
        if not data:
            continue
        out.append(
            {
                "source": data.get("source"),
                "description": _truncate_text(str(data.get("description") or data.get("value") or data), 500),
            }
        )
    return out


def _compact_completion_state(state: ExecutionState) -> Dict[str, Any]:
    completion = state.completion_state.to_dict()
    summary = completion.get("verifier_summary")
    if isinstance(summary, Mapping):
        completion["verifier_summary"] = {
            "valid": summary.get("valid"),
            "status": summary.get("status"),
            "reason": _truncate_text(str(summary.get("reason") or ""), 600),
            "failed_checks": [
                {
                    "valid": check.get("valid"),
                    "reason": _truncate_text(str(check.get("reason") or ""), 400),
                    "metadata_keys": sorted(str(key) for key in (check.get("metadata") or {}).keys())[:8]
                    if isinstance(check.get("metadata"), Mapping)
                    else [],
                }
                for check in (summary.get("checks") or [])
                if isinstance(check, Mapping) and not check.get("valid", False)
            ][:5],
        }
    completion["reason"] = _truncate_text(str(completion.get("reason") or ""), 500)
    completion["needed"] = _truncate(completion.get("needed", []), 3000)
    return completion


def _evidence_content_item_threshold() -> int:
    try:
        return max(1, int(os.environ.get("EWM_EVIDENCE_CONTENT_ITEM_THRESHOLD", "12")))
    except ValueError:
        return 12


def _one_step_inbox_instruction(readable: bool) -> str:
    if readable:
        return (
            "new_evidence_items includes readable content for the full new batch. "
            "Extract task-relevant claims now; this readable content will not be re-exposed by default."
        )
    return (
        "The new evidence batch is too large to expose readable content. "
        "new_evidence_items contains headers, record IDs, and provenance only. "
        "If the headers are insufficient, select a narrower/direct backend query for the specific records or terms you want to inspect."
    )


def _claimed_evidence_ids(state: ExecutionState) -> set:
    claimed = set()
    for claim in state.derived.get("claims", []):
        for evidence_id in claim.supporting_evidence_ids:
            if evidence_id:
                claimed.add(evidence_id)
    return claimed


def _evidence_inventory(state: ExecutionState, max_items: int) -> List[Dict[str, Any]]:
    claimed_ids = _claimed_evidence_ids(state)
    inventory = []
    for item in state.collected.get("evidence", [])[-max_items:]:
        inventory.append(
            {
                "evidence_id": item.evidence_id,
                "source_observation_id": item.source_observation_id,
                "source_tool": item.source_tool,
                "source_object": item.source_object,
                "record_id": item.record_id,
                "subject_scope": item.subject_scope,
                "claimed": item.evidence_id in claimed_ids,
                "content_header": _evidence_content_header(item.content),
            }
        )
    return inventory


def _evidence_content_header(content: Any) -> Dict[str, Any]:
    if not isinstance(content, Mapping):
        return {"preview": _truncate_text(str(content), 200)}
    header = {}
    for key in ("Id", "Name", "Title", "Subject", "Status", "StageName", "Summary", "UrlName"):
        if key in content:
            header[key] = _truncate_text(str(content.get(key) or ""), 300)
    if not header:
        for key, value in list(content.items())[:5]:
            header[str(key)] = _truncate_text(str(value), 160)
    return header


def _compact_message(message: Mapping[str, Any]) -> Dict[str, str]:
    return {
        "role": str(message.get("role") or ""),
        "content": _truncate_text(str(message.get("content") or ""), 1600),
    }


def _compact_observations(state: ExecutionState, max_items: int) -> List[Dict[str, Any]]:
    out = []
    for observation in state.collected.get("observations", [])[-max_items:]:
        payload = observation.payload
        summary = _payload_summary(payload)
        item = {
            "observation_id": observation.observation_id,
            "source": observation.source,
            "action_id": observation.action_id,
            "ok": observation.ok,
            "summary": summary,
        }
        if observation.metadata:
            item["metadata"] = _truncate(observation.metadata, 2000)
        out.append(item)
    return out


def _payload_summary(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {"type": type(payload).__name__, "preview": _truncate_text(str(payload), 300)}
    content = payload.get("content") if isinstance(payload.get("content"), Mapping) else payload
    records = []
    for key in ("records", "searchRecords"):
        value = content.get(key) if isinstance(content, Mapping) else None
        if isinstance(value, list):
            records = value
            break
    summary: Dict[str, Any] = {
        "ok": payload.get("ok"),
        "tool": payload.get("tool"),
        "keys": sorted(str(key) for key in content.keys())[:12] if isinstance(content, Mapping) else [],
    }
    if records:
        summary["record_count"] = len(records)
        summary["sample_records"] = [_record_header(record) for record in records[:5]]
    return summary


def _record_header(record: Any) -> Dict[str, Any]:
    if not isinstance(record, Mapping):
        return {"preview": _truncate_text(str(record), 200)}
    header = {}
    for key in ("Id", "Name", "Title", "Subject", "Status", "StageName", "Summary", "UrlName"):
        if key in record:
            header[key] = _truncate_text(str(record.get(key) or ""), 300)
    if not header:
        for key, value in list(record.items())[:5]:
            header[str(key)] = _truncate_text(str(value), 160)
    return header


def _compact_evidence_content(content: Any) -> Any:
    if not isinstance(content, Mapping):
        return _truncate(content, 900)
    compact = {}
    for key, value in content.items():
        if key in ("FAQ_Answer__c", "Body", "Description", "TextBody", "HtmlBody", "Summary"):
            compact[key] = _truncate_text(str(value or ""), 900)
        else:
            compact[key] = _truncate(value, 500)
    return compact


def _one_step_readable_evidence_content(content: Any) -> Any:
    """Expose fresh small-batch evidence with enough body text to derive claims.

    Old evidence is removed from later decision prompts once presented, so this
    is the one chance for the model to read article bodies and convert them into
    persistent claims. Keep a generous per-field guard only to avoid accidental
    pathological payloads.
    """

    max_chars = _one_step_readable_field_max_chars()
    if not isinstance(content, Mapping):
        return _truncate_text(str(content), max_chars)
    return {str(key): _truncate_text(str(value or ""), max_chars) for key, value in content.items()}


def _one_step_readable_field_max_chars() -> int:
    try:
        return max(1000, int(os.environ.get("EWM_READABLE_EVIDENCE_FIELD_MAX_CHARS", "20000")))
    except ValueError:
        return 20000


def _compact_verifier_results(state: ExecutionState, max_items: int) -> List[Dict[str, Any]]:
    out = []
    for result in state.verifier_results[-max_items:]:
        if not isinstance(result, Mapping):
            out.append({"value": _truncate_text(str(result), 300)})
            continue
        out.append(
            {
                "valid": result.get("valid"),
                "reason": _truncate_text(str(result.get("reason") or ""), 500),
                "metadata_keys": sorted(str(key) for key in (result.get("metadata") or {}).keys())[:8]
                if isinstance(result.get("metadata"), Mapping)
                else [],
            }
        )
    return out


def _truncate(value: Any, max_chars: int) -> Any:
    text = json.dumps(to_plain(value), sort_keys=True, default=str)
    if len(text) <= max_chars:
        return value
    return {"truncated_json": text[:max_chars], "truncated": True}


def _truncate_text(text: str, max_chars: int) -> str:
    text = str(text or "")
    return text if len(text) <= max_chars else text[:max_chars] + "...[truncated]"


def _shallow_compact_verifier_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Preserve verifier payload shape while bounding the largest channels."""

    data = dict(payload)
    data["instance_frame"] = _truncate(data.get("instance_frame"), 12000)
    execution_state = data.get("execution_state")
    if isinstance(execution_state, dict):
        compact_state = dict(execution_state)
        compact_state["history"] = _truncate(compact_state.get("history", [])[-6:], 9000)
        compact_state["resolved"] = _truncate(compact_state.get("resolved"), 9000)
        compact_state["effects"] = _truncate(compact_state.get("effects", [])[-12:], 9000)
        compact_state["claims"] = _truncate(compact_state.get("claims", [])[-16:], 12000)
        compact_state["recent_actions"] = _truncate(compact_state.get("recent_actions"), 9000)
        compact_state["evidence_inventory"] = _truncate(compact_state.get("evidence_inventory", [])[-30:], 12000)
        data["execution_state"] = compact_state
    data["cited_evidence_spans"] = _truncate(data.get("cited_evidence_spans", [])[:8], 18000)
    data["candidate_outcome"] = _truncate(data.get("candidate_outcome"), 6000)
    data["candidate_response"] = _truncate_text(str(data.get("candidate_response") or ""), 6000)
    return data


def _strip_think_blocks(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.IGNORECASE | re.DOTALL)


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


def _extract_first_json_object(text: str) -> str:
    start = text.find("{")
    if start < 0:
        return ""
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
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
                return text[start:index + 1]
    return ""
