"""Deterministic lead qualification DSL runner."""

import ast
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from dsl.lead_qualification.actions import (
    BANT_FACTORS,
    BANTState,
    TimelinePolicyJudgment,
    apply_deterministic_overrides,
    apply_timeline_policy_judgment,
    compute_budget_total,
    extract_bant_evidence_prompt,
    extract_target_lead_id,
    extract_timeline_policy_judgment_prompt,
    query_installation_policy,
    query_lead,
    query_pricebook_entries,
    query_products_by_name,
    query_voice_call_transcripts,
    render_failed_bant_response,
    respond_to_user,
)
from dsl.lead_qualification.parser import (
    BANTParseError,
    parse_bant_json,
    parse_timeline_policy_judgment_json,
)
from dsl.lead_qualification.prompts import (
    LEAD_QUALIFICATION_BANT_EXTRACTOR_SYSTEM_PROMPT,
    LEAD_QUALIFICATION_CLARIFICATION_SYSTEM_PROMPT,
    LEAD_QUALIFICATION_TIMELINE_POLICY_SYSTEM_PROMPT,
)


ModelExtractor = Callable[[List[Dict[str, str]]], str]
ClarificationGenerator = Callable[[List[Dict[str, str]]], str]


class DSLRunResult:
    def __init__(
        self,
        reward: float,
        done: bool,
        messages: List[Dict[str, str]],
        info: Optional[Dict[str, Any]] = None,
    ) -> TimelinePolicyJudgment:
        self.reward = reward
        self.done = done
        self.messages = messages
        self.info = info or {}


class LeadQualificationDSLDriver:
    """Runs the v1 lead-qualification symbolic pipeline.

    Control flow is deterministic. Semantic model calls are bounded extractors
    that must return strict JSON.
    """

    def __init__(
        self,
        model_extractor: ModelExtractor,
        max_extraction_retries: int = 1,
        clarification_generator: Optional[ClarificationGenerator] = None,
        max_clarification_turns: int = 2,
    ):
        self.model_extractor = model_extractor
        self.max_extraction_retries = max_extraction_retries
        self.clarification_generator = clarification_generator
        self.max_clarification_turns = max_clarification_turns

    def run(self, env, task_index=None) -> DSLRunResult:
        query, metadata = env.reset(task_index=task_index)
        messages = [{"role": "user", "content": query.strip()}]
        info: Dict[str, Any] = {
            "dsl_enabled": True,
            "dsl_task_family": "lead_qualification",
            "symbolic_state_snapshots": [],
            "retrieved_objects": {},
            "query_errors": [],
            "model_calls": 0,
            "env_steps": 0,
            "metadata": metadata,
        }

        lead_id, terminal_result = self._resolve_target_lead_id(env, query, messages, info)
        if terminal_result is not None:
            return terminal_result
        info["target_lead_id"] = lead_id
        if not lead_id:
            info["missing_requirements"] = ["target_lead_id"]
            return self._respond(env, messages, info, "None")

        lead_records = self._execute(env, query_lead(lead_id), messages, info, "query_lead")
        transcript_records = self._execute(
            env,
            query_voice_call_transcripts(lead_id),
            messages,
            info,
            "query_voice_call_transcripts",
        )

        state = self._extract_bant_state(query, lead_records, transcript_records, messages, info)
        self._snapshot(info, "extract_bant_evidence", state)

        product_records: List[Mapping[str, Any]] = []
        if self._needs_pricing(state):
            product_query = query_products_by_name(state.product_names or state.quantities.keys())
            if product_query:
                product_records = self._execute(
                    env,
                    product_query,
                    messages,
                    info,
                    "query_products_by_name",
                )
                product_ids = [record.get("Id") for record in product_records if record.get("Id")]
                price_query = query_pricebook_entries(product_ids)
                if price_query:
                    pricebook_records = self._execute(
                        env,
                        price_query,
                        messages,
                        info,
                        "query_pricebook_entries",
                    )
                    state.computed_total = compute_budget_total(
                        product_records,
                        pricebook_records,
                        state.quantities,
                    )
                    info["computed_total"] = (
                        str(state.computed_total) if state.computed_total is not None else None
                    )
                    apply_deterministic_overrides(state)
                    self._snapshot(info, "compute_budget_total", state)

        if self._has_strong_seller_timeline_commitment(state):
            state.factors["Timeline"].status = "supported"
            state.factors["Timeline"].evidence = (
                state.seller_timeline_feasibility
                or state.factors["Timeline"].evidence
                or "Seller made a concrete commitment to the customer's requested timeline."
            )
            info["timeline_policy_skipped"] = {
                "reason": "strong_seller_timeline_commitment",
                "seller_timeline_feasibility": state.seller_timeline_feasibility,
            }
            self._snapshot(info, "skip_installation_policy_strong_seller_commitment", state)
        elif self._needs_installation_policy(state):
            policy_records = self._execute(
                env,
                query_installation_policy(),
                messages,
                info,
                "query_installation_policy",
            )
            state.installation_policy = list(policy_records)
            judgment = self._extract_timeline_policy_judgment(
                state,
                policy_records,
                messages,
                info,
            )
            apply_timeline_policy_judgment(state, judgment)
            info["required_installation_days"] = judgment.required_installation_days
            info["timeline_policy_evidence"] = judgment.policy_evidence
            self._snapshot(info, "query_installation_policy", state)

        final_answer = render_failed_bant_response(state)
        info["final_failed_factors"] = [] if final_answer == "None" else final_answer.split(", ")
        info["extraction_json"] = state.as_dict()
        return self._respond(env, messages, info, final_answer)

    def _resolve_target_lead_id(
        self,
        env,
        initial_query: str,
        messages: List[Dict[str, str]],
        info: Dict[str, Any],
    ) -> Tuple[Optional[str], Optional[DSLRunResult]]:
        lead_id = extract_target_lead_id(initial_query)
        if lead_id:
            return lead_id, None

        info["missing_requirements"] = ["target_lead_id"]
        if not self._can_ask_user(env):
            return None, None

        conversation_text = initial_query
        for turn in range(self.max_clarification_turns):
            question = self._build_user_clarification(
                missing_requirement="target_lead_id",
                conversation_text=conversation_text,
                info=info,
            )
            observation, reward, done, step_info = self._respond_to_user(
                env,
                messages,
                info,
                question,
                symbolic_action="request_target_lead_clarification",
            )
            info.setdefault("clarification_turns", []).append(
                {
                    "turn": turn + 1,
                    "question": question,
                    "observation": observation,
                    "done": done,
                }
            )
            if done:
                info["end_reason"] = step_info.get("end_reason", {})
                info["agent_actions"] = step_info.get("agent_actions", [])
                self._copy_resolution_timing(info, step_info)
                return None, DSLRunResult(reward=reward, done=done, messages=messages, info=info)

            conversation_text += "\n" + observation
            lead_id = extract_target_lead_id(observation)
            if lead_id:
                return lead_id, None

        return None, None

    def _execute(
        self,
        env,
        query: str,
        messages: List[Dict[str, str]],
        info: Dict[str, Any],
        symbolic_action: str,
    ) -> List[Mapping[str, Any]]:
        action = {"name": "execute", "content": query}
        messages.append({"role": "assistant", "content": f"<execute>{query}</execute>"})
        observation, _reward, _done, step_info = env.step(action)
        info["env_steps"] += 1
        messages.append({"role": "user", "content": f"Salesforce instance output: {observation}"})

        if step_info.get("end_reason", {}).get("message") == "SOQL/SOSL query error":
            info["query_errors"].append(
                {
                    "symbolic_action": symbolic_action,
                    "query": query,
                    "error": step_info["end_reason"].get("content"),
                }
            )
            records: List[Mapping[str, Any]] = []
        else:
            records = _parse_records(observation)
        info["retrieved_objects"][symbolic_action] = {
            "query": query,
            "record_count": len(records),
            "records": records,
        }
        return records

    def _extract_bant_state(
        self,
        task_query: str,
        lead_records: List[Mapping[str, Any]],
        transcript_records: List[Mapping[str, Any]],
        messages: List[Dict[str, str]],
        info: Dict[str, Any],
    ) -> BANTState:
        prompt = extract_bant_evidence_prompt(task_query, lead_records, transcript_records)
        extractor_messages = [
            {
                "role": "system",
                "content": LEAD_QUALIFICATION_BANT_EXTRACTOR_SYSTEM_PROMPT,
            },
            {"role": "user", "content": prompt},
        ]
        last_error = None
        for attempt in range(self.max_extraction_retries + 1):
            output = self.model_extractor(extractor_messages)
            info["model_calls"] += 1
            info.setdefault("extractor_outputs", []).append(
                {
                    "attempt": attempt + 1,
                    "output": output,
                }
            )
            print(f"Lead DSL extractor attempt {attempt + 1}: {output!r}", flush=True)
            messages.append(
                {
                    "role": "assistant",
                    "content": f"<extract_bant_evidence attempt=\"{attempt + 1}\">{output}</extract_bant_evidence>",
                }
            )
            try:
                return parse_bant_json(output)
            except BANTParseError as exc:
                last_error = str(exc)
                extractor_messages.append({"role": "assistant", "content": output})
                extractor_messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Invalid BANT JSON: {last_error}. Retry with exactly one JSON object "
                            "and no prose. Do not include a reasoning field, multi-step analysis, "
                            "bullet lists, markdown, or prose outside the JSON. The JSON must contain "
                            "Budget, Authority, Need, and Timeline, each with status and evidence."
                        ),
                    }
                )

        info["extraction_error"] = last_error
        return BANTState()

    def _extract_timeline_policy_judgment(
        self,
        state: BANTState,
        policy_records: List[Mapping[str, Any]],
        messages: List[Dict[str, str]],
        info: Dict[str, Any],
    ):
        prompt = extract_timeline_policy_judgment_prompt(state, policy_records)
        extractor_messages = [
            {
                "role": "system",
                "content": LEAD_QUALIFICATION_TIMELINE_POLICY_SYSTEM_PROMPT,
            },
            {"role": "user", "content": prompt},
        ]
        last_error = None
        for attempt in range(self.max_extraction_retries + 1):
            output = self.model_extractor(extractor_messages)
            info["model_calls"] += 1
            info.setdefault("timeline_policy_outputs", []).append(
                {
                    "attempt": attempt + 1,
                    "output": output,
                }
            )
            print(f"Lead DSL timeline policy attempt {attempt + 1}: {output!r}", flush=True)
            messages.append(
                {
                    "role": "assistant",
                    "content": (
                        f"<extract_timeline_policy_judgment attempt=\"{attempt + 1}\">"
                        f"{output}</extract_timeline_policy_judgment>"
                    ),
                }
            )
            try:
                return parse_timeline_policy_judgment_json(output)
            except BANTParseError as exc:
                last_error = str(exc)
                extractor_messages.append({"role": "assistant", "content": output})
                extractor_messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Invalid Timeline policy JSON: {last_error}. Retry with exactly one JSON "
                            "object and no prose. Do not include a reasoning field, multi-step analysis, "
                            "bullet lists, markdown, or prose outside the JSON. The JSON must contain "
                            "required_installation_days, policy_evidence, and Timeline with status "
                            "and evidence."
                        ),
                    }
                )

        info["timeline_policy_extraction_error"] = last_error
        return TimelinePolicyJudgment(
            required_installation_days=None,
            policy_evidence="",
            timeline_status=state.factors["Timeline"].status,
            timeline_evidence=state.factors["Timeline"].evidence,
        )

    def _build_user_clarification(
        self,
        missing_requirement: str,
        conversation_text: str,
        info: Dict[str, Any],
    ) -> str:
        fallback = respond_to_user(missing_requirement)
        if self.clarification_generator is None:
            return fallback

        messages = [
            {
                "role": "system",
                "content": LEAD_QUALIFICATION_CLARIFICATION_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": (
                    f"Missing requirement: {missing_requirement}\n\n"
                    f"Conversation so far:\n{conversation_text}\n\n"
                    "Ask one concise clarification question."
                ),
            },
        ]
        try:
            question = (self.clarification_generator(messages) or "").strip()
        except Exception as exc:
            info.setdefault("clarification_errors", []).append(str(exc))
            return fallback
        info["model_calls"] += 1
        return question or fallback

    def _respond_to_user(
        self,
        env,
        messages: List[Dict[str, str]],
        info: Dict[str, Any],
        content: str,
        symbolic_action: str,
    ) -> Tuple[str, float, bool, Dict[str, Any]]:
        action = {"name": "respond", "content": content}
        messages.append({"role": "assistant", "content": f"<respond_to_user>{content}</respond_to_user>"})
        observation, reward, done, step_info = env.step(action)
        info["env_steps"] += 1
        info.setdefault("user_responses", []).append(
            {
                "symbolic_action": symbolic_action,
                "content": content,
                "observation": observation,
                "done": done,
            }
        )
        messages.append({"role": "user", "content": observation})
        if done:
            self._copy_resolution_timing(info, step_info)
        return observation, reward, done, step_info

    def _respond(
        self,
        env,
        messages: List[Dict[str, str]],
        info: Dict[str, Any],
        answer: str,
    ) -> DSLRunResult:
        action = {"name": "respond", "content": answer}
        messages.append({"role": "assistant", "content": f"<respond>{answer}</respond>"})
        observation, reward, done, step_info = env.step(action)
        info["env_steps"] += 1

        info["end_reason"] = step_info.get("end_reason", {})
        info["agent_actions"] = step_info.get("agent_actions", [])
        self._copy_resolution_timing(info, step_info)
        messages.append({"role": "user", "content": observation})
        return DSLRunResult(reward=reward, done=done, messages=messages, info=info)

    @staticmethod
    def _copy_resolution_timing(info: Dict[str, Any], step_info: Mapping[str, Any]) -> None:
        for key in (
            "time_to_resolution_seconds",
            "interaction_start_time",
            "interaction_end_time",
        ):
            if key in step_info:
                info[key] = step_info[key]

    @staticmethod
    def _can_ask_user(env) -> bool:
        return hasattr(env, "user")

    @staticmethod
    def _needs_pricing(state: BANTState) -> bool:
        if state.budget_amount is None:
            return False
        return bool(state.product_names or state.quantities)

    @staticmethod
    def _needs_installation_policy(state: BANTState) -> bool:
        return state.requested_timeline_days is not None

    @staticmethod
    def _has_strong_seller_timeline_commitment(state: BANTState) -> bool:
        return (
            state.requested_timeline_days is not None
            and state.seller_timeline_commitment_strength == "strong"
        )

    @staticmethod
    def _snapshot(info: Dict[str, Any], event: str, state: BANTState) -> None:
        info["symbolic_state_snapshots"].append(
            {
                "event": event,
                "state": state.as_dict(),
                "failed_factors": [
                    factor for factor in BANT_FACTORS if state.factors[factor].status == "failed"
                ],
            }
        )


def _parse_records(observation: Any) -> List[Mapping[str, Any]]:
    if isinstance(observation, list):
        return observation
    if not isinstance(observation, str):
        return []
    try:
        parsed = ast.literal_eval(observation)
    except (SyntaxError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []
