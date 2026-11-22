"""Generic action definitions for the shared symbolic runtime."""

from typing import Any, Dict, List

ACTION_CATEGORIES = ("environment", "symbolic", "termination")

ENVIRONMENT_ACTIONS = (
    "get_record_by_id", "find_records", "retrieve_knowledge", "query_children",
    "follow_reference", "aggregate_records", "query_current_customer",
    "query_purchase_history", "query_order_history", "query_case_status",
    "query_product_catalog", "query_opportunity_by_id",
    "query_opportunity_activities", "query_opportunity_commercial_context",
    "query_case_by_id", "query_case_interactions", "query_case_linked_context",
    "query_internal_policy_articles",
)
SYMBOLIC_ACTIONS = (
    "extract_claims", "disclosure_gate", "classify_selected_evidence", "filter_evidence",
    "compare_values", "compute_totals", "rank_candidates",
)
TERMINATION_ACTIONS = (
    "render_answer", "refuse", "return_none", "pause_for_clarification", "stop",
)
RUNTIME_CHECKPOINTS = (
    "schema_validated", "action_verified", "evidence_privacy_gate",
    "answer_contract_gate", "completion_predicates_evaluated",
)

def _action(category: str, description: str, required=None, optional=None, preconditions=None, effects=None) -> Dict[str, Any]:
    return {
        "category": category,
        "description": description,
        "required_args": list(required or []),
        "optional_args": list(optional or []),
        "preconditions": preconditions or {},
        "effects": effects or {"sets": [], "may_set": []},
    }

ACTION_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "get_record_by_id": _action("environment", "Retrieve one Salesforce record by object and ID.", ["object", "record_id", "fields"], preconditions={"all_of": ["record_id_available"]}, effects={"sets": ["retrieved_records", "env_calls"], "may_set": ["query_errors"]}),
    "find_records": _action("environment", "Search records using runtime-compiled safe query templates.", ["object", "search_terms", "fields"], ["limit"], {"all_of": ["search_terms_available"]}, {"sets": ["retrieved_records", "env_calls"], "may_set": ["query_errors"]}),
    "retrieve_knowledge": _action("environment", "Search Knowledge__kav articles for relevant evidence.", ["search_terms"], ["evidence_type_hint", "limit"], {"all_of": ["query_terms_available"]}, {"sets": ["retrieved_records.Knowledge__kav", "env_calls"], "may_set": ["evidence_items", "query_errors"]}),
    "query_children": _action("environment", "Retrieve child records through a verified lookup relationship.", ["parent_object", "parent_id", "child_object", "relationship_field", "fields"], ["filters"], {"all_of": ["parent_id_available", "relationship_verified"]}, {"sets": ["retrieved_records", "env_calls"], "may_set": ["query_errors"]}),
    "follow_reference": _action("environment", "Follow a verified reference field to another object.", ["source_object", "source_id", "reference_field", "target_fields"], preconditions={"all_of": ["source_record_available", "reference_verified"]}, effects={"sets": ["retrieved_records", "env_calls"], "may_set": ["query_errors"]}),
    "aggregate_records": _action("environment", "Run a verified aggregation over records.", ["object", "metric"], ["filters", "group_by"], {"all_of": ["aggregation_schema_verified"]}, {"sets": ["computed_values", "env_calls"], "may_set": ["query_errors"]}),
    "query_current_customer": _action("environment", "Retrieve scoped profile evidence for the current external customer.", optional=["fields"], preconditions={"all_of": ["current_customer_scope_allowed"]}, effects={"sets": ["retrieved_records.current_customer", "env_calls"], "may_set": ["query_errors"]}),
    "query_purchase_history": _action("environment", "Retrieve purchase history scoped to the current customer.", ["search_terms_or_timeframe"], ["product_terms", "limit"], {"all_of": ["current_customer_scope_allowed"]}, {"sets": ["retrieved_records.purchase_history", "env_calls"], "may_set": ["query_errors"]}),
    "query_order_history": _action("environment", "Retrieve order history scoped to the current customer.", ["search_terms_or_timeframe"], ["product_terms", "limit"], {"all_of": ["current_customer_scope_allowed"]}, {"sets": ["retrieved_records.order_history", "env_calls"], "may_set": ["query_errors"]}),
    "query_case_status": _action("environment", "Retrieve case status scoped to the current customer.", ["case_reference_or_description"], preconditions={"all_of": ["current_customer_scope_allowed"]}, effects={"sets": ["retrieved_records.case_status", "env_calls"], "may_set": ["query_errors"]}),
    "query_product_catalog": _action("environment", "Retrieve public product catalog candidates.", ["product_terms"], ["limit"], {"all_of": ["product_terms_available"]}, {"sets": ["retrieved_records.product_catalog", "env_calls"], "may_set": ["query_errors"]}),
    "query_opportunity_by_id": _action("environment", "Retrieve a target Opportunity by verified ID.", ["opportunity_id"], ["fields"], {"all_of": ["record_id_available"]}, {"sets": ["retrieved_records.Opportunity", "env_calls"], "may_set": ["query_errors"]}),
    "query_opportunity_activities": _action("environment", "Retrieve Task and Event activity evidence related to a target Opportunity.", ["opportunity_id"], ["fields"], {"all_of": ["record_id_available"]}, {"sets": ["retrieved_records.Task", "retrieved_records.Event", "env_calls"], "may_set": ["query_errors"]}),
    "query_opportunity_commercial_context": _action("environment", "Retrieve Quote, QuoteLineItem, OpportunityLineItem, and Contract context related to a target Opportunity.", ["opportunity_id"], ["fields"], {"all_of": ["record_id_available"]}, {"sets": ["retrieved_records.Quote", "retrieved_records.QuoteLineItem", "retrieved_records.OpportunityLineItem", "retrieved_records.Contract", "env_calls"], "may_set": ["query_errors"]}),
    "query_case_by_id": _action("environment", "Retrieve a target Case by verified ID.", ["case_id"], ["fields"], {"all_of": ["record_id_available"]}, {"sets": ["retrieved_records.Case", "env_calls"], "may_set": ["query_errors"]}),
    "query_case_interactions": _action("environment", "Retrieve interaction/history evidence related to a target Case.", ["case_id"], ["fields"], {"all_of": ["record_id_available"]}, {"sets": ["retrieved_records.EmailMessage", "retrieved_records.CaseHistory__c", "env_calls"], "may_set": ["query_errors"]}),
    "query_case_linked_context": _action("environment", "Retrieve Issue__c, OrderItem, Order, and Product2 context referenced by a target Case.", ["case_id"], ["fields"], {"all_of": ["retrieved_records_available"]}, {"sets": ["retrieved_records.Issue__c", "retrieved_records.OrderItem", "retrieved_records.Order", "retrieved_records.Product2", "env_calls"], "may_set": ["query_errors"]}),
    "query_internal_policy_articles": _action("environment", "Retrieve internal Knowledge__kav policy articles for internal policy comparison.", ["search_terms"], ["limit"], {"any_of": ["query_terms_available", "retrieved_records_available"]}, {"sets": ["retrieved_records.Knowledge__kav", "env_calls"], "may_set": ["query_errors"]}),
    "extract_claims": _action("symbolic", "Extract workflow requirement claims from evidence.", ["requirements", "evidence_items"], preconditions={"all_of": ["retrieved_records_available", "pending_requirements_exist"]}, effects={"sets": ["claims", "model_calls"], "may_set": ["selected_evidence"]}),
    "disclosure_gate": _action("symbolic", "Classify whether the selected evidence and answer candidate can be disclosed to the external user.", ["answer_candidate"], ["selected_evidence"], {"all_of": ["answer_contract_satisfied"]}, {"sets": ["privacy_gate_decisions", "model_calls"], "may_set": ["blocked_evidence"]}),
    "classify_selected_evidence": _action("symbolic", "Classify selected evidence into taxonomy and scope.", ["selected_evidence"], ["answer_candidate"], {"all_of": ["selected_evidence_available"]}, {"sets": ["privacy_gate_decisions", "model_calls"], "may_set": ["blocked_evidence"]}),
    "filter_evidence": _action("symbolic", "Keep only evidence relevant to pending requirements.", ["evidence_items"], ["requirements"], {"all_of": ["evidence_items_available"]}, {"sets": ["selected_evidence"], "may_set": []}),
    "compare_values": _action("symbolic", "Compare structured values such as dates or thresholds.", ["left", "operator", "right"], ["units"], {"all_of": ["comparison_values_available"]}, {"sets": ["computed_values"], "may_set": ["claims"]}),
    "compute_totals": _action("symbolic", "Compute deterministic totals from quantities and prices.", ["line_items"], ["default_quantity"], {"all_of": ["numeric_inputs_available"]}, {"sets": ["computed_values"], "may_set": ["claims"]}),
    "rank_candidates": _action("symbolic", "Rank retrieved candidates using workflow criteria.", ["candidates"], ["ranking_criteria"], {"all_of": ["candidates_available"]}, {"sets": ["computed_values.ranked_candidates"], "may_set": ["claims"]}),
    "render_answer": _action("termination", "Render an answer satisfying the answer contract.", ["answer_candidate"], preconditions={"all_of": ["answer_contract_satisfied"]}, effects={"sets": ["final_answer", "completion_state"], "may_set": []}),
    "refuse": _action("termination", "Refuse when disclosure violates gates.", ["blocked_information"], preconditions={"all_of": ["refusal_required"]}, effects={"sets": ["final_answer", "completion_state"], "may_set": []}),
    "return_none": _action("termination", "Return None when the answer contract calls for no finding.", preconditions={"all_of": ["none_answer_allowed"]}, effects={"sets": ["final_answer", "completion_state"], "may_set": []}),
    "pause_for_clarification": _action("termination", "Pause workflow and ask for missing user-held information.", ["clarification_requirements"], preconditions={"all_of": ["clarification_requirements_blocks_progress"]}, effects={"sets": ["completion_state", "clarification_prompt"], "may_set": []}),
    "stop": _action("termination", "Stop after completion or max-turn termination.", preconditions={"any_of": ["answer_contract_satisfied", "max_turns_reached"]}, effects={"sets": ["completion_state"], "may_set": []}),
}

def action_category(action_name: str) -> str:
    return str(ACTION_DEFINITIONS.get(action_name, {}).get("category", ""))

def action_definition(action_name: str) -> Dict[str, Any]:
    return dict(ACTION_DEFINITIONS[action_name])

def actions_for_category(category: str) -> List[str]:
    return [name for name, spec in ACTION_DEFINITIONS.items() if spec.get("category") == category]
