"""Deterministic quote approval DSL runner."""

import ast
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple

from dsl.quote_approval.actions import (
    ArticleExtraction,
    DiscountPolicyStructure,
    PolicySearchIntent,
    QuoteApprovalState,
    article_extraction_from_discount_evaluation,
    apply_article_policy_judgment,
    dedupe_articles,
    dedupe_policy_searches,
    default_policy_searches,
    derive_quote_facts,
    extract_article_evidence_prompt,
    extract_discount_policy_structure_prompt,
    extract_policy_search_plan_prompt,
    extract_target_quote_id,
    evaluate_discount_policy,
    evaluate_discount_policy_structure,
    has_discount_or_volume_facts,
    is_discount_policy_article,
    query_account,
    query_contact,
    query_knowledge_articles,
    query_line_items,
    query_opportunity,
    query_pricebook_entries,
    query_pricebook_entries_by_ids,
    query_products_by_ids,
    query_quote,
    render_failed_quote_response,
    respond_to_user,
)
from dsl.quote_approval.parser import (
    QuoteApprovalParseError,
    parse_article_json,
    parse_discount_policy_structure_json,
    parse_policy_search_plan_json,
)
from dsl.quote_approval.prompts import (
    QUOTE_APPROVAL_CLARIFICATION_SYSTEM_PROMPT,
    QUOTE_ARTICLE_EVIDENCE_SYSTEM_PROMPT,
    QUOTE_DISCOUNT_POLICY_STRUCTURE_SYSTEM_PROMPT,
    QUOTE_POLICY_SEARCH_PLANNER_SYSTEM_PROMPT,
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


class QuoteApprovalDSLDriver:
    """Runs the v1 quote-approval symbolic pipeline.

    Direct quote evidence is retrieved deterministically. The LLM is used only
    for bounded policy-search planning and Knowledge article policy judgment.
    """

    def __init__(
        self,
        model_extractor: ModelExtractor,
        max_extraction_retries: int = 1,
        clarification_generator: Optional[ClarificationGenerator] = None,
        max_clarification_turns: int = 2,
        max_policy_searches: int = 12,
        max_followup_searches: int = 4,
    ):
        self.model_extractor = model_extractor
        self.max_extraction_retries = max_extraction_retries
        self.clarification_generator = clarification_generator
        self.max_clarification_turns = max_clarification_turns
        self.max_policy_searches = max_policy_searches
        self.max_followup_searches = max_followup_searches

    def run(self, env, task_index=None) -> DSLRunResult:
        query, metadata = env.reset(task_index=task_index)
        messages = [{"role": "user", "content": query.strip()}]
        info: Dict[str, Any] = {
            "dsl_enabled": True,
            "dsl_task_family": "quote_approval",
            "symbolic_state_snapshots": [],
            "retrieved_objects": {},
            "query_errors": [],
            "model_calls": 0,
            "env_steps": 0,
            "metadata": metadata,
        }

        state = QuoteApprovalState()
        quote_id, terminal_result = self._resolve_target_quote_id(env, query, messages, info)
        if terminal_result is not None:
            return terminal_result
        state.quote_id = quote_id
        info["target_quote_id"] = quote_id
        if not quote_id:
            info["missing_requirements"] = ["target_quote_id"]
            return self._respond(env, messages, info, "None")

        quote_records = self._execute(env, query_quote(quote_id), messages, info, "query_quote")
        if not quote_records:
            info["missing_requirements"] = ["quote_record"]
            info["final_article_id"] = None
            self._snapshot(info, "quote_not_found", state)
            return self._respond(env, messages, info, "None")
        state.quote = quote_records[0]

        line_items = self._execute(
            env,
            query_line_items(quote_id),
            messages,
            info,
            "query_line_items",
        )
        state.line_items = list(line_items)

        product_ids = [item.get("Product2Id") for item in line_items if item.get("Product2Id")]
        product_query = query_products_by_ids(product_ids)
        product_records = (
            self._execute(env, product_query, messages, info, "query_products_by_ids")
            if product_query
            else []
        )
        state.products = list(product_records)

        pricebook_entry_ids = [
            item.get("PricebookEntryId") for item in line_items if item.get("PricebookEntryId")
        ]
        pricebook_query = query_pricebook_entries_by_ids(pricebook_entry_ids)
        if not pricebook_query:
            pricebook_query = query_pricebook_entries(product_ids)
        pricebook_records = (
            self._execute(env, pricebook_query, messages, info, "query_pricebook_entries")
            if pricebook_query
            else []
        )
        state.pricebook_entries = list(pricebook_records)

        opportunity_records = self._execute_optional(
            env,
            query_opportunity((state.quote or {}).get("OpportunityId")),
            messages,
            info,
            "query_opportunity",
        )
        account_records = self._execute_optional(
            env,
            query_account((state.quote or {}).get("AccountId")),
            messages,
            info,
            "query_account",
        )
        contact_records = self._execute_optional(
            env,
            query_contact((state.quote or {}).get("ContactId")),
            messages,
            info,
            "query_contact",
        )
        state.opportunity = opportunity_records[0] if opportunity_records else None
        state.account = account_records[0] if account_records else None
        state.contact = contact_records[0] if contact_records else None

        state.quote_facts = derive_quote_facts(
            quote_records,
            line_items,
            product_records,
            pricebook_records,
            opportunity_records,
            account_records,
            contact_records,
        )
        self._snapshot(info, "derive_quote_facts", state)

        planned_searches = self._extract_policy_search_plan(query, state, messages, info)
        state.policy_searches = self._merge_policy_searches(default_policy_searches(state), planned_searches)
        self._snapshot(info, "plan_policy_searches", state)

        state.knowledge_articles = self._run_policy_searches(
            env,
            state.policy_searches[: self.max_policy_searches],
            messages,
            info,
        )
        extraction = self._extract_article_state_discount_first(query, state, messages, info)
        self._snapshot(info, "extract_article_evidence", state)

        if (
            state.final_article_id is None
            and extraction.additional_searches
            and self.max_followup_searches > 0
        ):
            followups = self._merge_policy_searches([], extraction.additional_searches)
            followup_articles = self._run_policy_searches(
                env,
                followups[: self.max_followup_searches],
                messages,
                info,
            )
            state.knowledge_articles = dedupe_articles(list(state.knowledge_articles) + followup_articles)
            info["followup_policy_search_count"] = len(followups[: self.max_followup_searches])
            extraction = self._extract_article_state(query, state, messages, info)
            apply_article_policy_judgment(state, extraction)
            self._snapshot(info, "extract_article_evidence_followup", state)

        final_answer = render_failed_quote_response(state)
        info["final_article_id"] = None if final_answer == "None" else final_answer
        info["quote_approval_state"] = state.as_dict()
        return self._respond(env, messages, info, final_answer)

    def _resolve_target_quote_id(
        self,
        env,
        initial_query: str,
        messages: List[Dict[str, str]],
        info: Dict[str, Any],
    ) -> Tuple[Optional[str], Optional[DSLRunResult]]:
        quote_id = extract_target_quote_id(initial_query)
        if quote_id:
            return quote_id, None

        info["missing_requirements"] = ["target_quote_id"]
        if not self._can_ask_user(env):
            return None, None

        conversation_text = initial_query
        for turn in range(self.max_clarification_turns):
            question = self._build_user_clarification(
                missing_requirement="target_quote_id",
                conversation_text=conversation_text,
                info=info,
            )
            observation, reward, done, step_info = self._respond_to_user(
                env,
                messages,
                info,
                question,
                symbolic_action="request_target_quote_clarification",
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
            quote_id = extract_target_quote_id(observation)
            if quote_id:
                return quote_id, None

        return None, None

    def _execute_optional(
        self,
        env,
        query: Optional[str],
        messages: List[Dict[str, str]],
        info: Dict[str, Any],
        symbolic_action: str,
    ) -> List[Mapping[str, Any]]:
        if not query:
            return []
        return self._execute(env, query, messages, info, symbolic_action)

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

    def _extract_policy_search_plan(
        self,
        task_query: str,
        state: QuoteApprovalState,
        messages: List[Dict[str, str]],
        info: Dict[str, Any],
    ) -> List[PolicySearchIntent]:
        prompt = extract_policy_search_plan_prompt(task_query, state)
        extractor_messages = [
            {"role": "system", "content": QUOTE_POLICY_SEARCH_PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        last_error = None
        for attempt in range(self.max_extraction_retries + 1):
            output = self.model_extractor(extractor_messages)
            info["model_calls"] += 1
            info.setdefault("policy_search_planner_outputs", []).append(
                {"attempt": attempt + 1, "output": output}
            )
            print("Quote DSL policy search attempt {}: {!r}".format(attempt + 1, output), flush=True)
            messages.append(
                {
                    "role": "assistant",
                    "content": (
                        '<plan_policy_searches attempt="{}">{}</plan_policy_searches>'.format(
                            attempt + 1,
                            output,
                        )
                    ),
                }
            )
            try:
                return parse_policy_search_plan_json(output)
            except QuoteApprovalParseError as exc:
                last_error = str(exc)
                extractor_messages.append({"role": "assistant", "content": output})
                extractor_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Invalid quote policy search JSON: {}. Retry with exactly one JSON "
                            "object and no prose. Include a searches list with dimension, terms, "
                            "and reason. Do not output SOQL or SOSL."
                        ).format(last_error),
                    }
                )
        info["policy_search_plan_error"] = last_error
        return []

    def _run_policy_searches(
        self,
        env,
        searches: Iterable[PolicySearchIntent],
        messages: List[Dict[str, str]],
        info: Dict[str, Any],
    ) -> List[Mapping[str, Any]]:
        articles: List[Mapping[str, Any]] = []
        executed = []
        for index, search in enumerate(searches):
            query = query_knowledge_articles(search.terms)
            if not query:
                continue
            records = self._execute(
                env,
                query,
                messages,
                info,
                "query_knowledge_articles:{}:{}".format(index + 1, search.dimension),
            )
            executed.append({"search": search.as_dict(), "record_count": len(records)})
            articles.extend(records)
        info.setdefault("policy_search_executions", []).extend(executed)
        return dedupe_articles(articles)

    def _extract_article_state(
        self,
        task_query: str,
        state: QuoteApprovalState,
        messages: List[Dict[str, str]],
        info: Dict[str, Any],
    ) -> ArticleExtraction:
        prompt = extract_article_evidence_prompt(task_query, state, state.knowledge_articles)
        allowed_article_ids = [
            article.get("Id") for article in state.knowledge_articles if article.get("Id")
        ]
        extractor_messages = [
            {"role": "system", "content": QUOTE_ARTICLE_EVIDENCE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        last_error = None
        for attempt in range(self.max_extraction_retries + 1):
            output = self.model_extractor(extractor_messages)
            info["model_calls"] += 1
            info.setdefault("article_evidence_outputs", []).append(
                {"attempt": attempt + 1, "output": output}
            )
            print("Quote DSL article evidence attempt {}: {!r}".format(attempt + 1, output), flush=True)
            messages.append(
                {
                    "role": "assistant",
                    "content": (
                        '<extract_article_evidence attempt="{}">{}</extract_article_evidence>'.format(
                            attempt + 1,
                            output,
                        )
                    ),
                }
            )
            try:
                return parse_article_json(output, allowed_article_ids=allowed_article_ids)
            except QuoteApprovalParseError as exc:
                last_error = str(exc)
                extractor_messages.append({"role": "assistant", "content": output})
                extractor_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Invalid quote article JSON: {}. Retry with exactly one JSON object "
                            "and no prose. selected_article_id must be a candidate Knowledge__kav "
                            "Id or None. judgments must contain article_id, dimension, status, "
                            "rule_summary, and evidence."
                        ).format(last_error),
                    }
                )
        info["article_extraction_error"] = last_error
        return ArticleExtraction()

    def _extract_article_state_discount_first(
        self,
        task_query: str,
        state: QuoteApprovalState,
        messages: List[Dict[str, str]],
        info: Dict[str, Any],
    ) -> ArticleExtraction:
        """Evaluate volume/discount policy before lower-priority policy families."""

        all_articles = list(state.knowledge_articles)
        discount_articles = [
            article for article in all_articles if is_discount_policy_article(article)
        ]
        if has_discount_or_volume_facts(state) and discount_articles:
            deterministic_discount = self._evaluate_discount_articles(
                state,
                discount_articles,
                messages,
                info,
            )
            info.setdefault("deterministic_discount_policy_evaluations", []).append(
                deterministic_discount.as_dict()
            )
            if deterministic_discount.article_id:
                discount_extraction = article_extraction_from_discount_evaluation(
                    deterministic_discount
                )
                state.knowledge_articles = all_articles
                apply_article_policy_judgment(state, discount_extraction)
                state.article_extraction = discount_extraction
                info["discount_first_article_ids"] = [
                    article.get("Id") for article in discount_articles if article.get("Id")
                ]
                info["discount_first_result"] = (
                    "deterministic_discount_violation"
                    if deterministic_discount.violated
                    else "deterministic_discount_no_violation"
                )
                return discount_extraction

            state.knowledge_articles = discount_articles
            discount_extraction = self._extract_article_state(task_query, state, messages, info)
            apply_article_policy_judgment(state, discount_extraction)
            info["discount_first_article_ids"] = [
                article.get("Id") for article in discount_articles if article.get("Id")
            ]
            if state.final_article_id:
                state.knowledge_articles = all_articles
                state.article_extraction = discount_extraction
                return discount_extraction
            info["discount_first_result"] = "no_discount_violation_selected"
            state.knowledge_articles = all_articles

        extraction = self._extract_article_state(task_query, state, messages, info)
        apply_article_policy_judgment(state, extraction)
        return extraction

    def _evaluate_discount_articles(
        self,
        state: QuoteApprovalState,
        discount_articles: List[Mapping[str, Any]],
        messages: List[Dict[str, str]],
        info: Dict[str, Any],
    ):
        structures = []
        clean_evaluations = []
        for article in discount_articles:
            structure = self._extract_discount_policy_structure(article, state, messages, info)
            if structure is None:
                continue
            structures.append(structure)
            evaluation = evaluate_discount_policy_structure(state, structure)
            clean_evaluations.append(evaluation)
            info.setdefault("discount_policy_structures", []).append(structure.as_dict())
            info.setdefault("discount_policy_structure_evaluations", []).append(
                evaluation.as_dict()
            )
            if evaluation.violated:
                return evaluation

        if clean_evaluations:
            info["discount_policy_fallback_used"] = False
            return clean_evaluations[0]

        fallback = evaluate_discount_policy(state, discount_articles)
        if fallback.violated:
            info["discount_policy_fallback_used"] = True
        return fallback

    def _extract_discount_policy_structure(
        self,
        article: Mapping[str, Any],
        state: QuoteApprovalState,
        messages: List[Dict[str, str]],
        info: Dict[str, Any],
    ) -> Optional[DiscountPolicyStructure]:
        prompt = extract_discount_policy_structure_prompt(state, article)
        article_id = article.get("Id")
        extractor_messages = [
            {"role": "system", "content": QUOTE_DISCOUNT_POLICY_STRUCTURE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        last_error = None
        for attempt in range(self.max_extraction_retries + 1):
            output = self.model_extractor(extractor_messages)
            info["model_calls"] += 1
            info.setdefault("discount_policy_structure_outputs", []).append(
                {"attempt": attempt + 1, "article_id": article_id, "output": output}
            )
            print(
                "Quote DSL discount policy structure attempt {}: {!r}".format(
                    attempt + 1,
                    output,
                ),
                flush=True,
            )
            messages.append(
                {
                    "role": "assistant",
                    "content": (
                        '<extract_discount_policy_structure attempt="{}">{}</extract_discount_policy_structure>'.format(
                            attempt + 1,
                            output,
                        )
                    ),
                }
            )
            try:
                return parse_discount_policy_structure_json(
                    output,
                    allowed_article_ids=[article_id] if article_id else None,
                )
            except QuoteApprovalParseError as exc:
                last_error = str(exc)
                extractor_messages.append({"role": "assistant", "content": output})
                extractor_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Invalid discount policy structure JSON: {}. Retry with exactly one "
                            "JSON object and no prose. Include article_id, policy_type, basis, "
                            "application, scope, tiers, rule_confidence, and notes."
                        ).format(last_error),
                    }
                )
        info.setdefault("discount_policy_structure_errors", []).append(
            {"article_id": article_id, "error": last_error}
        )
        return None

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
            {"role": "system", "content": QUOTE_APPROVAL_CLARIFICATION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Missing requirement: {}\n\n"
                    "Conversation so far:\n{}\n\n"
                    "Ask one concise clarification question."
                ).format(missing_requirement, conversation_text),
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
        messages.append(
            {"role": "assistant", "content": "<respond_to_user>{}</respond_to_user>".format(content)}
        )
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
        messages.append({"role": "assistant", "content": "<respond>{}</respond>".format(answer)})
        observation, reward, done, step_info = env.step(action)
        info["env_steps"] += 1

        info["end_reason"] = step_info.get("end_reason", {})
        info["agent_actions"] = step_info.get("agent_actions", [])
        self._copy_resolution_timing(info, step_info)
        messages.append({"role": "user", "content": observation})
        return DSLRunResult(reward=reward, done=done, messages=messages, info=info)

    def _merge_policy_searches(
        self,
        deterministic: Iterable[PolicySearchIntent],
        planned: Iterable[PolicySearchIntent],
    ) -> List[PolicySearchIntent]:
        return dedupe_policy_searches(list(deterministic) + list(planned))

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
    def _snapshot(info: Dict[str, Any], event: str, state: QuoteApprovalState) -> None:
        info["symbolic_state_snapshots"].append(
            {
                "event": event,
                "state": state.as_dict(),
                "final_article_id": state.final_article_id,
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
