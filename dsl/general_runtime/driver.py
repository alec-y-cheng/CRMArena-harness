"""Canonical spec-driven general runtime driver."""

import re
from typing import Any, Callable, Dict, List, Mapping, Optional

from dsl.external_facing.actions import render_refusal, render_unavailable_response
from dsl.external_facing.harness import ExternalFacingDSLRunResult, ExternalFacingRouter
from dsl.general_runtime.executor import RuntimeExecutor, execute_driver_action
from dsl.general_runtime.io import (
    can_ask_user,
    conversation_from_messages,
    dedupe_records,
    execute_env,
    init_runtime_info,
    respond_env,
    snapshot_state,
    unique_record_values,
)
from dsl.general_runtime.parser import (
    RuntimeParseError,
    parse_answer_candidate_json,
    parse_disclosure_gate_json,
    parse_instance_frame_json,
)
from dsl.general_runtime.privacy import gate_external_router_followup, gate_final_response, gate_retrieval, gate_retrieved
from dsl.general_runtime.prompts import (
    DISCLOSURE_GATE_SYSTEM_PROMPT,
    GENERIC_EXTRACTION_SYSTEM_PROMPT,
    INSTANCE_FRAME_SYSTEM_PROMPT,
    build_disclosure_gate_prompt,
    build_generic_extraction_prompt,
    build_instance_frame_prompt,
)
from dsl.general_runtime.state import EvidenceItem, ExecutionState, InstanceFrame
from dsl.general_runtime.workflow_specs import load_workflow_spec
from dsl.knowledge_qa.actions import query_public_knowledge_articles
from dsl.named_entity_disambiguation.actions import (
    query_current_customer,
    query_product_catalog,
    query_products_by_ids,
    query_purchase_history,
)

ModelExtractor = Callable[[List[Dict[str, str]]], str]


class CanonicalGeneralRuntimeDriver:
    """One shared loop driven by WorkflowSpec contracts and generic actions."""

    def __init__(
        self,
        workflow_id: str,
        model_extractor: ModelExtractor,
        external_router: Optional[ExternalFacingRouter] = None,
        max_extraction_retries: int = 1,
        max_answer_turns: int = 4,
        max_clarification_turns: int = 1,
    ):
        self.workflow_spec = load_workflow_spec(workflow_id)
        self.model_extractor = model_extractor
        self.external_router = external_router
        self.max_extraction_retries = max_extraction_retries
        self.max_answer_turns = max_answer_turns
        self.max_clarification_turns = max_clarification_turns
        self.executor = RuntimeExecutor()
        self.executor.register("retrieve_knowledge", self._handle_retrieve_knowledge)
        self.executor.register("query_current_customer", self._handle_query_current_customer)
        self.executor.register("query_product_catalog", self._handle_query_product_catalog)
        self.executor.register("query_purchase_history", self._handle_query_purchase_history)
        self.executor.register("query_opportunity_by_id", self._handle_query_opportunity_by_id)
        self.executor.register("query_opportunity_activities", self._handle_query_opportunity_activities)
        self.executor.register("query_opportunity_commercial_context", self._handle_query_opportunity_commercial_context)
        self.executor.register("query_case_by_id", self._handle_query_case_by_id)
        self.executor.register("query_case_interactions", self._handle_query_case_interactions)
        self.executor.register("query_case_linked_context", self._handle_query_case_linked_context)
        self.executor.register("query_internal_policy_articles", self._handle_query_internal_policy_articles)
        self.executor.register("extract_claims", self._handle_extract_claims)
        self.executor.register("disclosure_gate", self._handle_disclosure_gate)
        self.executor.register("classify_selected_evidence", self._handle_classify_selected_evidence)
        self.executor.register("render_answer", self._handle_render_answer)
        self.executor.register("refuse", self._handle_refuse)
        self.executor.register("pause_for_clarification", self._handle_pause_for_clarification)

    def run(
        self,
        env,
        task_index=None,
        initial_query: Optional[str] = None,
        initial_metadata: Any = None,
        initial_messages: Optional[List[Dict[str, str]]] = None,
    ) -> ExternalFacingDSLRunResult:
        if initial_query is None:
            query, metadata = env.reset(task_index=task_index)
            messages = [{"role": "user", "content": query.strip()}]
        else:
            query = initial_query
            metadata = initial_metadata
            messages = list(initial_messages or [{"role": "user", "content": query.strip()}])

        state = ExecutionState(self.workflow_spec, conversation_history=messages)
        info = init_runtime_info(self.workflow_spec.task_family, self.workflow_spec.workflow_id, metadata)
        state.runtime_data["env"] = env
        state.runtime_data["messages"] = messages
        state.runtime_data["info"] = info
        state.runtime_data["metadata"] = _task_metadata(metadata)
        conversation_text = query.strip()
        clarification_turns = 0
        final_result = None
        clarification_policy = self.workflow_spec.clarification_policy
        max_clarification_turns = int(clarification_policy.get("max_turns", self.max_clarification_turns))

        for turn in range(self.max_answer_turns):
            followup_response = gate_external_router_followup(
                self.external_router,
                query,
                conversation_text,
                turn,
                info,
                allowed_route=self.workflow_spec.task_family,
                driver_name="canonical_general_runtime",
            )
            if followup_response:
                return respond_env(env, messages, info, followup_response)

            self._frame_instance(state, conversation_text, info, messages)
            snapshot_state(info, "frame_instance", state)

            if state.instance_frame and state.instance_frame.clarification_requirements:
                fallback = str(clarification_policy.get("fallback_when_exhausted") or "unavailable")
                if can_ask_user(env) and clarification_turns < max_clarification_turns:
                    clarification_turns += 1
                    execute_driver_action(
                        self.executor,
                        state,
                        "pause_for_clarification",
                        {"clarification_requirements": state.instance_frame.clarification_requirements},
                    )
                    result = respond_env(env, messages, info, state.clarification_prompt)
                    info.setdefault("clarification_turns", []).append(
                        {"turn": clarification_turns, "question": state.clarification_prompt, "done": result.done}
                    )
                    if result.done:
                        return result
                    state.completion_state = "running"
                    conversation_text = conversation_from_messages(messages)
                    final_result = result
                    continue
                if fallback == "search_with_available_evidence":
                    info.setdefault("clarification_fallbacks", []).append(
                        {
                            "clarification_requirements": list(state.instance_frame.clarification_requirements),
                            "fallback": fallback,
                        }
                    )
                    state.instance_frame.clarification_requirements = []
                elif can_ask_user(env):
                    info["clarification_exhausted"] = True
                    return respond_env(env, messages, info, render_unavailable_response())

            self._acquire_evidence(state)
            snapshot_state(info, "acquire_evidence", state)
            if info.get("external_gate_refusal"):
                return respond_env(env, messages, info, info["external_gate_refusal"])

            execute_driver_action(self.executor, state, "extract_claims", self._default_action_args(state, "extract_claims"))
            if self._uses_privacy_gates():
                execute_driver_action(self.executor, state, "disclosure_gate", self._default_action_args(state, "disclosure_gate"))
                execute_driver_action(self.executor, state, "classify_selected_evidence", self._default_action_args(state, "classify_selected_evidence"))
            execute_driver_action(self.executor, state, "render_answer", self._default_action_args(state, "render_answer"))
            snapshot_state(info, "render_answer", state)

            if info.get("external_gate_refusal"):
                state.final_answer = info["external_gate_refusal"]
            info["general_runtime_state"] = state.as_dict()
            result = respond_env(env, messages, info, state.final_answer)
            info["answer_turns"].append({"turn": turn + 1, "answer": state.final_answer, "done": result.done})
            final_result = result
            if result.done:
                return result
            conversation_text = conversation_from_messages(messages)

        if final_result is not None:
            return final_result
        return respond_env(env, messages, info, "None")

    def _frame_instance(self, state: ExecutionState, conversation_text: str, info: Dict[str, Any], messages: List[Dict[str, str]]) -> None:
        state.runtime_data["user_visible_conversation_history"] = _user_visible_conversation_history(messages)
        extractor_messages = [
            {"role": "system", "content": INSTANCE_FRAME_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_instance_frame_prompt(
                    self.workflow_spec,
                    conversation_text,
                    metadata=state.runtime_data.get("metadata", {}),
                    conversation_history=state.runtime_data["user_visible_conversation_history"],
                ),
            },
        ]
        last_error = None
        for attempt in range(self.max_extraction_retries + 1):
            output = self.model_extractor(extractor_messages)
            info["model_calls"] += 1
            state.model_calls += 1
            info.setdefault("instance_frame_outputs", []).append({"attempt": attempt + 1, "output": output})
            messages.append({"role": "assistant", "content": '<frame_instance attempt="{}">{}</frame_instance>'.format(attempt + 1, output)})
            try:
                frame = parse_instance_frame_json(output)
                if frame.workflow_id != self.workflow_spec.workflow_id:
                    raise RuntimeParseError("workflow_id does not match active WorkflowSpec")
                state.instance_frame = frame
                _apply_required_instance_fields(state)
                state.current_phase = "acquire_evidence_or_clarify"
                return
            except RuntimeParseError as exc:
                last_error = str(exc)
                extractor_messages.append({"role": "assistant", "content": output})
                extractor_messages.append({"role": "user", "content": "Invalid InstanceFrame JSON: {}. Retry with exactly one JSON object and no prose.".format(last_error)})
        info["instance_frame_error"] = last_error
        state.instance_frame = InstanceFrame(workflow_id=self.workflow_spec.workflow_id, request_summary=conversation_text)
        _apply_required_instance_fields(state)

    def _acquire_evidence(self, state: ExecutionState) -> None:
        for action in self.workflow_spec.allowed_action_categories.get("environment", []):
            execute_driver_action(self.executor, state, action, self._default_action_args(state, action))
            if state.runtime_data["info"].get("external_gate_refusal"):
                return

    def _default_action_args(self, state: ExecutionState, action: str) -> Dict[str, Any]:
        frame = state.instance_frame
        if action == "retrieve_knowledge":
            return {"search_terms": list(frame.query_terms if frame else [])}
        if action == "query_current_customer":
            return {"customer_id": _customer_id_from_state(state)}
        if action == "query_product_catalog":
            return {"product_terms": _product_terms_from_frame(frame)}
        if action == "query_purchase_history":
            return {
                "search_terms_or_timeframe": list(_date_window_from_frame(frame) or []),
                "date_window": list(_date_window_from_frame(frame) or []),
            }
        if action == "query_opportunity_by_id":
            return {"opportunity_id": _target_id_from_state(state, "Opportunity")}
        if action == "query_opportunity_activities":
            return {"opportunity_id": _target_id_from_state(state, "Opportunity")}
        if action == "query_opportunity_commercial_context":
            return {"opportunity_id": _target_id_from_state(state, "Opportunity")}
        if action == "query_case_by_id":
            return {"case_id": _target_id_from_state(state, "Case")}
        if action == "query_case_interactions":
            return {"case_id": _target_id_from_state(state, "Case")}
        if action == "query_case_linked_context":
            return {"case_id": _target_id_from_state(state, "Case")}
        if action == "query_internal_policy_articles":
            return {"search_terms": _policy_search_terms_from_state(state)}
        if action == "extract_claims":
            return {
                "requirements": state.workflow_spec.requirement_names(),
                "evidence_items": [item.as_dict() for item in state.evidence_items],
            }
        if action == "classify_selected_evidence":
            return {"selected_evidence": list(state.selected_evidence)}
        if action == "disclosure_gate":
            return {"answer_candidate": dict(state.answer_candidate or {})}
        if action == "render_answer":
            return {"answer_candidate": dict(state.answer_candidate or {})}
        return {}

    def _uses_privacy_gates(self) -> bool:
        if self.workflow_spec.request_scope == "external_customer":
            return True
        for phase in self.workflow_spec.phases.values():
            checkpoints = phase.get("required_checkpoints", []) if isinstance(phase, Mapping) else []
            if "evidence_privacy_gate" in checkpoints:
                return True
        return False

    def _handle_retrieve_knowledge(self, state: ExecutionState, arguments: Mapping[str, Any]) -> None:
        env = state.runtime_data["env"]
        messages = state.runtime_data["messages"]
        info = state.runtime_data["info"]
        frame = state.instance_frame
        if not frame:
            return
        records: List[Mapping[str, Any]] = []
        executions = []
        search_inputs = [[term] for term in frame.query_terms if term]
        if not search_inputs and frame.request_summary:
            search_inputs = [[frame.request_summary]]
        for index, terms in enumerate(search_inputs[:4]):
            action_name = "retrieve_knowledge:{}".format(index + 1)
            if not gate_retrieval(info, action_name, ["public_knowledge_article"], "public"):
                return
            query = query_public_knowledge_articles(terms)
            if not query:
                continue
            result_records = execute_env(env, query, messages, info, action_name)
            if not gate_retrieved(info, action_name, "public_knowledge_article", result_records):
                return
            records.extend(result_records)
            executions.append({"terms": list(terms), "record_count": len(result_records)})
        records = dedupe_records(records)
        existing_records = state.retrieved_records.get("Knowledge__kav", [])
        records = dedupe_records(existing_records + records)
        state.retrieved_records["Knowledge__kav"] = [dict(item) for item in records]
        state.evidence_items = _merge_evidence_items(
            state.evidence_items,
            [
                EvidenceItem(str(item.get("Id") or ""), "public_knowledge_article", "Knowledge__kav", item, "public")
                for item in records
            ],
        )
        state.env_calls = info["env_steps"]
        info["knowledge_article_search_executions"] = executions

    def _handle_query_current_customer(self, state: ExecutionState, arguments: Mapping[str, Any]) -> None:
        env = state.runtime_data["env"]
        messages = state.runtime_data["messages"]
        info = state.runtime_data["info"]
        customer_id = str(arguments.get("customer_id") or _customer_id_from_state(state) or "")
        if not customer_id:
            return
        if not gate_retrieval(info, "query_current_customer", ["current_customer_profile"], "current_customer"):
            return
        query = query_current_customer(customer_id)
        records = execute_env(env, query, messages, info, "query_current_customer") if query else []
        if not gate_retrieved(info, "query_current_customer", "current_customer_profile", records):
            return
        records = dedupe_records(records)
        state.retrieved_records["Contact"] = [dict(item) for item in records]
        if records:
            state.runtime_data["current_customer_account_id"] = records[0].get("AccountId")
        state.env_calls = info["env_steps"]

    def _handle_query_product_catalog(self, state: ExecutionState, arguments: Mapping[str, Any]) -> None:
        env = state.runtime_data["env"]
        messages = state.runtime_data["messages"]
        info = state.runtime_data["info"]
        frame = state.instance_frame
        product_terms = list(arguments.get("product_terms") or _product_terms_from_frame(frame))
        if not product_terms:
            return
        records: List[Mapping[str, Any]] = []
        executions = []
        for index, terms in enumerate(_product_search_inputs(product_terms)[:4]):
            action_name = "query_product_catalog:{}".format(index + 1)
            if not gate_retrieval(info, action_name, ["product_catalog"], "public"):
                return
            query = query_product_catalog(terms)
            result_records = execute_env(env, query, messages, info, action_name) if query else []
            if not gate_retrieved(info, action_name, "product_catalog", result_records):
                return
            records.extend(result_records)
            executions.append({"terms": list(terms), "record_count": len(result_records)})
        existing = state.retrieved_records.get("Product2", [])
        records = dedupe_records(existing + records)
        state.retrieved_records["Product2"] = [dict(item) for item in records]
        state.evidence_items = _merge_evidence_items(
            state.evidence_items,
            [EvidenceItem(str(item.get("Id") or ""), "product_catalog", "Product2", item, "public") for item in records],
        )
        state.env_calls = info["env_steps"]
        info["product_catalog_search_executions"] = executions

    def _handle_query_purchase_history(self, state: ExecutionState, arguments: Mapping[str, Any]) -> None:
        env = state.runtime_data["env"]
        messages = state.runtime_data["messages"]
        info = state.runtime_data["info"]
        account_id = state.runtime_data.get("current_customer_account_id")
        date_window = _date_window_from_frame(state.instance_frame)
        if not account_id or not date_window:
            return
        if not gate_retrieval(info, "query_purchase_history", ["current_customer_purchase_history", "current_customer_order_history"], "current_customer"):
            return
        query = query_purchase_history(str(account_id), date_window)
        purchase_records = execute_env(env, query, messages, info, "query_purchase_history") if query else []
        if not gate_retrieved(info, "query_purchase_history", "current_customer_purchase_history", purchase_records):
            return
        purchase_records = [
            _annotate_purchase_record_with_query_context(record, date_window)
            for record in dedupe_records(purchase_records)
        ]
        state.retrieved_records["OrderItem"] = [dict(item) for item in purchase_records]
        state.evidence_items = _merge_evidence_items(
            state.evidence_items,
            [EvidenceItem(str(item.get("Id") or ""), "current_customer_purchase_history", "OrderItem", item, "current_customer") for item in purchase_records],
        )

        product_ids = unique_record_values(purchase_records, "Product2Id")
        if product_ids:
            if not gate_retrieval(info, "query_purchased_products", ["product_catalog"], "public"):
                return
            product_query = query_products_by_ids(product_ids)
            product_records = execute_env(env, product_query, messages, info, "query_purchased_products") if product_query else []
            if not gate_retrieved(info, "query_purchased_products", "product_catalog", product_records):
                return
            existing = state.retrieved_records.get("Product2", [])
            product_records = dedupe_records(existing + product_records)
            state.retrieved_records["Product2"] = [dict(item) for item in product_records]
            state.evidence_items = _merge_evidence_items(
                state.evidence_items,
                [EvidenceItem(str(item.get("Id") or ""), "product_catalog", "Product2", item, "public") for item in product_records],
            )
        state.env_calls = info["env_steps"]

    def _handle_query_opportunity_by_id(self, state: ExecutionState, arguments: Mapping[str, Any]) -> None:
        env = state.runtime_data["env"]
        messages = state.runtime_data["messages"]
        info = state.runtime_data["info"]
        opportunity_id = _clean_salesforce_id(arguments.get("opportunity_id") or _target_id_from_state(state, "Opportunity"), "006")
        if not opportunity_id:
            return
        query = (
            "SELECT Id, ContractID__c, AccountId, ContactId, OwnerId, Probability, "
            "Amount, StageName, Name, Description, CreatedDate, CloseDate "
            "FROM Opportunity WHERE Id = '{opportunity_id}'"
        ).format(opportunity_id=_escape_literal(opportunity_id))
        records = dedupe_records(execute_env(env, query, messages, info, "query_opportunity_by_id"))
        state.retrieved_records["Opportunity"] = [dict(item) for item in records]
        state.evidence_items = _merge_evidence_items(
            state.evidence_items,
            [EvidenceItem(str(item.get("Id") or ""), "opportunity_record", "Opportunity", item, "internal_company") for item in records],
        )
        state.env_calls = info["env_steps"]

    def _handle_query_opportunity_activities(self, state: ExecutionState, arguments: Mapping[str, Any]) -> None:
        env = state.runtime_data["env"]
        messages = state.runtime_data["messages"]
        info = state.runtime_data["info"]
        opportunity_id = _clean_salesforce_id(arguments.get("opportunity_id") or _target_id_from_state(state, "Opportunity"), "006")
        if not opportunity_id:
            return
        task_query = (
            "SELECT Id, WhatId, OwnerId, Priority, Status, ActivityDate, Subject, Description "
            "FROM Task WHERE WhatId = '{opportunity_id}'"
        ).format(opportunity_id=_escape_literal(opportunity_id))
        event_query = (
            "SELECT Id, WhatId, OwnerId, StartDateTime, Subject, Description, "
            "DurationInMinutes, Location, IsAllDayEvent "
            "FROM Event WHERE WhatId = '{opportunity_id}'"
        ).format(opportunity_id=_escape_literal(opportunity_id))
        task_records = dedupe_records(execute_env(env, task_query, messages, info, "query_opportunity_tasks"))
        event_records = dedupe_records(execute_env(env, event_query, messages, info, "query_opportunity_events"))
        state.retrieved_records["Task"] = [dict(item) for item in task_records]
        state.retrieved_records["Event"] = [dict(item) for item in event_records]
        state.evidence_items = _merge_evidence_items(
            state.evidence_items,
            [EvidenceItem(str(item.get("Id") or ""), "opportunity_activity", "Task", item, "internal_company") for item in task_records]
            + [EvidenceItem(str(item.get("Id") or ""), "opportunity_activity", "Event", item, "internal_company") for item in event_records],
        )
        state.env_calls = info["env_steps"]

    def _handle_query_opportunity_commercial_context(self, state: ExecutionState, arguments: Mapping[str, Any]) -> None:
        env = state.runtime_data["env"]
        messages = state.runtime_data["messages"]
        info = state.runtime_data["info"]
        opportunity_id = _clean_salesforce_id(arguments.get("opportunity_id") or _target_id_from_state(state, "Opportunity"), "006")
        if not opportunity_id:
            return

        quote_query = (
            "SELECT Id, OpportunityId, AccountId, ContactId, Name, Description, Status, "
            "CreatedDate, ExpirationDate FROM Quote WHERE OpportunityId = '{opportunity_id}'"
        ).format(opportunity_id=_escape_literal(opportunity_id))
        opportunity_line_item_query = (
            "SELECT Id, OpportunityId, Product2Id, PricebookEntryId, Quantity, TotalPrice "
            "FROM OpportunityLineItem WHERE OpportunityId = '{opportunity_id}'"
        ).format(opportunity_id=_escape_literal(opportunity_id))

        quote_records = dedupe_records(execute_env(env, quote_query, messages, info, "query_opportunity_quotes"))
        opportunity_line_items = dedupe_records(
            execute_env(env, opportunity_line_item_query, messages, info, "query_opportunity_line_items")
        )

        quote_line_items: List[Mapping[str, Any]] = []
        quote_ids = unique_record_values(quote_records, "Id")
        if quote_ids:
            quoted_ids = ", ".join("'{}'".format(_escape_literal(str(quote_id))) for quote_id in quote_ids)
            quote_line_item_query = (
                "SELECT Id, QuoteId, OpportunityLineItemId, Product2Id, PricebookEntryId, "
                "Quantity, UnitPrice, Discount, TotalPrice FROM QuoteLineItem "
                "WHERE QuoteId IN ({quote_ids})"
            ).format(quote_ids=quoted_ids)
            quote_line_items = dedupe_records(
                execute_env(env, quote_line_item_query, messages, info, "query_opportunity_quote_line_items")
            )

        contract_records: List[Mapping[str, Any]] = []
        opportunity_records = state.retrieved_records.get("Opportunity") or []
        contract_ids = unique_record_values(opportunity_records, "ContractID__c")
        if contract_ids:
            quoted_contract_ids = ", ".join("'{}'".format(_escape_literal(str(contract_id))) for contract_id in contract_ids)
            contract_query = (
                "SELECT Id, AccountId, Status, StartDate, CustomerSignedDate, CompanySignedDate, "
                "Description, ContractTerm FROM Contract WHERE Id IN ({contract_ids})"
            ).format(contract_ids=quoted_contract_ids)
            contract_records = dedupe_records(execute_env(env, contract_query, messages, info, "query_opportunity_contracts"))

        state.retrieved_records["Quote"] = [dict(item) for item in quote_records]
        state.retrieved_records["QuoteLineItem"] = [dict(item) for item in quote_line_items]
        state.retrieved_records["OpportunityLineItem"] = [dict(item) for item in opportunity_line_items]
        state.retrieved_records["Contract"] = [dict(item) for item in contract_records]
        state.evidence_items = _merge_evidence_items(
            state.evidence_items,
            [EvidenceItem(str(item.get("Id") or ""), "opportunity_commercial_context", "Quote", item, "internal_company") for item in quote_records]
            + [EvidenceItem(str(item.get("Id") or ""), "opportunity_commercial_context", "QuoteLineItem", item, "internal_company") for item in quote_line_items]
            + [EvidenceItem(str(item.get("Id") or ""), "opportunity_commercial_context", "OpportunityLineItem", item, "internal_company") for item in opportunity_line_items]
            + [EvidenceItem(str(item.get("Id") or ""), "opportunity_commercial_context", "Contract", item, "internal_company") for item in contract_records],
        )
        state.env_calls = info["env_steps"]

    def _handle_query_case_by_id(self, state: ExecutionState, arguments: Mapping[str, Any]) -> None:
        env = state.runtime_data["env"]
        messages = state.runtime_data["messages"]
        info = state.runtime_data["info"]
        case_id = _clean_salesforce_id(arguments.get("case_id") or _target_id_from_state(state, "Case"), "500")
        if not case_id:
            return
        query = (
            "SELECT Id, Priority, Subject, Description, Status, ContactId, CreatedDate, "
            "ClosedDate, OrderItemId__c, IssueId__c, AccountId, OwnerId "
            "FROM Case WHERE Id = '{case_id}'"
        ).format(case_id=_escape_literal(case_id))
        records = dedupe_records(execute_env(env, query, messages, info, "query_case_by_id"))
        state.retrieved_records["Case"] = [dict(item) for item in records]
        state.evidence_items = _merge_evidence_items(
            state.evidence_items,
            [EvidenceItem(str(item.get("Id") or ""), "case_record", "Case", item, "internal_company") for item in records],
        )
        state.env_calls = info["env_steps"]

    def _handle_query_case_interactions(self, state: ExecutionState, arguments: Mapping[str, Any]) -> None:
        env = state.runtime_data["env"]
        messages = state.runtime_data["messages"]
        info = state.runtime_data["info"]
        case_id = _clean_salesforce_id(arguments.get("case_id") or _target_id_from_state(state, "Case"), "500")
        if not case_id:
            return
        email_query = (
            "SELECT Id, Subject, TextBody, ParentId, FromAddress, ToIds, MessageDate, RelatedToId "
            "FROM EmailMessage WHERE ParentId = '{case_id}' OR RelatedToId = '{case_id}'"
        ).format(case_id=_escape_literal(case_id))
        history_query = (
            "SELECT Id, CaseId__c, OldValue__c, NewValue__c, CreatedDate, Field__c "
            "FROM CaseHistory__c WHERE CaseId__c = '{case_id}'"
        ).format(case_id=_escape_literal(case_id))
        email_records = dedupe_records(execute_env(env, email_query, messages, info, "query_case_email_messages"))
        history_records = dedupe_records(execute_env(env, history_query, messages, info, "query_case_history"))
        state.retrieved_records["EmailMessage"] = [dict(item) for item in email_records]
        state.retrieved_records["CaseHistory__c"] = [dict(item) for item in history_records]
        state.evidence_items = _merge_evidence_items(
            state.evidence_items,
            [EvidenceItem(str(item.get("Id") or ""), "case_interaction", "EmailMessage", item, "internal_company") for item in email_records]
            + [EvidenceItem(str(item.get("Id") or ""), "case_interaction", "CaseHistory__c", item, "internal_company") for item in history_records],
        )
        state.env_calls = info["env_steps"]

    def _handle_query_case_linked_context(self, state: ExecutionState, arguments: Mapping[str, Any]) -> None:
        env = state.runtime_data["env"]
        messages = state.runtime_data["messages"]
        info = state.runtime_data["info"]
        case_records = state.retrieved_records.get("Case", [])
        if not case_records:
            return

        issue_ids = _clean_salesforce_ids(record.get("IssueId__c") for record in case_records)
        order_item_ids = _clean_salesforce_ids(record.get("OrderItemId__c") for record in case_records)
        issue_records: List[Mapping[str, Any]] = []
        order_item_records: List[Mapping[str, Any]] = []
        order_records: List[Mapping[str, Any]] = []
        product_records: List[Mapping[str, Any]] = []

        if issue_ids:
            query = (
                "SELECT Id, Name FROM Issue__c WHERE Id IN ({ids})"
            ).format(ids=_quote_id_list(issue_ids))
            issue_records = dedupe_records(execute_env(env, query, messages, info, "query_case_issues"))

        if order_item_ids:
            query = (
                "SELECT Id, OrderId, Product2Id, Quantity, UnitPrice "
                "FROM OrderItem WHERE Id IN ({ids})"
            ).format(ids=_quote_id_list(order_item_ids))
            order_item_records = dedupe_records(execute_env(env, query, messages, info, "query_case_order_items"))

        order_ids = _clean_salesforce_ids(record.get("OrderId") for record in order_item_records)
        if order_ids:
            query = (
                "SELECT Id, AccountId, Status, EffectiveDate, CreatedDate "
                "FROM Order WHERE Id IN ({ids})"
            ).format(ids=_quote_id_list(order_ids))
            order_records = dedupe_records(execute_env(env, query, messages, info, "query_case_orders"))

        product_ids = _clean_salesforce_ids(record.get("Product2Id") for record in order_item_records)
        if product_ids:
            query = (
                "SELECT Id, Name, Description, IsActive "
                "FROM Product2 WHERE Id IN ({ids})"
            ).format(ids=_quote_id_list(product_ids))
            product_records = dedupe_records(execute_env(env, query, messages, info, "query_case_products"))

        if issue_records:
            existing = state.retrieved_records.get("Issue__c", [])
            state.retrieved_records["Issue__c"] = [dict(item) for item in dedupe_records(existing + issue_records)]
        if order_item_records:
            existing = state.retrieved_records.get("OrderItem", [])
            state.retrieved_records["OrderItem"] = [dict(item) for item in dedupe_records(existing + order_item_records)]
        if order_records:
            existing = state.retrieved_records.get("Order", [])
            state.retrieved_records["Order"] = [dict(item) for item in dedupe_records(existing + order_records)]
        if product_records:
            existing = state.retrieved_records.get("Product2", [])
            state.retrieved_records["Product2"] = [dict(item) for item in dedupe_records(existing + product_records)]

        state.evidence_items = _merge_evidence_items(
            state.evidence_items,
            [EvidenceItem(str(item.get("Id") or ""), "case_issue_record", "Issue__c", item, "internal_company") for item in issue_records]
            + [EvidenceItem(str(item.get("Id") or ""), "case_order_item", "OrderItem", item, "internal_company") for item in order_item_records]
            + [EvidenceItem(str(item.get("Id") or ""), "case_order_record", "Order", item, "internal_company") for item in order_records]
            + [EvidenceItem(str(item.get("Id") or ""), "case_product_record", "Product2", item, "internal_company") for item in product_records],
        )
        state.env_calls = info["env_steps"]
        info["case_linked_context"] = {
            "issue_ids": issue_ids,
            "order_item_ids": order_item_ids,
            "order_ids": order_ids,
            "product_ids": product_ids,
            "issue_count": len(issue_records),
            "order_item_count": len(order_item_records),
            "order_count": len(order_records),
            "product_count": len(product_records),
        }

    def _handle_query_internal_policy_articles(self, state: ExecutionState, arguments: Mapping[str, Any]) -> None:
        env = state.runtime_data["env"]
        messages = state.runtime_data["messages"]
        info = state.runtime_data["info"]
        terms = _policy_search_terms_from_state(state)
        records: List[Mapping[str, Any]] = []
        executions = []
        for index, term_group in enumerate(_knowledge_search_inputs(terms)[:4]):
            query = _query_knowledge_by_terms(term_group)
            if not query:
                continue
            result_records = execute_env(env, query, messages, info, "query_internal_policy_articles:{}".format(index + 1))
            records.extend(result_records)
            executions.append({"terms": list(term_group), "record_count": len(result_records)})
        all_records: List[Mapping[str, Any]] = []
        if not records:
            all_query = "SELECT Id, Title, Summary, FAQ_Answer__c FROM Knowledge__kav LIMIT 100"
            all_records = execute_env(env, all_query, messages, info, "query_internal_policy_articles:all")
        records = dedupe_records(records + all_records)
        existing = state.retrieved_records.get("Knowledge__kav", [])
        records = dedupe_records(existing + records)
        state.retrieved_records["Knowledge__kav"] = [dict(item) for item in records]
        state.evidence_items = _merge_evidence_items(
            state.evidence_items,
            [EvidenceItem(str(item.get("Id") or ""), "internal_policy_article", "Knowledge__kav", item, "internal_company") for item in records],
        )
        state.env_calls = info["env_steps"]
        if all_records:
            executions.append({"terms": ["*"], "record_count": len(all_records)})
        info["internal_policy_article_search_executions"] = executions

    def _handle_extract_claims(self, state: ExecutionState, arguments: Mapping[str, Any]) -> None:
        info = state.runtime_data["info"]
        messages = state.runtime_data["messages"]
        if not state.evidence_items:
            state.answer_candidate = {"answer": "None", "selected_evidence": [], "clarification_requirements": []}
            return
        _prepare_extraction_evidence(state)
        extractor_messages = [
            {"role": "system", "content": GENERIC_EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": build_generic_extraction_prompt(state)},
        ]
        last_error = None
        for attempt in range(self.max_extraction_retries + 1):
            output = self.model_extractor(extractor_messages)
            info["model_calls"] += 1
            state.model_calls += 1
            info.setdefault("generic_extraction_outputs", []).append({"attempt": attempt + 1, "output": output})
            messages.append({"role": "assistant", "content": '<extract_claims attempt="{}">{}</extract_claims>'.format(attempt + 1, output)})
            try:
                state.answer_candidate = parse_answer_candidate_json(output, state)
                state.selected_evidence = list(state.answer_candidate.get("selected_evidence", []))
                return
            except RuntimeParseError as exc:
                last_error = str(exc)
                extractor_messages.append({"role": "assistant", "content": output})
                extractor_messages.append({"role": "user", "content": "Invalid extraction JSON: {}. Retry with exactly one JSON object and no prose.".format(last_error)})
        info["generic_extraction_error"] = last_error
        state.answer_candidate = {"answer": "None", "selected_evidence": [], "clarification_requirements": []}

    def _handle_disclosure_gate(self, state: ExecutionState, arguments: Mapping[str, Any]) -> None:
        info = state.runtime_data["info"]
        messages = state.runtime_data["messages"]
        candidate = state.answer_candidate or {}
        if not candidate:
            return
        extractor_messages = [
            {"role": "system", "content": DISCLOSURE_GATE_SYSTEM_PROMPT},
            {"role": "user", "content": build_disclosure_gate_prompt(state)},
        ]
        last_error = None
        for attempt in range(self.max_extraction_retries + 1):
            output = self.model_extractor(extractor_messages)
            info["model_calls"] += 1
            state.model_calls += 1
            info.setdefault("disclosure_gate_outputs", []).append({"attempt": attempt + 1, "output": output})
            messages.append({"role": "assistant", "content": '<disclosure_gate attempt="{}">{}</disclosure_gate>'.format(attempt + 1, output)})
            try:
                decision = parse_disclosure_gate_json(output, state)
                info.setdefault("disclosure_gate_decisions", []).append(decision)
                state.privacy_gate_decisions.append(
                    {
                        "stage": "selected_evidence_disclosure",
                        "allowed": decision["safe_to_disclose"] and decision["recommended_action"] == "answer",
                        "reason": decision["reason"],
                        "blocked_information": list(decision["blocked_information"]),
                        "blocked_evidence_ids": list(decision["blocked_evidence_ids"]),
                    }
                )
                if not (decision["safe_to_disclose"] and decision["recommended_action"] == "answer"):
                    info["external_gate_refusal"] = render_refusal(decision["reason"])
                    state.completion_state = "refused"
                return
            except RuntimeParseError as exc:
                last_error = str(exc)
                extractor_messages.append({"role": "assistant", "content": output})
                extractor_messages.append({"role": "user", "content": "Invalid disclosure gate JSON: {}. Retry with exactly one JSON object and no prose.".format(last_error)})
        info["disclosure_gate_error"] = last_error
        if str(candidate.get("answer") or "").strip().lower() not in ("", "none", "null"):
            info["external_gate_refusal"] = render_refusal("Disclosure gate could not validate selected evidence.")
            state.completion_state = "refused"

    def _handle_classify_selected_evidence(self, state: ExecutionState, arguments: Mapping[str, Any]) -> None:
        info = state.runtime_data["info"]
        blocked = []
        for item in state.selected_evidence:
            evidence_type = str(item.get("evidence_type") or "")
            subject_scope = str(item.get("subject_scope") or "unknown")
            gate = gate_retrieval(
                info,
                "selected_evidence:{}".format(item.get("evidence_id") or ""),
                [{"evidence_type": evidence_type, "subject_scope": subject_scope}],
                subject_scope,
            )
            if not (gate and item.get("safe_to_use") is True):
                blocked.append(dict(item))
        info["selected_evidence"] = [dict(item) for item in state.selected_evidence]
        info["blocked_selected_evidence"] = blocked
        if blocked:
            info["external_gate_refusal"] = render_refusal("Selected evidence was classified as disallowed.")
            state.completion_state = "refused"

    def _handle_render_answer(self, state: ExecutionState, arguments: Mapping[str, Any]) -> None:
        info = state.runtime_data["info"]
        candidate = state.answer_candidate or {}
        answer = candidate.get(self.workflow_spec.render_policy.get("answer_field", "answer"), "None")
        none_values = self.workflow_spec.render_policy.get("none_values", ["", "None", "none", None])
        answer = _maybe_repair_entity_id_none_answer(state, answer, none_values)
        answer = _normalize_answer_for_contract(state, answer, none_values)
        if answer in none_values:
            answer = self.workflow_spec.render_policy.get("fallback", "None")
        evidence_classes = []
        for item in state.selected_evidence:
            evidence_type = item.get("evidence_type")
            if evidence_type and evidence_type not in evidence_classes:
                evidence_classes.append(evidence_type)
        if self._uses_privacy_gates() and not gate_final_response(info, state, str(answer), evidence_classes):
            answer = info["external_gate_refusal"]
        state.final_answer = str(answer)
        state.completion_state = "completed"

    def _handle_refuse(self, state: ExecutionState, arguments: Mapping[str, Any]) -> None:
        state.final_answer = render_refusal(str(arguments.get("blocked_information") or "Requested evidence is not allowed."))
        state.completion_state = "refused"

    def _handle_pause_for_clarification(self, state: ExecutionState, arguments: Mapping[str, Any]) -> None:
        missing = list(arguments.get("clarification_requirements") or [])
        state.clarification_prompt = _render_clarification(missing)
        state.completion_state = "paused_for_clarification"


def _apply_required_instance_fields(state: ExecutionState) -> None:
    frame = state.instance_frame
    if not frame:
        return
    preserve_model_missing = bool(
        state.workflow_spec.clarification_policy.get(
            "ask_when_instance_clarification_requirements",
            False,
        )
    )
    required_fields = state.workflow_spec.clarification_policy.get("required_fields")
    if not required_fields:
        required_fields = state.workflow_spec.data.get("instance_contract", {}).get("required_fields", [])
    missing = list(frame.clarification_requirements) if preserve_model_missing else []
    for field in required_fields:
        if field == "product_terms" and not _product_terms_from_frame(frame):
            missing.append("product or item description")
        elif field == "purchase_date_window" and not _date_window_from_frame(frame):
            missing.append("purchase date or timeframe")
        elif field == "query_terms" and not frame.query_terms and not frame.request_summary:
            missing.append("search topic")
        elif field == "opportunity_id" and not _target_id_from_state(state, "Opportunity"):
            missing.append("Opportunity ID")
        elif field == "case_id" and not _target_id_from_state(state, "Case"):
            missing.append("Case ID")
    frame.clarification_requirements = _dedupe_strings(missing)


def _render_clarification(clarification_requirements: List[str]) -> str:
    missing = _dedupe_strings(clarification_requirements)
    if missing:
        return "Could you clarify {} so I can continue?".format(", ".join(missing))
    return "Could you clarify the missing details so I can continue?"


def _user_visible_conversation_history(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    history = []
    for message in messages:
        role = message.get("role")
        content = (message.get("content") or "").strip()
        if not content or content.startswith("Salesforce instance output:"):
            continue
        if role == "user":
            history.append({"role": "user", "content": content})
        elif role == "assistant" and content.startswith("<respond>") and content.endswith("</respond>"):
            history.append(
                {
                    "role": "assistant",
                    "content": content[len("<respond>") : -len("</respond>")],
                }
            )
    return history


def _task_metadata(metadata: Any) -> Mapping[str, Any]:
    if not isinstance(metadata, Mapping):
        return {}
    required = metadata.get("required")
    if isinstance(required, Mapping):
        return required
    if isinstance(required, str):
        out: Dict[str, Any] = {}
        contact = re.search(r"Contact\s+Id\s+interacting:\s*([A-Za-z0-9]{15,18})", required)
        if contact:
            out["customer_id"] = contact.group(1)
        today = re.search(r"Today's\s+date:\s*(\d{4}-\d{2}-\d{2})", required)
        if today:
            out["today"] = today.group(1)
        if out:
            return out
    return metadata


def _target_id_from_state(state: ExecutionState, object_name: str) -> str:
    prefix = {"Opportunity": "006", "Case": "500"}.get(object_name, "")
    keys = {
        "Opportunity": ("opportunity_id", "OpportunityId", "record_id", "id", "Id"),
        "Case": ("case_id", "CaseId", "record_id", "id", "Id"),
    }.get(object_name, ("record_id", "id", "Id"))
    frame = state.instance_frame
    if frame:
        for source in list(frame.target_entities) + list(frame.constraints) + list(frame.required_evidence_instances):
            if not isinstance(source, Mapping):
                continue
            for key in keys:
                cleaned = _clean_salesforce_id(source.get(key), prefix)
                if cleaned:
                    return cleaned
            for value in source.values():
                cleaned = _extract_salesforce_id(str(value or ""), prefix)
                if cleaned:
                    return cleaned
        for value in [frame.request_summary] + list(frame.query_terms) + list(frame.product_terms):
            cleaned = _extract_salesforce_id(str(value or ""), prefix)
            if cleaned:
                return cleaned
    for message in state.conversation_history:
        cleaned = _extract_salesforce_id(str(message.get("content") or ""), prefix)
        if cleaned:
            return cleaned
    for message in state.runtime_data.get("messages", []):
        cleaned = _extract_salesforce_id(str(message.get("content") or ""), prefix)
        if cleaned:
            return cleaned
    return ""


def _clean_salesforce_id(value: Any, prefix: str = "") -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if re.fullmatch(r"[A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?", text) and (not prefix or text.startswith(prefix)):
        return text
    return _extract_salesforce_id(text, prefix)


def _clean_salesforce_ids(values) -> List[str]:
    out = []
    for value in values:
        cleaned = _clean_salesforce_id(value)
        if cleaned and cleaned not in out:
            out.append(cleaned)
    return out


def _quote_id_list(ids: List[str]) -> str:
    return ", ".join("'{}'".format(_escape_literal(item)) for item in ids)


def _extract_salesforce_id(text: str, prefix: str = "") -> str:
    if not text:
        return ""
    pattern = r"\b{}[A-Za-z0-9]{{12}}(?:[A-Za-z0-9]{{3}})?\b".format(re.escape(prefix)) if prefix else r"\b[A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?\b"
    match = re.search(pattern, text)
    return match.group(0) if match else ""


def _escape_literal(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


def _policy_search_terms_from_state(state: ExecutionState) -> List[str]:
    terms = []
    frame = state.instance_frame
    # Prefer business text learned from the case and its linked records. Raw ids,
    # schema labels, and role labels produce poor SOSL matches and can force a
    # broad fallback query.
    for record in state.retrieved_records.get("Case", []):
        terms.extend(str(record.get(key) or "") for key in ("Subject", "Description"))
    for record in state.retrieved_records.get("Issue__c", []):
        terms.extend(str(record.get(key) or "") for key in ("Name",))
    for record in state.retrieved_records.get("Product2", []):
        terms.extend(str(record.get(key) or "") for key in ("Name", "Description"))
    for record in state.retrieved_records.get("EmailMessage", []):
        terms.extend(str(record.get(key) or "") for key in ("Subject", "TextBody"))
    if frame:
        terms.extend(frame.query_terms)
        if not terms:
            terms.append(frame.request_summary)
        for entity in frame.target_entities:
            if isinstance(entity, Mapping):
                terms.extend(
                    str(value)
                    for key, value in entity.items()
                    if isinstance(value, str) and _policy_search_value_allowed(key, value)
                )
    compact = []
    for term in terms:
        text = _compact_search_text(term)
        if text and text not in compact:
            compact.append(text)
    if not compact:
        compact = ["policy", "agent policy", "case policy"]
    for fallback in ("policy", "support policy"):
        if fallback not in compact:
            compact.append(fallback)
    return compact[:6]


def _policy_search_value_allowed(key: Any, value: str) -> bool:
    key_text = str(key or "").lower()
    text = str(value or "").strip()
    if not text:
        return False
    if _extract_salesforce_id(text):
        return False
    if key_text in ("id", "case_id", "record_id", "value", "type", "role", "entity_type"):
        return False
    lowered = text.lower()
    if lowered in ("case.id", "policy_violation_evaluation_target"):
        return False
    if lowered.endswith("_target"):
        return False
    return True


def _knowledge_search_inputs(terms: List[str]) -> List[List[str]]:
    inputs = [[term] for term in terms if term]
    if len(terms) > 1:
        inputs.append([term for term in terms[:3] if term])
    return inputs


def _query_knowledge_by_terms(search_terms: List[str]) -> Optional[str]:
    term = _sanitize_search_term(search_terms)
    if not term:
        return None
    return (
        "FIND {{{term}}} IN ALL FIELDS "
        "RETURNING Knowledge__kav(Id, Title, Summary, FAQ_Answer__c)"
    ).format(term=term)


def _sanitize_search_term(search_terms: List[str]) -> str:
    parts = []
    for item in search_terms:
        text = _compact_search_text(item)
        if text:
            parts.append(text)
    term = " ".join(parts).strip()
    term = re.sub(r"[{}]", " ", term)
    term = re.sub(r"\s+", " ", term).strip()
    return term[:200]


def _compact_search_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:160]


def _customer_id_from_state(state: ExecutionState) -> str:
    metadata = state.runtime_data.get("metadata") or {}
    for key in ("customer_id", "current_customer_id", "contact_id", "ContactId"):
        value = metadata.get(key) if isinstance(metadata, Mapping) else None
        if value:
            return str(value)
    return ""


def _product_terms_from_frame(frame: Optional[InstanceFrame]) -> List[str]:
    if not frame:
        return []
    terms = list(frame.product_terms)
    for entity in frame.target_entities:
        surface = entity.get("surface_text") if isinstance(entity, Mapping) else None
        if surface and surface not in terms:
            terms.append(str(surface))
    return [term for term in terms if term]


def _product_search_inputs(product_terms: List[str]) -> List[List[str]]:
    inputs = [[term] for term in product_terms if term]
    if len(product_terms) > 1:
        inputs.append([term for term in product_terms if term])
    return inputs


def _date_window_from_frame(frame: Optional[InstanceFrame]):
    if not frame:
        return None
    for constraint in frame.constraints:
        if not isinstance(constraint, Mapping):
            continue
        constraint_type = str(constraint.get("type") or "").lower()
        start = constraint.get("start_date") or constraint.get("start")
        end = constraint.get("end_date") or constraint.get("end")
        window = constraint.get("date_window")
        if isinstance(window, list) and len(window) == 2:
            start, end = window
        if (
            constraint_type in ("purchase_date_window", "date_window", "purchase_time")
            and start
            and end
            and _constraint_valid_for_retrieval(constraint)
        ):
            return (str(start), str(end))
    return None


def _constraint_valid_for_retrieval(constraint: Mapping[str, Any]) -> bool:
    for key in ("is_valid_for_retrieval", "valid_for_retrieval", "is_grounded", "grounded"):
        if key in constraint:
            return constraint[key] is True
    return True


def _merge_evidence_items(existing: List[EvidenceItem], new_items: List[EvidenceItem]) -> List[EvidenceItem]:
    by_key = {}
    for item in existing + new_items:
        key = (item.source_object, item.evidence_id, item.evidence_type)
        by_key[key] = item
    return list(by_key.values())


def _prepare_extraction_evidence(state: ExecutionState) -> None:
    ranking = state.workflow_spec.data.get("evidence_ranking")
    if not isinstance(ranking, Mapping):
        state.runtime_data.pop("extraction_evidence_items", None)
        return
    items = list(state.evidence_items)
    if not items:
        state.runtime_data["extraction_evidence_items"] = []
        return

    max_items = _positive_int(ranking.get("max_items"), len(items))
    always_types = set(_string_values(ranking.get("always_include_evidence_types", [])))
    rank_types = set(_string_values(ranking.get("rank_evidence_types", [])))
    raw_per_type_limits = ranking.get("max_ranked_items_per_type", {})
    per_type_limits = {
        str(key): _positive_int(value, max_items)
        for key, value in (raw_per_type_limits.items() if isinstance(raw_per_type_limits, Mapping) else [])
    }

    always: List[EvidenceItem] = []
    rankable = []
    other: List[EvidenceItem] = []
    context_terms = _ranking_context_terms(state)
    context_tokens = _tokenize_for_ranking(" ".join(context_terms))

    for index, item in enumerate(items):
        if item.evidence_type in always_types:
            always.append(item)
        elif not rank_types or item.evidence_type in rank_types:
            rankable.append((_evidence_rank_score(item, context_terms, context_tokens), index, item))
        else:
            other.append(item)

    ranked: List[EvidenceItem] = []
    per_type_counts: Dict[str, int] = {}
    for score, index, item in sorted(rankable, key=lambda value: (-value[0], value[1])):
        limit = per_type_limits.get(item.evidence_type, max_items)
        if per_type_counts.get(item.evidence_type, 0) >= limit:
            continue
        ranked.append(item)
        per_type_counts[item.evidence_type] = per_type_counts.get(item.evidence_type, 0) + 1

    selected = _dedupe_evidence_items(always + ranked + other)[:max_items]
    state.runtime_data["extraction_evidence_items"] = [item.as_dict() for item in selected]

    info = state.runtime_data.get("info")
    if isinstance(info, dict):
        info["evidence_ranking"] = {
            "configured": True,
            "input_count": len(items),
            "output_count": len(selected),
            "always_include_evidence_types": sorted(always_types),
            "rank_evidence_types": sorted(rank_types),
            "top_ranked": [
                {
                    "evidence_id": item.evidence_id,
                    "evidence_type": item.evidence_type,
                    "source_object": item.source_object,
                    "score": score,
                }
                for score, _, item in sorted(rankable, key=lambda value: (-value[0], value[1]))[:10]
            ],
        }


def _dedupe_evidence_items(items: List[EvidenceItem]) -> List[EvidenceItem]:
    out = []
    seen = set()
    for item in items:
        key = (item.source_object, item.evidence_id, item.evidence_type)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _ranking_context_terms(state: ExecutionState) -> List[str]:
    terms = []
    frame = state.instance_frame
    if frame:
        terms.append(frame.request_summary)
        terms.extend(frame.query_terms)
        terms.extend(frame.product_terms)
        for collection in (frame.target_entities, frame.constraints, frame.required_evidence_instances):
            for item in collection:
                if isinstance(item, Mapping):
                    terms.extend(str(value) for value in item.values() if isinstance(value, str))
    for message in state.runtime_data.get("user_visible_conversation_history") or state.conversation_history:
        terms.append(str(message.get("content") or ""))
    for object_name in ("Case", "Opportunity", "EmailMessage", "Task", "Event", "CaseHistory__c", "Issue__c", "OrderItem", "Order", "Product2"):
        for record in state.retrieved_records.get(object_name, []):
            terms.append(_record_rank_text(record))
    return [_compact_search_text(term) for term in terms if _compact_search_text(term)]


def _evidence_rank_score(item: EvidenceItem, context_terms: List[str], context_tokens: set) -> int:
    record_text = _record_rank_text(item.record).lower()
    if not record_text:
        return 0
    record_tokens = _tokenize_for_ranking(record_text)
    score = len(context_tokens.intersection(record_tokens))
    for term in context_terms:
        normalized = term.lower().strip()
        if len(normalized) >= 4 and normalized in record_text:
            score += 8
    title = str(item.record.get("Title") or item.record.get("Name") or "").lower()
    if title:
        title_tokens = _tokenize_for_ranking(title)
        score += 2 * len(context_tokens.intersection(title_tokens))
    return score


def _record_rank_text(record: Mapping[str, Any]) -> str:
    fields = [
        "Title",
        "Name",
        "Summary",
        "FAQ_Answer__c",
        "Subject",
        "Description",
        "TextBody",
        "Status",
        "Priority",
        "StageName",
        "EffectiveDate",
        "OldValue__c",
        "NewValue__c",
        "Field__c",
    ]
    return " ".join(str(record.get(field) or "") for field in fields)


def _tokenize_for_ranking(text: str) -> set:
    stopwords = {
        "the", "and", "for", "with", "that", "this", "from", "into", "about",
        "case", "policy", "article", "customer", "agent", "user", "help",
        "assist", "identify", "whether", "what", "which", "when", "where",
        "why", "how", "any", "our", "their", "your", "its", "are", "was",
        "were", "has", "have", "had", "does", "did", "not", "none",
    }
    tokens = set()
    for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_'-]{2,}", text.lower()):
        if token not in stopwords:
            tokens.add(token)
    return tokens


def _string_values(value: Any) -> List[str]:
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _annotate_purchase_record_with_query_context(record: Mapping[str, Any], date_window) -> Dict[str, Any]:
    annotated = dict(record)
    if not date_window:
        return annotated
    start, end = date_window
    annotated["__symbolic_context"] = {
        "retrieval_action": "query_purchase_history",
        "date_window": [str(start), str(end)],
        "date_window_guarantee": (
            "This current-customer purchase record was returned by a purchase-history "
            "query filtered to activated orders in this inclusive date window."
        ),
    }
    return annotated


def _normalize_answer_for_contract(state: ExecutionState, answer: Any, none_values: List[Any]) -> Any:
    contract_type = state.workflow_spec.answer_contract.get("type")
    if answer in none_values:
        return answer
    text = str(answer or "").strip()
    if not text:
        return "None"
    if contract_type == "stage_label_or_none":
        return _normalize_stage_label(text)
    if contract_type == "violating_policy_article_id_or_none":
        match = re.search(r"\bka0[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?\b", text)
        return match.group(0) if match else "None"
    return answer


def _normalize_stage_label(text: str) -> str:
    normalized = " ".join(text.split()).strip()
    if _is_none_text(normalized):
        return "None"
    labels = ["Qualification", "Discovery", "Quote", "Negotiation", "Closed"]
    lowered = normalized.lower()
    exact = [label for label in labels if lowered == label.lower()]
    if exact:
        return exact[0]
    matches = [label for label in labels if re.search(r"\b{}\b".format(re.escape(label.lower())), lowered)]
    return matches[0] if len(matches) == 1 else "None"


def _normalize_none_text(text: str) -> str:
    return "None" if _is_none_text(text) else text


def _is_none_text(text: str) -> bool:
    return text.strip().strip("[]'\"").lower() in ("", "none", "null", "no violation", "no policy violation")


def _maybe_repair_entity_id_none_answer(state: ExecutionState, answer: Any, none_values: List[Any]) -> Any:
    if state.workflow_spec.answer_contract.get("type") != "entity_id_or_none":
        return answer
    if answer not in none_values:
        return answer
    candidate = state.answer_candidate or {}
    purchased_product_ids = _purchased_product_ids(state)
    if not purchased_product_ids:
        return answer

    candidate_ids = set()
    text_parts = [str(candidate.get("evidence") or "")]
    order_items_by_id = {
        str(record.get("Id") or ""): record
        for record in state.retrieved_records.get("OrderItem", [])
    }
    for item in state.selected_evidence:
        evidence_id = str(item.get("evidence_id") or "")
        evidence_type = str(item.get("evidence_type") or "")
        reason = str(item.get("reason") or "")
        text_parts.append(reason)
        if evidence_type == "product_catalog" and evidence_id in purchased_product_ids:
            candidate_ids.add(evidence_id)
        if evidence_type == "current_customer_purchase_history":
            product_id = str(order_items_by_id.get(evidence_id, {}).get("Product2Id") or "")
            if product_id in purchased_product_ids:
                candidate_ids.add(product_id)

    combined_text = "\n".join(text_parts)
    for product_id in _extract_product_ids(combined_text):
        if product_id in purchased_product_ids:
            candidate_ids.add(product_id)

    if len(candidate_ids) != 1 or not _has_positive_single_match_signal(combined_text):
        return answer

    repaired = next(iter(candidate_ids))
    candidate["answer"] = repaired
    state.answer_candidate = candidate
    state.runtime_data["info"].setdefault("answer_repairs", []).append(
        {
            "type": "entity_id_none_consistency_repair",
            "from": answer,
            "to": repaired,
            "reason": "Answer was None, but selected evidence/explanation identified exactly one purchased Product2Id as the material match.",
        }
    )
    return repaired


def _purchased_product_ids(state: ExecutionState) -> set:
    out = set()
    for record in state.retrieved_records.get("OrderItem", []):
        product_id = str(record.get("Product2Id") or "")
        if product_id:
            out.add(product_id)
    return out


def _extract_product_ids(text: str) -> List[str]:
    return re.findall(r"\b01t[A-Za-z0-9]{12,15}\b", text or "")


def _has_positive_single_match_signal(text: str) -> bool:
    normalized = " ".join((text or "").lower().split())
    if not normalized:
        return False
    positive_patterns = [
        r"\b(one|single|only|unique|best|strong|material)\b.{0,120}\bmatch",
        r"\bmatch(?:es|ed|ing)?\b.{0,120}\b(one|single|only|unique|best|strong|material)",
        r"\bis a material match\b",
        r"\bmatches the (requested|customer|product|description|type|class)",
    ]
    return any(re.search(pattern, normalized) for pattern in positive_patterns)


def _dedupe_strings(values: List[str]) -> List[str]:
    seen = set()
    out = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out
