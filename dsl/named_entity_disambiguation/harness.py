"""Deterministic named entity disambiguation DSL runner."""

import ast
import re
from collections.abc import Mapping as ABCMapping
from typing import Any, Callable, Dict, List, Mapping, Optional

from dsl.external_facing.actions import (
    evaluate_final_response,
    evaluate_intended_retrieval,
    evaluate_retrieved_evidence,
    render_refusal,
    render_unavailable_response,
)
from dsl.external_facing.harness import ExternalFacingDSLRunResult, ExternalFacingRouter
from dsl.named_entity_disambiguation.actions import (
    NEDCandidateSelection,
    NamedEntityDisambiguationState,
    extract_ned_slots_prompt,
    normalize_purchase_date_window,
    product_search_terms_for_extraction,
    is_generic_entity_phrase,
    query_current_customer,
    query_product_catalog,
    query_products_by_ids,
    query_purchase_history,
    render_ned_clarification_prompt,
    render_ned_response,
    respond_to_user,
    select_ned_candidate_prompt,
)
from dsl.named_entity_disambiguation.parser import (
    NamedEntityDisambiguationParseError,
    parse_ned_candidate_selection_json,
    parse_ned_clarification_json,
    parse_ned_extraction_json,
)
from dsl.named_entity_disambiguation.prompts import (
    NED_CANDIDATE_SELECTION_SYSTEM_PROMPT,
    NED_CLARIFICATION_SYSTEM_PROMPT,
    NED_SLOT_EXTRACTION_SYSTEM_PROMPT,
)


ModelExtractor = Callable[[List[Dict[str, str]]], str]


class NamedEntityDisambiguationDSLDriver:
    """Runs customer-scoped product/entity disambiguation."""

    def __init__(
        self,
        model_extractor: ModelExtractor,
        external_router: Optional[ExternalFacingRouter] = None,
        max_extraction_retries: int = 1,
        max_answer_turns: int = 4,
        max_clarification_turns: int = 3,
    ):
        self.model_extractor = model_extractor
        self.external_router = external_router
        self.max_extraction_retries = max_extraction_retries
        self.max_answer_turns = max_answer_turns
        self.max_clarification_turns = max_clarification_turns

    def run(
        self,
        env,
        task_index=None,
        initial_query: Optional[str] = None,
        initial_metadata: Any = None,
        initial_messages: Optional[List[Dict[str, str]]] = None,
    ) -> ExternalFacingDSLRunResult:
        """Execute scoped contact -> product search -> purchase retrieval -> selection."""
        if initial_query is None:
            query, metadata = env.reset(task_index=task_index)
            messages = [{"role": "user", "content": query.strip()}]
        else:
            query = initial_query
            metadata = initial_metadata
            messages = list(initial_messages or [{"role": "user", "content": query.strip()}])
        task_metadata = _task_metadata(metadata)
        info: Dict[str, Any] = {
            "dsl_enabled": True,
            "dsl_task_family": "named_entity_disambiguation",
            "symbolic_state_snapshots": [],
            "retrieved_objects": {},
            "query_errors": [],
            "model_calls": 0,
            "env_steps": 0,
            "metadata": metadata,
            "answer_turns": [],
            "external_gate_decisions": [],
        }

        conversation_text = query.strip()
        clarification_turns = 0
        final_result = None
        for turn in range(self.max_answer_turns):
            followup_response = self._gate_followup_request(
                query,
                conversation_text,
                turn,
                info,
            )
            if followup_response:
                return self._respond(env, messages, info, followup_response)

            state = self._extract_slots(query, conversation_text, task_metadata, messages, info)
            self._snapshot(info, "extract_ned_slots", state)

            if state.extraction and state.extraction.clarification_needed:
                if self._can_ask_user(env) and clarification_turns < self.max_clarification_turns:
                    clarification_turns += 1
                    question = self._render_clarification(
                        state,
                        conversation_text,
                        messages,
                        info,
                    )
                    result = self._respond(env, messages, info, question)
                    info.setdefault("clarification_turns", []).append(
                        {
                            "turn": clarification_turns,
                            "question": question,
                            "done": result.done,
                        }
                    )
                    if result.done:
                        return result
                    conversation_text = _conversation_from_messages(messages)
                    final_result = result
                    continue
                if self._can_ask_user(env):
                    info["clarification_exhausted"] = True
                    return self._respond(env, messages, info, render_unavailable_response())

            state = self._retrieve_customer_purchase_evidence(env, state, messages, info)
            self._snapshot(info, "retrieve_customer_purchase_evidence", state)
            if info.get("external_gate_refusal"):
                return self._respond(env, messages, info, info["external_gate_refusal"])
            state = self._select_candidate(state, messages, info)
            state.final_product_id = render_ned_response(state.selection)
            final_evidence = (
                ["own_purchase_history", "product_catalog"]
                if state.final_product_id != "None"
                else []
            )
            final_gate = evaluate_final_response(state.final_product_id, final_evidence)
            info["external_gate_decisions"].append(
                {
                    "stage": "final_response",
                    "evidence_classes": final_evidence,
                    "decision": final_gate.as_dict(),
                }
            )
            if not final_gate.allowed:
                state.final_product_id = render_refusal(final_gate.reason)
                info["external_gate_refusal"] = state.final_product_id
            info["named_entity_disambiguation_state"] = state.as_dict()
            self._snapshot(info, "select_ned_candidate", state)

            result = self._respond(env, messages, info, state.final_product_id)
            info["answer_turns"].append(
                {
                    "turn": turn + 1,
                    "answer": state.final_product_id,
                    "done": result.done,
                }
            )
            final_result = result
            if result.done:
                return result

            if (
                state.selection
                and state.selection.ambiguous
                and self._can_ask_user(env)
            ):
                if clarification_turns < self.max_clarification_turns:
                    clarification_turns += 1
                    question = self._render_clarification(
                        state,
                        conversation_text,
                        messages,
                        info,
                        clarification_requirements=state.selection.clarification_requirements,
                    )
                    result = self._respond(env, messages, info, question)
                    if result.done:
                        return result
                    final_result = result
                else:
                    info["clarification_exhausted"] = True
                    return self._respond(env, messages, info, render_unavailable_response())
            conversation_text = _conversation_from_messages(messages)

        if final_result is not None:
            return final_result
        return self._respond(env, messages, info, "None")

    def _gate_followup_request(
        self,
        task_query: str,
        conversation_text: str,
        turn: int,
        info: Dict[str, Any],
    ) -> str:
        """Re-run the external router on follow-up turns before NED continues."""
        if turn == 0 or self.external_router is None:
            return ""
        route = self.external_router.route(task_query.strip(), conversation_text)
        gate = self.external_router.gate_intended_retrieval(route)
        route_info = dict(self.external_router.last_info)
        route_info["driver"] = "named_entity_disambiguation"
        route_info["driver_turn"] = turn + 1
        route_info["pre_retrieval_gate"] = gate.as_dict()
        info.setdefault("external_router_followup_checks", []).append(route_info)
        if route.route == "named_entity_disambiguation" and gate.allowed:
            return ""
        if route.route in ("refuse", "unsupported") or not gate.allowed:
            info["external_gate_refusal"] = self.external_router.build_refusal(route)
            return info["external_gate_refusal"]
        if route.route == "clarify":
            return ""
        info["external_gate_refusal"] = render_unavailable_response()
        return info["external_gate_refusal"]


    def _extract_slots(
        self,
        task_query: str,
        conversation_text: str,
        task_metadata: Mapping[str, Any],
        messages: List[Dict[str, str]],
        info: Dict[str, Any],
    ) -> NamedEntityDisambiguationState:
        """Extract product/entity phrase and date expression."""
        state = NamedEntityDisambiguationState()
        state.customer_id = task_metadata.get("customer_id")
        state.today = task_metadata.get("today", "")
        prompt = extract_ned_slots_prompt(task_query, conversation_text, state.today)
        extractor_messages = [
            {"role": "system", "content": NED_SLOT_EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        last_error = None
        for attempt in range(self.max_extraction_retries + 1):
            output = self.model_extractor(extractor_messages)
            info["model_calls"] += 1
            info.setdefault("ned_slot_outputs", []).append(
                {"attempt": attempt + 1, "output": output}
            )
            print("NED DSL slot attempt {}: {!r}".format(attempt + 1, output), flush=True)
            messages.append(
                {
                    "role": "assistant",
                    "content": '<extract_ned_slots attempt="{}">{}</extract_ned_slots>'.format(
                        attempt + 1,
                        output,
                    ),
                }
            )
            try:
                state.extraction = parse_ned_extraction_json(output)
                state.date_window = normalize_purchase_date_window(
                    state.extraction,
                    state.today,
                )
                _apply_required_slot_checks(state)
                return state
            except NamedEntityDisambiguationParseError as exc:
                last_error = str(exc)
                extractor_messages.append({"role": "assistant", "content": output})
                extractor_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Invalid NED slot JSON: {}. Retry with exactly one JSON "
                            "object and no prose. Include entity_phrase, product_terms, "
                            "date_expression, period, interval_count, exact_purchase_date, "
                            "attributes, clarification_needed, and clarification_requirements."
                        ).format(last_error),
                    }
                )
        info["ned_slot_error"] = last_error
        return state

    def _retrieve_customer_purchase_evidence(
        self,
        env,
        state: NamedEntityDisambiguationState,
        messages: List[Dict[str, str]],
        info: Dict[str, Any],
    ) -> NamedEntityDisambiguationState:
        """Retrieve current-customer purchase/order history and product candidates."""
        if not state.customer_id or not state.extraction:
            return state

        contact_query = query_current_customer(state.customer_id)
        if not self._gate_retrieval(
            info,
            "query_current_customer",
            ["own_customer_profile"],
            "current_customer",
        ):
            return state
        contact_records = self._execute(
            env,
            contact_query,
            messages,
            info,
            "query_current_customer",
        ) if contact_query else []
        if not self._gate_retrieved(
            info,
            "query_current_customer",
            "own_customer_profile",
            contact_records,
        ):
            return state
        state.customer_records = _dedupe_records(contact_records)
        if state.customer_records:
            state.account_id = state.customer_records[0].get("AccountId")
        if not state.account_id:
            return state

        product_records = []
        for index, terms in enumerate(_product_search_inputs(state.extraction)[:4]):
            product_query = query_product_catalog(terms)
            action_name = "query_product_catalog:{}".format(index + 1)
            if not self._gate_retrieval(
                info,
                action_name,
                ["product_catalog"],
                "public",
            ):
                return state
            records = self._execute(
                env,
                product_query,
                messages,
                info,
                action_name,
            ) if product_query else []
            if not self._gate_retrieved(
                info,
                action_name,
                "product_catalog",
                records,
            ):
                return state
            product_records.extend(records)

        purchase_query = query_purchase_history(state.account_id, state.date_window)
        if not self._gate_retrieval(
            info,
            "query_purchase_history",
            ["own_purchase_history", "own_order_history"],
            "current_customer",
        ):
            return state
        purchase_records = self._execute(
            env,
            purchase_query,
            messages,
            info,
            "query_purchase_history",
        ) if purchase_query else []
        if not self._gate_retrieved(
            info,
            "query_purchase_history",
            "own_purchase_history",
            purchase_records,
        ):
            return state
        state.purchase_records = _dedupe_records(purchase_records)
        purchased_product_ids = _unique_product_ids(state.purchase_records)
        purchased_product_query = query_products_by_ids(purchased_product_ids)
        if not self._gate_retrieval(
            info,
            "query_purchased_products",
            ["product_catalog"],
            "public",
        ):
            return state
        purchased_product_records = self._execute(
            env,
            purchased_product_query,
            messages,
            info,
            "query_purchased_products",
        ) if purchased_product_query else []
        if not self._gate_retrieved(
            info,
            "query_purchased_products",
            "product_catalog",
            purchased_product_records,
        ):
            return state
        product_records.extend(purchased_product_records)
        state.product_candidates = _dedupe_records(product_records)
        return state

    def _gate_retrieval(
        self,
        info: Dict[str, Any],
        symbolic_action: str,
        evidence_classes: List[str],
        subject_scope: str,
    ) -> bool:
        decision = evaluate_intended_retrieval(evidence_classes, subject_scope)
        info["external_gate_decisions"].append(
            {
                "stage": "pre_retrieval",
                "symbolic_action": symbolic_action,
                "evidence_classes": evidence_classes,
                "subject_scope": subject_scope,
                "decision": decision.as_dict(),
            }
        )
        if not decision.allowed:
            info["external_gate_refusal"] = render_refusal(decision.reason)
            return False
        return True

    def _gate_retrieved(
        self,
        info: Dict[str, Any],
        symbolic_action: str,
        evidence_class: str,
        records: List[Mapping[str, Any]],
    ) -> bool:
        decision = evaluate_retrieved_evidence(evidence_class, records)
        info["external_gate_decisions"].append(
            {
                "stage": "post_retrieval",
                "symbolic_action": symbolic_action,
                "evidence_class": evidence_class,
                "record_count": len(records),
                "decision": decision.as_dict(),
            }
        )
        if not decision.allowed:
            info["external_gate_refusal"] = render_refusal(decision.reason)
            return False
        return True

    def _select_candidate(
        self,
        state: NamedEntityDisambiguationState,
        messages: List[Dict[str, str]],
        info: Dict[str, Any],
    ) -> NamedEntityDisambiguationState:
        """Select a Product2.Id only from eligible retrieved purchases."""
        if not state.extraction:
            state.selection = NEDCandidateSelection(
                selected_product_id=None,
                evidence="Slot extraction failed.",
                confidence="unknown",
            )
            return state
        allowed_ids = _unique_product_ids(state.purchase_records)
        if not allowed_ids:
            state.selection = NEDCandidateSelection(
                selected_product_id=None,
                evidence="No eligible current-customer purchase records matched the request.",
                confidence="high",
            )
            return state

        prompt = select_ned_candidate_prompt(
            state.extraction,
            state.date_window,
            state.purchase_records,
            state.product_candidates,
        )
        extractor_messages = [
            {"role": "system", "content": NED_CANDIDATE_SELECTION_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        last_error = None
        for attempt in range(self.max_extraction_retries + 1):
            output = self.model_extractor(extractor_messages)
            info["model_calls"] += 1
            info.setdefault("ned_selection_outputs", []).append(
                {"attempt": attempt + 1, "output": output}
            )
            print("NED DSL selection attempt {}: {!r}".format(attempt + 1, output), flush=True)
            messages.append(
                {
                    "role": "assistant",
                    "content": '<select_ned_candidate attempt="{}">{}</select_ned_candidate>'.format(
                        attempt + 1,
                        output,
                    ),
                }
            )
            try:
                state.selection = parse_ned_candidate_selection_json(
                    output,
                    allowed_product_ids=allowed_ids,
                )
                return state
            except NamedEntityDisambiguationParseError as exc:
                last_error = str(exc)
                extractor_messages.append({"role": "assistant", "content": output})
                extractor_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Invalid NED selection JSON: {}. Retry with exactly one JSON "
                            "object and no prose. selected_product_id must be one eligible "
                            "Product2Id from purchase_records or null."
                        ).format(last_error),
                    }
                )
        info["ned_selection_error"] = last_error
        state.selection = NEDCandidateSelection(
            selected_product_id=None,
            evidence="Candidate selection failed.",
            confidence="unknown",
        )
        return state

    def _render_clarification(
        self,
        state: NamedEntityDisambiguationState,
        conversation_text: str,
        messages: List[Dict[str, str]],
        info: Dict[str, Any],
        clarification_requirements: Optional[List[str]] = None,
    ) -> str:
        """Use the extractor model to phrase one clarification question."""
        missing = clarification_requirements
        if missing is None and state.extraction:
            missing = state.extraction.clarification_requirements
        missing = missing or []
        if not state.extraction:
            return respond_to_user(missing)

        prompt = render_ned_clarification_prompt(
            state.extraction,
            missing,
            conversation_text,
        )
        extractor_messages = [
            {"role": "system", "content": NED_CLARIFICATION_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        last_error = None
        for attempt in range(self.max_extraction_retries + 1):
            output = self.model_extractor(extractor_messages)
            info["model_calls"] += 1
            info.setdefault("ned_clarification_outputs", []).append(
                {"attempt": attempt + 1, "output": output}
            )
            print("NED DSL clarification attempt {}: {!r}".format(attempt + 1, output), flush=True)
            messages.append(
                {
                    "role": "assistant",
                    "content": '<render_ned_clarification attempt="{}">{}</render_ned_clarification>'.format(
                        attempt + 1,
                        output,
                    ),
                }
            )
            try:
                return parse_ned_clarification_json(output)
            except NamedEntityDisambiguationParseError as exc:
                last_error = str(exc)
                extractor_messages.append({"role": "assistant", "content": output})
                extractor_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Invalid NED clarification JSON: {}. Retry with exactly one "
                            "JSON object and no prose. Include only question, one "
                            "customer-facing question ending with '?'."
                        ).format(last_error),
                    }
                )
        info["ned_clarification_error"] = last_error
        return respond_to_user(missing)

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
            records = []
        else:
            records = _parse_records(observation)
        info["retrieved_objects"][symbolic_action] = {
            "query": query,
            "record_count": len(records),
            "records": records,
        }
        return records

    def _respond(
        self,
        env,
        messages: List[Dict[str, str]],
        info: Dict[str, Any],
        answer: str,
    ) -> ExternalFacingDSLRunResult:
        """Send final Product2.Id or None to the interactive environment."""
        action = {"name": "respond", "content": answer}
        messages.append({"role": "assistant", "content": "<respond>{}</respond>".format(answer)})
        observation, reward, done, step_info = env.step(action)
        info["env_steps"] += 1
        info["end_reason"] = step_info.get("end_reason", {})
        info["agent_actions"] = step_info.get("agent_actions", [])
        self._copy_resolution_timing(info, step_info)
        messages.append({"role": "user", "content": observation})
        return ExternalFacingDSLRunResult(reward=reward, done=done, messages=messages, info=info)

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
    def _snapshot(info: Dict[str, Any], event: str, state: NamedEntityDisambiguationState) -> None:
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


def _dedupe_records(records: List[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    seen = set()
    out = []
    for record in records:
        record_id = record.get("Id") if isinstance(record, ABCMapping) else None
        key = record_id or repr(sorted(record.items())) if isinstance(record, ABCMapping) else repr(record)
        if key in seen:
            continue
        seen.add(key)
        out.append(record)
    return out


def _unique_product_ids(records: List[Mapping[str, Any]]) -> List[str]:
    seen = set()
    out = []
    for record in records:
        product_id = record.get("Product2Id") if isinstance(record, ABCMapping) else None
        if product_id and product_id not in seen:
            seen.add(product_id)
            out.append(product_id)
    return out


def _product_search_inputs(extraction) -> List[List[str]]:
    inputs: List[List[str]] = []
    for term in extraction.product_terms:
        if term:
            inputs.append([term])
    if extraction.entity_phrase:
        inputs.append([extraction.entity_phrase])
    for attr in extraction.attributes:
        if attr and extraction.entity_phrase:
            inputs.append([attr, extraction.entity_phrase])
    if not inputs:
        inputs.append(product_search_terms_for_extraction(extraction))
    return inputs


def _apply_required_slot_checks(state: NamedEntityDisambiguationState) -> None:
    extraction = state.extraction
    if extraction is None:
        return
    missing = list(extraction.clarification_requirements)
    if is_generic_entity_phrase(extraction.entity_phrase) and not extraction.attributes:
        missing.append("product kind or distinguishing product attributes")
    if not state.date_window:
        missing.append("purchase date or timeframe")
    if missing:
        deduped = []
        seen = set()
        for item in missing:
            cleaned = str(item or "").strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                deduped.append(cleaned)
        extraction.clarification_needed = True
        extraction.clarification_requirements = deduped


def _conversation_from_messages(messages: List[Dict[str, str]]) -> str:
    user_chunks = []
    for message in messages:
        if message.get("role") != "user":
            continue
        content = (message.get("content") or "").strip()
        if not content or content.startswith("Salesforce instance output:"):
            continue
        user_chunks.append(content)
    return "\n".join(user_chunks)


def _task_metadata(metadata: Any) -> Mapping[str, Any]:
    if not isinstance(metadata, ABCMapping):
        return {}
    required = metadata.get("required")
    if isinstance(required, ABCMapping):
        return required
    if isinstance(required, str):
        parsed = _parse_required_metadata_text(required)
        if parsed:
            return parsed
    return metadata


def _parse_required_metadata_text(text: str) -> Mapping[str, Any]:
    out: Dict[str, Any] = {}
    contact = re.search(r"Contact\s+Id\s+interacting:\s*([A-Za-z0-9]{15,18})", text)
    if contact:
        out["customer_id"] = contact.group(1)
    today = re.search(r"Today's\s+date:\s*(\d{4}-\d{2}-\d{2})", text)
    if today:
        out["today"] = today.group(1)
    return out
