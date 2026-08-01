"""Deterministic case-routing DSL runner."""

import ast
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple

from dsl.case_routing.actions import (
    CaseRoutingSlots,
    CaseRoutingState,
    CandidateSelection,
    agents_with_max_count,
    agents_with_min_count,
    count_cases_by_owner,
    dedupe_records,
    extract_case_routing_slots_prompt,
    fallback_select_issue,
    fallback_select_product,
    filter_counts_to_agents,
    query_closed_cases_by_issue,
    query_closed_cases_by_order_items,
    query_issues,
    query_open_cases_by_agents,
    query_order_items_by_product,
    query_products_by_terms,
    render_agent_id_response,
    respond_to_user,
    select_best_issue_prompt,
    select_best_product_prompt,
)
from dsl.case_routing.parser import (
    CaseRoutingParseError,
    parse_candidate_selection_json,
    parse_case_routing_slots_json,
)
from dsl.case_routing.prompts import (
    CASE_ROUTING_CLARIFICATION_SYSTEM_PROMPT,
    CASE_ROUTING_ISSUE_SELECTION_SYSTEM_PROMPT,
    CASE_ROUTING_PRODUCT_SELECTION_SYSTEM_PROMPT,
    CASE_ROUTING_SLOT_EXTRACTION_SYSTEM_PROMPT,
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
    ):
        self.reward = reward
        self.done = done
        self.messages = messages
        self.info = info or {}


class CaseRoutingDSLDriver:
    """Runs the v1 case-routing symbolic pipeline.

    The official routing rubric is deterministic. The model only extracts
    natural-language slots and selects among retrieved Issue/Product candidates.
    """

    def __init__(
        self,
        model_extractor: ModelExtractor,
        max_extraction_retries: int = 1,
        clarification_generator: Optional[ClarificationGenerator] = None,
        max_clarification_turns: int = 2,
        max_product_searches: int = 5,
    ):
        self.model_extractor = model_extractor
        self.max_extraction_retries = max_extraction_retries
        self.clarification_generator = clarification_generator
        self.max_clarification_turns = max_clarification_turns
        self.max_product_searches = max_product_searches

    def run(self, env, task_index=None) -> DSLRunResult:
        query, metadata = env.reset(task_index=task_index)
        messages = [{"role": "user", "content": query.strip()}]
        info: Dict[str, Any] = {
            "dsl_enabled": True,
            "dsl_task_family": "case_routing",
            "symbolic_state_snapshots": [],
            "retrieved_objects": {},
            "query_errors": [],
            "model_calls": 0,
            "env_steps": 0,
            "metadata": metadata,
        }

        state = CaseRoutingState()
        slots, terminal_result = self._resolve_case_slots(env, query, messages, info)
        if terminal_result is not None:
            return terminal_result
        state.slots = slots
        info["case_routing_slots"] = slots.as_dict()
        self._snapshot(info, "extract_case_routing_slots", state)

        issue_records = self._execute(env, query_issues(), messages, info, "query_issues")
        state.issue_candidates = list(issue_records)
        state.selected_issue = self._select_issue(slots, state.issue_candidates, messages, info)
        self._snapshot(info, "select_issue", state)

        if state.selected_issue and state.selected_issue.selected_id:
            state.issue_cases = self._execute(
                env,
                query_closed_cases_by_issue(state.selected_issue.selected_id),
                messages,
                info,
                "query_closed_cases_by_issue",
            )
            state.issue_owner_counts = count_cases_by_owner(state.issue_cases)
        state.issue_tied_agent_ids = agents_with_max_count(state.issue_owner_counts)
        self._snapshot(info, "issue_expertise_counts", state)

        if len(state.issue_tied_agent_ids) == 1:
            return self._finish(env, messages, info, state, state.issue_tied_agent_ids[0], "issue_expertise")

        product_records = self._run_product_searches(env, slots, messages, info)
        state.product_candidates = product_records
        state.selected_product = self._select_product(slots, state.product_candidates, messages, info)
        self._snapshot(info, "select_product", state)

        if state.selected_product and state.selected_product.selected_id:
            state.order_items = self._execute(
                env,
                query_order_items_by_product(state.selected_product.selected_id),
                messages,
                info,
                "query_order_items_by_product",
            )
            order_item_ids = [item.get("Id") for item in state.order_items if item.get("Id")]
            product_case_query = query_closed_cases_by_order_items(order_item_ids)
            if product_case_query:
                state.product_cases = self._execute(
                    env,
                    product_case_query,
                    messages,
                    info,
                    "query_closed_cases_by_order_items",
                )
        raw_product_counts = count_cases_by_owner(state.product_cases)
        if state.issue_tied_agent_ids:
            state.product_owner_counts = filter_counts_to_agents(
                raw_product_counts,
                state.issue_tied_agent_ids,
            )
        else:
            state.product_owner_counts = raw_product_counts
        state.product_tied_agent_ids = agents_with_max_count(state.product_owner_counts)
        self._snapshot(info, "product_expertise_counts", state)

        if len(state.product_tied_agent_ids) == 1:
            return self._finish(
                env,
                messages,
                info,
                state,
                state.product_tied_agent_ids[0],
                "product_expertise",
            )

        workload_candidates = state.product_tied_agent_ids or state.issue_tied_agent_ids
        open_case_query = query_open_cases_by_agents(workload_candidates)
        if open_case_query:
            state.open_workload_cases = self._execute(
                env,
                open_case_query,
                messages,
                info,
                "query_open_cases_by_agents",
            )
        raw_workload_counts = count_cases_by_owner(state.open_workload_cases)
        state.workload_counts = filter_counts_to_agents(raw_workload_counts, workload_candidates)
        workload_winners = agents_with_min_count(state.workload_counts)
        self._snapshot(info, "workload_counts", state)

        selected_agent = workload_winners[0] if workload_winners else None
        return self._finish(env, messages, info, state, selected_agent, "workload")

    def _resolve_case_slots(
        self,
        env,
        initial_query: str,
        messages: List[Dict[str, str]],
        info: Dict[str, Any],
    ) -> Tuple[CaseRoutingSlots, Optional[DSLRunResult]]:
        conversation_text = initial_query
        slots = self._extract_case_slots(initial_query, conversation_text, messages, info)
        if slots.has_case_details():
            return slots, None

        info["missing_requirements"] = ["case_details"]
        if not self._can_ask_user(env):
            return slots, None

        for turn in range(self.max_clarification_turns):
            question = self._build_user_clarification(
                missing_requirement="case_details",
                conversation_text=conversation_text,
                info=info,
            )
            observation, reward, done, step_info = self._respond_to_user(
                env,
                messages,
                info,
                question,
                symbolic_action="request_case_details_clarification",
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
                return slots, DSLRunResult(reward=reward, done=done, messages=messages, info=info)
            conversation_text += "\n" + observation
            slots = self._extract_case_slots(initial_query, conversation_text, messages, info)
            if slots.has_case_details():
                return slots, None

        return slots, None

    def _extract_case_slots(
        self,
        task_query: str,
        conversation_text: str,
        messages: List[Dict[str, str]],
        info: Dict[str, Any],
    ) -> CaseRoutingSlots:
        prompt = extract_case_routing_slots_prompt(task_query, conversation_text)
        extractor_messages = [
            {"role": "system", "content": CASE_ROUTING_SLOT_EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        last_error = None
        for attempt in range(self.max_extraction_retries + 1):
            output = self.model_extractor(extractor_messages)
            info["model_calls"] += 1
            info.setdefault("slot_extraction_outputs", []).append(
                {"attempt": attempt + 1, "output": output}
            )
            print("Case DSL slot extraction attempt {}: {!r}".format(attempt + 1, output), flush=True)
            messages.append(
                {
                    "role": "assistant",
                    "content": '<extract_case_routing_slots attempt="{}">{}</extract_case_routing_slots>'.format(
                        attempt + 1,
                        output,
                    ),
                }
            )
            try:
                return parse_case_routing_slots_json(output)
            except CaseRoutingParseError as exc:
                last_error = str(exc)
                extractor_messages.append({"role": "assistant", "content": output})
                extractor_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Invalid case-routing slot JSON: {}. Retry with exactly one JSON "
                            "object and no prose. Include case_subject, case_description, "
                            "issue_summary, issue_search_terms, and product_search_terms."
                        ).format(last_error),
                    }
                )
        info["slot_extraction_error"] = last_error
        return CaseRoutingSlots()

    def _select_issue(
        self,
        slots: CaseRoutingSlots,
        candidates: List[Mapping[str, Any]],
        messages: List[Dict[str, str]],
        info: Dict[str, Any],
    ) -> CandidateSelection:
        if not candidates:
            return CandidateSelection(None, "unknown", "No Issue__c candidates were retrieved.")
        prompt = select_best_issue_prompt(slots, candidates)
        allowed_ids = [item.get("Id") for item in candidates if item.get("Id")]
        extractor_messages = [
            {"role": "system", "content": CASE_ROUTING_ISSUE_SELECTION_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        last_error = None
        for attempt in range(self.max_extraction_retries + 1):
            output = self.model_extractor(extractor_messages)
            info["model_calls"] += 1
            info.setdefault("issue_selection_outputs", []).append(
                {"attempt": attempt + 1, "output": output}
            )
            print("Case DSL issue selection attempt {}: {!r}".format(attempt + 1, output), flush=True)
            messages.append(
                {
                    "role": "assistant",
                    "content": '<select_best_issue attempt="{}">{}</select_best_issue>'.format(
                        attempt + 1,
                        output,
                    ),
                }
            )
            try:
                return parse_candidate_selection_json(output, allowed_ids=allowed_ids)
            except CaseRoutingParseError as exc:
                last_error = str(exc)
                extractor_messages.append({"role": "assistant", "content": output})
                extractor_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Invalid issue selection JSON: {}. Retry with exactly one JSON "
                            "object and no prose. selected_id must be one of the retrieved "
                            "Issue__c ids or null."
                        ).format(last_error),
                    }
                )
        info["issue_selection_error"] = last_error
        fallback = fallback_select_issue(slots, candidates)
        info["issue_selection_fallback"] = fallback.as_dict()
        return fallback

    def _run_product_searches(
        self,
        env,
        slots: CaseRoutingSlots,
        messages: List[Dict[str, str]],
        info: Dict[str, Any],
    ) -> List[Mapping[str, Any]]:
        search_inputs = list(slots.product_search_terms)
        if not search_inputs and slots.case_subject:
            search_inputs.append(slots.case_subject)
        records: List[Mapping[str, Any]] = []
        executions = []
        for index, term in enumerate(search_inputs[: self.max_product_searches]):
            query = query_products_by_terms([term])
            if not query:
                continue
            found = self._execute(
                env,
                query,
                messages,
                info,
                "query_products_by_terms:{}".format(index + 1),
            )
            executions.append({"terms": [term], "record_count": len(found)})
            records.extend(found)
        info["product_search_executions"] = executions
        return dedupe_records(records)

    def _select_product(
        self,
        slots: CaseRoutingSlots,
        candidates: List[Mapping[str, Any]],
        messages: List[Dict[str, str]],
        info: Dict[str, Any],
    ) -> CandidateSelection:
        if not candidates:
            return CandidateSelection(None, "unknown", "No Product2 candidates were retrieved.")
        prompt = select_best_product_prompt(slots, candidates)
        allowed_ids = [item.get("Id") for item in candidates if item.get("Id")]
        extractor_messages = [
            {"role": "system", "content": CASE_ROUTING_PRODUCT_SELECTION_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        last_error = None
        for attempt in range(self.max_extraction_retries + 1):
            output = self.model_extractor(extractor_messages)
            info["model_calls"] += 1
            info.setdefault("product_selection_outputs", []).append(
                {"attempt": attempt + 1, "output": output}
            )
            print("Case DSL product selection attempt {}: {!r}".format(attempt + 1, output), flush=True)
            messages.append(
                {
                    "role": "assistant",
                    "content": '<select_best_product attempt="{}">{}</select_best_product>'.format(
                        attempt + 1,
                        output,
                    ),
                }
            )
            try:
                return parse_candidate_selection_json(output, allowed_ids=allowed_ids)
            except CaseRoutingParseError as exc:
                last_error = str(exc)
                extractor_messages.append({"role": "assistant", "content": output})
                extractor_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Invalid product selection JSON: {}. Retry with exactly one JSON "
                            "object and no prose. selected_id must be one of the retrieved "
                            "Product2 ids or null."
                        ).format(last_error),
                    }
                )
        info["product_selection_error"] = last_error
        fallback = fallback_select_product(slots, candidates)
        info["product_selection_fallback"] = fallback.as_dict()
        return fallback

    def _execute(
        self,
        env,
        query: str,
        messages: List[Dict[str, str]],
        info: Dict[str, Any],
        symbolic_action: str,
    ) -> List[Mapping[str, Any]]:
        action = {"name": "execute", "content": query}
        messages.append({"role": "assistant", "content": "<execute>{}</execute>".format(query)})
        observation, _reward, _done, step_info = env.step(action)
        info["env_steps"] += 1
        messages.append({"role": "user", "content": "Salesforce instance output: {}".format(observation)})

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

    def _build_user_clarification(
        self,
        missing_requirement: str,
        conversation_text: str,
        info: Dict[str, Any],
    ) -> str:
        fallback = respond_to_user(missing_requirement)
        if self.clarification_generator is None:
            return fallback
        prompt_messages = [
            {"role": "system", "content": CASE_ROUTING_CLARIFICATION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Missing requirement: {missing}\n\n"
                    "Conversation so far:\n{conversation}\n\n"
                    "Ask one concise clarification question."
                ).format(missing=missing_requirement, conversation=conversation_text),
            },
        ]
        try:
            question = (self.clarification_generator(prompt_messages) or "").strip()
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
        messages.append({"role": "assistant", "content": "<respond_to_user>{}</respond_to_user>".format(content)})
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

    def _finish(
        self,
        env,
        messages: List[Dict[str, str]],
        info: Dict[str, Any],
        state: CaseRoutingState,
        agent_id: Optional[str],
        stage: str,
    ) -> DSLRunResult:
        state.final_agent_id = agent_id
        state.resolution_stage = stage
        info["final_agent_id"] = agent_id
        info["resolution_stage"] = stage
        info["case_routing_state"] = state.as_dict()
        self._snapshot(info, "final", state)
        return self._respond(env, messages, info, render_agent_id_response(agent_id))

    def _respond(
        self,
        env,
        messages: List[Dict[str, str]],
        info: Dict[str, Any],
        answer: str,
    ) -> DSLRunResult:
        action = {"name": "respond", "content": answer}
        messages.append({"role": "assistant", "content": "<respond>{}</respond>".format(answer)})
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
    def _snapshot(info: Dict[str, Any], event: str, state: CaseRoutingState) -> None:
        info["symbolic_state_snapshots"].append(
            {
                "event": event,
                "state": state.as_dict(),
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
