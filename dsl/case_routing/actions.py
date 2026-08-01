"""Actions and state helpers for the case-routing symbolic layer."""

import re
from collections import Counter
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


CASE_FIELDS = (
    "Id",
    "Subject",
    "Description",
    "Status",
    "OwnerId",
    "CreatedDate",
    "ClosedDate",
    "AccountId",
    "ContactId",
    "IssueId__c",
    "OrderItemId__c",
)
ISSUE_FIELDS = ("Id", "Name")
ORDER_ITEM_FIELDS = ("Id", "Product2Id")
PRODUCT_FIELDS = ("Id", "Name", "Description", "IsActive")


SALESFORCE_ID_PATTERN = re.compile(r"\b[a-zA-Z0-9]{15}(?:[a-zA-Z0-9]{3})?\b")


class CaseRoutingSlots:
    def __init__(
        self,
        case_subject: str = "",
        case_description: str = "",
        issue_summary: str = "",
        issue_search_terms: Optional[List[str]] = None,
        product_search_terms: Optional[List[str]] = None,
    ):
        self.case_subject = case_subject
        self.case_description = case_description
        self.issue_summary = issue_summary
        self.issue_search_terms = issue_search_terms or []
        self.product_search_terms = product_search_terms or []

    def has_case_details(self) -> bool:
        text = " ".join(
            [
                self.case_subject,
                self.case_description,
                self.issue_summary,
                " ".join(self.product_search_terms),
            ]
        ).strip()
        return bool(text)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "case_subject": self.case_subject,
            "case_description": self.case_description,
            "issue_summary": self.issue_summary,
            "issue_search_terms": list(self.issue_search_terms),
            "product_search_terms": list(self.product_search_terms),
        }


class CandidateSelection:
    def __init__(self, selected_id: Optional[str], confidence: str = "unknown", rationale: str = ""):
        self.selected_id = selected_id
        self.confidence = confidence
        self.rationale = rationale

    def as_dict(self) -> Dict[str, Any]:
        return {
            "selected_id": self.selected_id,
            "confidence": self.confidence,
            "rationale": self.rationale,
        }


class CaseRoutingState:
    def __init__(self):
        self.slots = CaseRoutingSlots()
        self.issue_candidates: List[Mapping[str, Any]] = []
        self.selected_issue: Optional[CandidateSelection] = None
        self.issue_cases: List[Mapping[str, Any]] = []
        self.issue_owner_counts: Dict[str, int] = {}
        self.issue_tied_agent_ids: List[str] = []
        self.product_candidates: List[Mapping[str, Any]] = []
        self.selected_product: Optional[CandidateSelection] = None
        self.order_items: List[Mapping[str, Any]] = []
        self.product_cases: List[Mapping[str, Any]] = []
        self.product_owner_counts: Dict[str, int] = {}
        self.product_tied_agent_ids: List[str] = []
        self.open_workload_cases: List[Mapping[str, Any]] = []
        self.workload_counts: Dict[str, int] = {}
        self.final_agent_id: Optional[str] = None
        self.resolution_stage: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "slots": self.slots.as_dict(),
            "issue_candidates": [dict(item) for item in self.issue_candidates],
            "selected_issue": self.selected_issue.as_dict() if self.selected_issue else None,
            "issue_cases_count": len(self.issue_cases),
            "issue_owner_counts": dict(self.issue_owner_counts),
            "issue_tied_agent_ids": list(self.issue_tied_agent_ids),
            "product_candidates": [dict(item) for item in self.product_candidates],
            "selected_product": self.selected_product.as_dict() if self.selected_product else None,
            "order_item_count": len(self.order_items),
            "product_cases_count": len(self.product_cases),
            "product_owner_counts": dict(self.product_owner_counts),
            "product_tied_agent_ids": list(self.product_tied_agent_ids),
            "open_workload_case_count": len(self.open_workload_cases),
            "workload_counts": dict(self.workload_counts),
            "final_agent_id": self.final_agent_id,
            "resolution_stage": self.resolution_stage,
        }


def query_issues() -> str:
    return "SELECT {fields} FROM Issue__c".format(fields=", ".join(ISSUE_FIELDS))


def query_closed_cases_by_issue(issue_id: str) -> str:
    _validate_salesforce_id(issue_id, "issue_id")
    return (
        "SELECT {fields} FROM Case "
        "WHERE IssueId__c = '{issue_id}' AND Status = 'Closed'"
    ).format(fields=", ".join(CASE_FIELDS), issue_id=_escape_literal(issue_id))


def query_products_by_terms(search_terms: Iterable[str]) -> Optional[str]:
    term = sanitize_search_term(search_terms)
    if not term:
        return None
    return "FIND {{{term}}} IN ALL FIELDS RETURNING Product2({fields})".format(
        term=term,
        fields=", ".join(PRODUCT_FIELDS),
    )


def query_order_items_by_product(product_id: str) -> str:
    _validate_salesforce_id(product_id, "product_id")
    return (
        "SELECT {fields} FROM OrderItem WHERE Product2Id = '{product_id}'"
    ).format(fields=", ".join(ORDER_ITEM_FIELDS), product_id=_escape_literal(product_id))


def query_closed_cases_by_order_items(order_item_ids: Iterable[str]) -> Optional[str]:
    ids = _clean_salesforce_ids(order_item_ids)
    if not ids:
        return None
    return (
        "SELECT {fields} FROM Case "
        "WHERE OrderItemId__c IN ({ids}) AND Status = 'Closed'"
    ).format(
        fields=", ".join(CASE_FIELDS),
        ids=", ".join("'{}'".format(_escape_literal(item)) for item in ids),
    )


def query_open_cases_by_agents(agent_ids: Iterable[str]) -> Optional[str]:
    ids = _clean_salesforce_ids(agent_ids)
    if not ids:
        return None
    return (
        "SELECT {fields} FROM Case "
        "WHERE OwnerId IN ({ids}) AND Status != 'Closed'"
    ).format(
        fields=", ".join(CASE_FIELDS),
        ids=", ".join("'{}'".format(_escape_literal(item)) for item in ids),
    )


def count_cases_by_owner(cases: Iterable[Mapping[str, Any]]) -> Dict[str, int]:
    counts: Counter[str] = Counter()
    for case in cases:
        owner_id = case.get("OwnerId")
        if isinstance(owner_id, str) and owner_id:
            counts[owner_id] += 1
    return dict(counts)


def agents_with_max_count(
    counts: Mapping[str, int],
    candidate_agent_ids: Optional[Iterable[str]] = None,
) -> List[str]:
    scoped = _counts_with_zero_candidates(counts, candidate_agent_ids)
    if not scoped:
        return []
    max_count = max(scoped.values())
    return sorted(agent_id for agent_id, count in scoped.items() if count == max_count)


def agents_with_min_count(
    counts: Mapping[str, int],
    candidate_agent_ids: Optional[Iterable[str]] = None,
) -> List[str]:
    scoped = _counts_with_zero_candidates(counts, candidate_agent_ids)
    if not scoped:
        return []
    min_count = min(scoped.values())
    return sorted(agent_id for agent_id, count in scoped.items() if count == min_count)


def filter_counts_to_agents(
    counts: Mapping[str, int],
    candidate_agent_ids: Iterable[str],
) -> Dict[str, int]:
    candidates = list(dict.fromkeys(candidate_agent_ids))
    return {agent_id: int(counts.get(agent_id, 0)) for agent_id in candidates}


def render_agent_id_response(agent_id: Optional[str]) -> str:
    return agent_id or "None"


def respond_to_user(missing_requirement: str, context: str = "") -> str:
    if missing_requirement == "case_details":
        return "Could you provide the case subject and description that need routing?"
    return "Could you provide the missing case routing information?"


def extract_case_routing_slots_prompt(task_query: str, conversation_text: str) -> str:
    return (
        "Extract case-routing slots from the task and conversation. Return exactly one JSON object.\n\n"
        "Task prompt:\n{task}\n\n"
        "Conversation so far:\n{conversation}"
    ).format(task=task_query, conversation=conversation_text)


def select_best_issue_prompt(
    slots: CaseRoutingSlots,
    issue_candidates: Sequence[Mapping[str, Any]],
) -> str:
    return (
        "Select the Issue__c candidate most similar to the given case. Return exactly one JSON object.\n\n"
        "Case routing slots:\n{slots}\n\n"
        "Issue candidates:\n{candidates}"
    ).format(
        slots=slots.as_dict(),
        candidates=[_compact_mapping(item, ISSUE_FIELDS) for item in issue_candidates],
    )


def select_best_product_prompt(
    slots: CaseRoutingSlots,
    product_candidates: Sequence[Mapping[str, Any]],
) -> str:
    return (
        "Select the Product2 candidate most relevant to the given case. Return exactly one JSON object.\n\n"
        "Case routing slots:\n{slots}\n\n"
        "Product candidates:\n{candidates}"
    ).format(
        slots=slots.as_dict(),
        candidates=[_compact_mapping(item, PRODUCT_FIELDS) for item in product_candidates],
    )


def fallback_select_issue(slots: CaseRoutingSlots, candidates: Sequence[Mapping[str, Any]]) -> CandidateSelection:
    return _fallback_select_candidate(
        " ".join([slots.issue_summary, slots.case_subject, slots.case_description]),
        candidates,
    )


def fallback_select_product(slots: CaseRoutingSlots, candidates: Sequence[Mapping[str, Any]]) -> CandidateSelection:
    return _fallback_select_candidate(
        " ".join(slots.product_search_terms + [slots.case_subject, slots.case_description]),
        candidates,
    )


def dedupe_records(records: Iterable[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    seen = set()
    result = []
    for record in records:
        record_id = record.get("Id")
        key = record_id if record_id else tuple(sorted(record.items()))
        if key in seen:
            continue
        seen.add(key)
        result.append(record)
    return result


def sanitize_search_term(search_terms: Iterable[str]) -> str:
    tokens: List[str] = []
    for raw_term in search_terms:
        if raw_term is None:
            continue
        text = str(raw_term)
        text = re.sub(r"[{}'\"\\]", " ", text)
        # SOSL treats hyphen as syntax inside FIND braces on this benchmark
        # connector. Tokenize hyphenated product names into searchable words.
        text = re.sub(r"[-/]", " ", text)
        for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_.]*", text):
            if len(token) > 64:
                token = token[:64]
            if token.lower() not in {"and", "or", "the", "a", "an"}:
                tokens.append(token)
    deduped = list(dict.fromkeys(tokens))
    return " ".join(deduped[:12])


def _counts_with_zero_candidates(
    counts: Mapping[str, int],
    candidate_agent_ids: Optional[Iterable[str]],
) -> Dict[str, int]:
    if candidate_agent_ids is None:
        return {str(agent_id): int(count) for agent_id, count in counts.items()}
    scoped: Dict[str, int] = {}
    for agent_id in dict.fromkeys(candidate_agent_ids):
        if isinstance(agent_id, str) and agent_id:
            scoped[agent_id] = int(counts.get(agent_id, 0))
    return scoped


def _fallback_select_candidate(text: str, candidates: Sequence[Mapping[str, Any]]) -> CandidateSelection:
    text_tokens = set(_tokenize(text))
    best_id = None
    best_score = -1
    for candidate in candidates:
        candidate_id = candidate.get("Id")
        if not isinstance(candidate_id, str):
            continue
        candidate_text = " ".join(
            str(candidate.get(field) or "") for field in ("Name", "Description")
        )
        score = len(text_tokens.intersection(_tokenize(candidate_text)))
        if score > best_score:
            best_score = score
            best_id = candidate_id
    return CandidateSelection(best_id, "low", "Lexical fallback selection.")


def _tokenize(text: str) -> List[str]:
    return [
        token.lower()
        for token in re.findall(r"[A-Za-z0-9]+", text or "")
        if len(token) > 2
    ]


def _clean_salesforce_ids(values: Iterable[str]) -> List[str]:
    ids = []
    for value in values:
        if isinstance(value, str) and _looks_like_salesforce_id(value):
            ids.append(value)
    return list(dict.fromkeys(ids))


def _validate_salesforce_id(value: str, field_name: str) -> None:
    if not _looks_like_salesforce_id(value):
        raise ValueError("{} must be a Salesforce id".format(field_name))


def _looks_like_salesforce_id(value: str) -> bool:
    return isinstance(value, str) and bool(SALESFORCE_ID_PATTERN.fullmatch(value))


def _escape_literal(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


def _compact_mapping(record: Mapping[str, Any], fields: Sequence[str]) -> Dict[str, Any]:
    return {field: record.get(field) for field in fields if record.get(field) not in (None, "")}
