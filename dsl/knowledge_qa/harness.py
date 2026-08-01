"""Deterministic knowledge QA DSL runner."""

import ast
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
from dsl.knowledge_qa.actions import (
    KnowledgeQAState,
    classify_knowledge_selected_evidence_prompt,
    extract_knowledge_answer_prompt,
    extract_knowledge_search_plan_prompt,
    query_public_knowledge_articles,
    render_knowledge_answer_response,
    respond_to_user,
)
from dsl.knowledge_qa.parser import (
    KnowledgeQAParseError,
    parse_knowledge_answer_json,
    parse_knowledge_article_evidence_json,
    parse_knowledge_search_plan_json,
)
from dsl.knowledge_qa.prompts import (
    KNOWLEDGE_QA_ANSWER_EXTRACTOR_SYSTEM_PROMPT,
    KNOWLEDGE_QA_ARTICLE_EVIDENCE_SYSTEM_PROMPT,
    KNOWLEDGE_QA_SEARCH_PLANNER_SYSTEM_PROMPT,
)


ModelExtractor = Callable[[List[Dict[str, str]]], str]


class KnowledgeQADSLDriver:
    """Runs the customer-facing knowledge_qa symbolic workflow."""

    def __init__(
        self,
        model_extractor: ModelExtractor,
        external_router: Optional[ExternalFacingRouter] = None,
        max_extraction_retries: int = 1,
        max_answer_turns: int = 6,
        max_clarification_turns: int = 1,
        max_article_searches: int = 4,
    ):
        self.model_extractor = model_extractor
        self.external_router = external_router
        self.max_extraction_retries = max_extraction_retries
        self.max_answer_turns = max_answer_turns
        self.max_clarification_turns = max_clarification_turns
        self.max_article_searches = max_article_searches

    def run(
        self,
        env,
        task_index=None,
        initial_query: Optional[str] = None,
        initial_metadata: Any = None,
        initial_messages: Optional[List[Dict[str, str]]] = None,
    ) -> ExternalFacingDSLRunResult:
        """Execute route -> public article retrieval -> answer extraction."""
        if initial_query is None:
            query, metadata = env.reset(task_index=task_index)
            messages = [{"role": "user", "content": query.strip()}]
        else:
            query = initial_query
            metadata = initial_metadata
            messages = list(initial_messages or [{"role": "user", "content": query.strip()}])
        info: Dict[str, Any] = {
            "dsl_enabled": True,
            "dsl_task_family": "knowledge_qa",
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

            state = self._extract_search_plan(query, conversation_text, messages, info)
            self._snapshot(info, "extract_knowledge_search_plan", state)

            if state.search_plan and state.search_plan.clarification_needed:
                if self._can_ask_user(env) and clarification_turns < self.max_clarification_turns:
                    clarification_turns += 1
                    question = respond_to_user(state.search_plan.missing_information)
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

            state = self._retrieve_public_articles(env, state, messages, info)
            self._snapshot(info, "retrieve_public_knowledge_articles", state)
            if info.get("external_gate_refusal"):
                return self._respond(env, messages, info, info["external_gate_refusal"])
            state = self._extract_answer(state, messages, info)
            state.final_response = render_knowledge_answer_response(state.answer)
            state = self._gate_selected_answer_evidence(state, messages, info)
            self._snapshot(info, "classify_selected_knowledge_evidence", state)
            final_evidence_classes = self._final_evidence_classes(state)
            final_gate = evaluate_final_response(
                state.final_response,
                final_evidence_classes,
            )
            info["external_gate_decisions"].append(
                {
                    "stage": "final_response",
                    "evidence_classes": final_evidence_classes,
                    "decision": final_gate.as_dict(),
                }
            )
            if not final_gate.allowed:
                state.final_response = render_refusal(final_gate.reason)
                info["external_gate_refusal"] = state.final_response
            info["knowledge_qa_state"] = state.as_dict()
            self._snapshot(info, "extract_knowledge_answer", state)

            result = self._respond(env, messages, info, state.final_response)
            info["answer_turns"].append(
                {
                    "turn": turn + 1,
                    "answer": state.final_response,
                    "done": result.done,
                }
            )
            final_result = result
            if result.done:
                return result
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
        """Re-run the external router on follow-up turns before KQA continues."""
        if turn == 0 or self.external_router is None:
            return ""
        route = self.external_router.route(task_query.strip(), conversation_text)
        gate = self.external_router.gate_intended_retrieval(route)
        route_info = dict(self.external_router.last_info)
        route_info["driver"] = "knowledge_qa"
        route_info["driver_turn"] = turn + 1
        route_info["pre_retrieval_gate"] = gate.as_dict()
        info.setdefault("external_router_followup_checks", []).append(route_info)
        if route.route == "knowledge_qa" and gate.allowed:
            return ""
        if route.route in ("refuse", "unsupported") or not gate.allowed:
            info["external_gate_refusal"] = self.external_router.build_refusal(route)
            return info["external_gate_refusal"]
        if route.route == "clarify":
            return ""
        info["external_gate_refusal"] = render_unavailable_response()
        return info["external_gate_refusal"]


    def _extract_search_plan(
        self,
        task_query: str,
        conversation_text: str,
        messages: List[Dict[str, str]],
        info: Dict[str, Any],
    ) -> KnowledgeQAState:
        """Extract normalized question and deterministic article search terms."""
        state = KnowledgeQAState()
        prompt = extract_knowledge_search_plan_prompt(task_query, conversation_text)
        extractor_messages = [
            {"role": "system", "content": KNOWLEDGE_QA_SEARCH_PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        last_error = None
        for attempt in range(self.max_extraction_retries + 1):
            output = self.model_extractor(extractor_messages)
            info["model_calls"] += 1
            info.setdefault("search_plan_outputs", []).append(
                {"attempt": attempt + 1, "output": output}
            )
            print("Knowledge QA DSL search plan attempt {}: {!r}".format(attempt + 1, output), flush=True)
            messages.append(
                {
                    "role": "assistant",
                    "content": '<extract_knowledge_search_plan attempt="{}">{}</extract_knowledge_search_plan>'.format(
                        attempt + 1,
                        output,
                    ),
                }
            )
            try:
                state.search_plan = parse_knowledge_search_plan_json(output)
                return state
            except KnowledgeQAParseError as exc:
                last_error = str(exc)
                extractor_messages.append({"role": "assistant", "content": output})
                extractor_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Invalid knowledge search-plan JSON: {}. Retry with exactly one "
                            "JSON object and no prose. Include normalized_question, "
                            "search_terms, product_terms, clarification_needed, and "
                            "missing_information."
                        ).format(last_error),
                    }
                )
        info["search_plan_error"] = last_error
        return state

    def _retrieve_public_articles(
        self,
        env,
        state: KnowledgeQAState,
        messages: List[Dict[str, str]],
        info: Dict[str, Any],
    ) -> KnowledgeQAState:
        """Retrieve public Knowledge__kav records using compiled queries."""
        plan = state.search_plan
        if plan is None:
            return state
        search_inputs = _search_inputs_for_plan(plan)
        articles = []
        executions = []
        for index, terms in enumerate(search_inputs[: self.max_article_searches]):
            gate = evaluate_intended_retrieval(
                ["public_knowledge_article"],
                "public",
            )
            info["external_gate_decisions"].append(
                {
                    "stage": "pre_retrieval",
                    "symbolic_action": "query_public_knowledge_articles:{}".format(index + 1),
                    "evidence_classes": ["public_knowledge_article"],
                    "subject_scope": "public",
                    "decision": gate.as_dict(),
                }
            )
            if not gate.allowed:
                info["external_gate_refusal"] = render_refusal(gate.reason)
                return state
            query = query_public_knowledge_articles(terms)
            if not query:
                continue
            records = self._execute(
                env,
                query,
                messages,
                info,
                "query_public_knowledge_articles:{}".format(index + 1),
            )
            retrieved_gate = evaluate_retrieved_evidence(
                "public_knowledge_article",
                records,
            )
            info["external_gate_decisions"].append(
                {
                    "stage": "post_retrieval",
                    "symbolic_action": "query_public_knowledge_articles:{}".format(index + 1),
                    "evidence_class": "public_knowledge_article",
                    "record_count": len(records),
                    "decision": retrieved_gate.as_dict(),
                }
            )
            if not retrieved_gate.allowed:
                info["external_gate_refusal"] = render_refusal(retrieved_gate.reason)
                return state
            executions.append({"terms": list(terms), "record_count": len(records)})
            articles.extend(records)
        state.knowledge_articles = _dedupe_records(articles)
        info["knowledge_article_search_executions"] = executions
        return state

    def _gate_selected_answer_evidence(
        self,
        state: KnowledgeQAState,
        messages: List[Dict[str, str]],
        info: Dict[str, Any],
    ) -> KnowledgeQAState:
        """Classify selected answer evidence before the final response is sent."""
        if (
            not state.search_plan
            or not state.answer
            or state.final_response == "None"
            or not state.answer.selected_article_ids
        ):
            return state
        selected_ids = [article_id for article_id in state.answer.selected_article_ids if article_id]
        prompt = classify_knowledge_selected_evidence_prompt(
            state.search_plan,
            state.answer,
            state.knowledge_articles,
        )
        extractor_messages = [
            {"role": "system", "content": KNOWLEDGE_QA_ARTICLE_EVIDENCE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        last_error = None
        classifications = None
        for attempt in range(self.max_extraction_retries + 1):
            output = self.model_extractor(extractor_messages)
            info["model_calls"] += 1
            info.setdefault("selected_evidence_outputs", []).append(
                {"attempt": attempt + 1, "output": output}
            )
            print("Knowledge QA DSL selected evidence attempt {}: {!r}".format(attempt + 1, output), flush=True)
            messages.append(
                {
                    "role": "assistant",
                    "content": '<classify_selected_knowledge_evidence attempt="{}">{}</classify_selected_knowledge_evidence>'.format(
                        attempt + 1,
                        output,
                    ),
                }
            )
            try:
                classifications = parse_knowledge_article_evidence_json(
                    output,
                    allowed_article_ids=selected_ids,
                )
                break
            except KnowledgeQAParseError as exc:
                last_error = str(exc)
                extractor_messages.append({"role": "assistant", "content": output})
                extractor_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Invalid selected knowledge evidence JSON: {}. Retry with "
                            "exactly one JSON object and no prose. Include article_evidence "
                            "for selected article ids using only fixed evidence_type "
                            "and subject_scope labels."
                        ).format(last_error),
                    }
                )
        if classifications is None:
            info["selected_evidence_error"] = last_error
            info["external_gate_refusal"] = render_refusal(
                "Could not verify whether selected knowledge evidence is safe."
            )
            state.final_response = info["external_gate_refusal"]
            return state

        state.article_evidence = classifications
        evidence_by_id = {evidence.article_id: evidence for evidence in classifications}
        blocked_evidence = []
        for article_id in selected_ids:
            evidence = evidence_by_id.get(article_id)
            if evidence is None:
                blocked_evidence.append(
                    {"article_id": article_id, "reason": "missing selected evidence classification"}
                )
                continue
            gate = evaluate_intended_retrieval(
                [
                    {
                        "evidence_type": evidence.evidence_type,
                        "subject_scope": evidence.subject_scope,
                    }
                ],
                evidence.subject_scope,
            )
            info["external_gate_decisions"].append(
                {
                    "stage": "article_evidence",
                    "article_id": article_id,
                    "evidence_type": evidence.evidence_type,
                    "subject_scope": evidence.subject_scope,
                    "safe_to_use": evidence.safe_to_use,
                    "decision": gate.as_dict(),
                }
            )
            if not (gate.allowed and evidence.safe_to_use):
                blocked_evidence.append(
                    {
                        "article_id": article_id,
                        "evidence_type": evidence.evidence_type,
                        "subject_scope": evidence.subject_scope,
                        "safe_to_use": evidence.safe_to_use,
                        "reason": evidence.reason,
                        "gate": gate.as_dict(),
                    }
                )
        info["selected_knowledge_evidence"] = [
            evidence.as_dict() for evidence in classifications
        ]
        info["blocked_selected_knowledge_evidence"] = blocked_evidence
        if blocked_evidence:
            info["external_gate_refusal"] = render_refusal(
                "Selected knowledge evidence was classified as disallowed."
            )
            state.final_response = info["external_gate_refusal"]
        return state


    def _extract_answer(
        self,
        state: KnowledgeQAState,
        messages: List[Dict[str, str]],
        info: Dict[str, Any],
    ) -> KnowledgeQAState:
        """Extract grounded answer from retrieved articles."""
        if not state.search_plan:
            return state
        if not state.knowledge_articles:
            from dsl.knowledge_qa.actions import KnowledgeQAAnswer

            state.answer = KnowledgeQAAnswer(
                question_type="description",
                asked_focus=state.search_plan.normalized_question,
                candidate_answer_spans=[],
                answer="None",
                selected_article_ids=[],
                evidence="No public knowledge articles were retrieved.",
                confidence="unknown",
            )
            return state
        prompt = extract_knowledge_answer_prompt(state.search_plan, state.knowledge_articles)
        allowed_ids = [article.get("Id") for article in state.knowledge_articles if article.get("Id")]
        extractor_messages = [
            {"role": "system", "content": KNOWLEDGE_QA_ANSWER_EXTRACTOR_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        last_error = None
        for attempt in range(self.max_extraction_retries + 1):
            output = self.model_extractor(extractor_messages)
            info["model_calls"] += 1
            info.setdefault("answer_extraction_outputs", []).append(
                {"attempt": attempt + 1, "output": output}
            )
            print("Knowledge QA DSL answer attempt {}: {!r}".format(attempt + 1, output), flush=True)
            messages.append(
                {
                    "role": "assistant",
                    "content": '<extract_knowledge_answer attempt="{}">{}</extract_knowledge_answer>'.format(
                        attempt + 1,
                        output,
                    ),
                }
            )
            try:
                state.answer = parse_knowledge_answer_json(output, allowed_article_ids=allowed_ids)
                return state
            except KnowledgeQAParseError as exc:
                last_error = str(exc)
                extractor_messages.append({"role": "assistant", "content": output})
                extractor_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Invalid knowledge answer JSON: {}. Retry with exactly one JSON "
                            "object and no prose. Include question_type, asked_focus, "
                            "candidate_answer_spans, answer, selected_article_ids, evidence, "
                            "and confidence. selected_article_ids and span article_id values "
                            "must be retrieved Knowledge__kav ids or empty."
                        ).format(last_error),
                    }
                )
        info["answer_extraction_error"] = last_error
        from dsl.knowledge_qa.actions import KnowledgeQAAnswer

        state.answer = KnowledgeQAAnswer(
            question_type="description",
            asked_focus=state.search_plan.normalized_question,
            candidate_answer_spans=[],
            answer="None",
            selected_article_ids=[],
            evidence="Answer extraction failed.",
            confidence="unknown",
        )
        return state

    @staticmethod
    def _final_evidence_classes(state: KnowledgeQAState) -> List[str]:
        if state.final_response == "None" or not state.answer:
            return []
        evidence_by_id = {
            evidence.article_id: evidence.evidence_type
            for evidence in state.article_evidence
        }
        classes = []
        for article_id in state.answer.selected_article_ids:
            evidence_type = evidence_by_id.get(article_id, "public_knowledge_article")
            if evidence_type not in classes:
                classes.append(evidence_type)
        if not classes and state.final_response != "None":
            classes.append("public_knowledge_article")
        return classes


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
        """Send final answer to the interactive environment."""
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
    def _snapshot(info: Dict[str, Any], event: str, state: KnowledgeQAState) -> None:
        info["symbolic_state_snapshots"].append(
            {
                "event": event,
                "state": state.as_dict(),
            }
        )


def _search_inputs_for_plan(plan) -> List[List[str]]:
    inputs: List[List[str]] = []
    for term in plan.search_terms:
        if term:
            inputs.append([term])
    if plan.product_terms:
        inputs.append(list(plan.product_terms))
    if not inputs and plan.normalized_question:
        inputs.append([plan.normalized_question])
    return inputs


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
