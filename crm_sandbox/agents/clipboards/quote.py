import ast
import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional

from verifiers.schema_utils import normalize_query
from verifiers.types import VerificationResult


FROM_OBJECT_RE = re.compile(r"\bFROM\s+([A-Za-z_][A-Za-z0-9_]*(?:__[a-zA-Z])?)\b", re.IGNORECASE)
RETURNING_RE = re.compile(r"\bRETURNING\s+([A-Za-z_][A-Za-z0-9_]*(?:__[a-zA-Z])?)\s*\(([^)]*)\)", re.IGNORECASE)
SELECT_FIELDS_RE = re.compile(r"^\s*SELECT\s+(.*?)\s+FROM\s+", re.IGNORECASE | re.DOTALL)
SUBSTANTIVE_POLICY_FIELDS = {
    "FAQ_Answer__c",
    "Content",
    "Body",
    "Body__c",
    "Description",
    "Description__c",
    "Details",
    "Details__c",
    "Answer",
    "Answer__c",
    "Text",
    "Text__c",
}
TITLE_ONLY_FIELDS = {"Id", "Title", "Name", "UrlName", "KnowledgeArticleId"}


@dataclass
class QueryFacts:
    query_type: str = "unknown"
    objects: set[str] = field(default_factory=set)
    selected_fields: set[str] = field(default_factory=set)
    targets_quote: bool = False
    targets_line_items: bool = False
    targets_policy: bool = False
    retrieves_policy_detail: bool = False


@dataclass
class ObservationFacts:
    failed: bool = False
    records: list[dict] = field(default_factory=list)
    record_count: int = 0

    @property
    def has_records(self) -> bool:
        return self.record_count > 0


@dataclass
class QuoteClipboard:
    stage: str = "retrieve_quote"
    next_goal: str = "Retrieve the target quote."
    quote_retrieved: bool = False
    quote_id: Optional[str] = None
    quote_fields: dict = field(default_factory=dict)
    line_items_retrieved: bool = False
    line_item_count: int = 0
    line_items: list[dict] = field(default_factory=list)
    candidate_policies: dict[str, dict] = field(default_factory=dict)
    inspected_policy_ids: set[str] = field(default_factory=set)
    failed_queries: list[str] = field(default_factory=list)


class QuoteApprovalClipboard:
    """Deterministic retrieval-state clipboard for quote approval tasks."""

    def __init__(self, max_chars: int = 1000, max_items: int = 5) -> None:
        self.max_chars = max(400, max_chars)
        self.max_items = max(2, max_items)
        self.state = QuoteClipboard()

    def reset(self, query: str = "", routing_result: Optional[Mapping[str, Any]] = None) -> None:
        self.state = QuoteClipboard()

    def record_verifier_failure(self, action: Optional[Mapping[str, str]], error_code: Optional[str]) -> None:
        if action and action.get("name") == "execute":
            self._add_failed_query(str(action.get("content", "")))
        if error_code:
            self.state.next_goal = f"Revise the rejected action before continuing: {error_code}."
        self._determine_stage()

    def record_env_step(self, action: Mapping[str, str], observation: Any, info: Optional[Mapping[str, Any]] = None) -> None:
        action_name = str(action.get("name", ""))
        if action_name == "respond":
            self.state.next_goal = "Final response submitted."
            return
        if action_name != "execute":
            return

        query = str(action.get("content", "")).strip()
        query_facts = self.extract_query_facts(query)
        observation_facts = self.extract_observation_facts(observation, info)
        self.update(query, query_facts, observation_facts)

    def update(self, query: str, query_facts: QueryFacts, observation_facts: ObservationFacts) -> None:
        if observation_facts.failed:
            self._add_failed_query(query)
            self.state.next_goal = "Change the failed query; do not repeat it exactly."
            self._determine_stage()
            return

        if not observation_facts.has_records:
            self.state.next_goal = "The last query returned no records. Refine the query for the current stage."
            self._determine_stage()
            return

        if query_facts.targets_quote:
            first = observation_facts.records[0]
            self.state.quote_retrieved = True
            self.state.quote_id = self._record_id(first) or self.state.quote_id
            self.state.quote_fields = self._compact_record(first)

        if query_facts.targets_line_items:
            self.state.line_items_retrieved = True
            self.state.line_item_count = observation_facts.record_count
            self.state.line_items = [self._compact_record(record) for record in observation_facts.records[: self.max_items]]

        if query_facts.targets_policy:
            for record in observation_facts.records:
                key = self._policy_key(record)
                self.state.candidate_policies[key] = self._compact_record(record)
                if query_facts.retrieves_policy_detail or self._record_has_policy_detail(record):
                    self.state.inspected_policy_ids.add(key)

        self._determine_stage()

    def response_gate(self, action: Optional[Mapping[str, str]]) -> VerificationResult:
        if not action or str(action.get("name", "")).lower() != "respond":
            return VerificationResult(valid=True)
        if not self.state.quote_retrieved:
            return self._invalid("QUOTE_CLIPBOARD_MISSING_QUOTE", "Retrieve the target Quote record before responding.")
        if not self.state.line_items_retrieved:
            return self._invalid("QUOTE_CLIPBOARD_MISSING_LINE_ITEMS", "Retrieve QuoteLineItem evidence before responding.")
        if not self.state.candidate_policies:
            return self._invalid("QUOTE_CLIPBOARD_MISSING_POLICY_CANDIDATES", "Find plausible quote approval policy or knowledge article candidates before responding.")
        if not self.state.inspected_policy_ids:
            return self._invalid("QUOTE_CLIPBOARD_MISSING_POLICY_DETAIL", "Inspect the contents of at least one plausible policy before responding.")
        return VerificationResult(
            valid=True,
            status="UNKNOWN",
            error_code="QUOTE_CLIPBOARD_RETRIEVAL_COMPLETE",
            feedback="Retrieval prerequisites are complete; semantic policy evaluation is still the model's responsibility.",
            rule="quote_clipboard_response_gate",
        )

    def render(self) -> str:
        lines = [
            "# Quote approval clipboard",
            "",
            f"Stage: {self.state.stage}",
            f"Next goal: {self.state.next_goal}",
            "",
            "Retrieved:",
            f"- Quote: {'yes' if self.state.quote_retrieved else 'no'}",
            f"- Quote line items: {'yes' if self.state.line_items_retrieved else 'no'}",
            f"- Candidate policies: {len(self.state.candidate_policies)}",
            f"- Policies inspected: {len(self.state.inspected_policy_ids)}",
            "",
            "Important:",
            "- This clipboard tracks retrieval only.",
            "- Do not claim an uninspected policy was evaluated.",
        ]
        if self.state.failed_queries:
            lines.extend(["", "Failed queries:"])
            for query in self.state.failed_queries[-self.max_items :]:
                lines.append(f"- {self._compact_text(query, 120)}")
        return self._fit("\n".join(lines))

    def as_dict(self) -> dict:
        return {
            "stage": self.state.stage,
            "next_goal": self.state.next_goal,
            "quote_retrieved": self.state.quote_retrieved,
            "quote_id": self.state.quote_id,
            "quote_fields": dict(self.state.quote_fields),
            "line_items_retrieved": self.state.line_items_retrieved,
            "line_item_count": self.state.line_item_count,
            "line_items": list(self.state.line_items),
            "candidate_policies": dict(self.state.candidate_policies),
            "inspected_policy_ids": sorted(self.state.inspected_policy_ids),
            "failed_queries": list(self.state.failed_queries),
        }

    def extract_query_facts(self, query: str) -> QueryFacts:
        stripped = query.strip()
        query_type = "sosl" if stripped.lower().startswith("find") else "soql" if stripped.lower().startswith("select") else "unknown"
        objects = {match.group(1) for match in FROM_OBJECT_RE.finditer(query)}
        selected_fields = set()

        select_match = SELECT_FIELDS_RE.search(query)
        if select_match:
            selected_fields.update(self._split_fields(select_match.group(1)))

        for match in RETURNING_RE.finditer(query):
            objects.add(match.group(1))
            selected_fields.update(self._split_fields(match.group(2)))

        lowered = query.lower()
        targets_line_items = "quotelineitem" in lowered or "quotelineitems" in lowered
        targets_policy = "knowledge__kav" in lowered or "knowledge" in lowered or "policy" in lowered
        facts = QueryFacts(
            query_type=query_type,
            objects=objects,
            selected_fields=selected_fields,
            targets_quote=("Quote" in objects or "quote" in lowered) and not targets_line_items and not targets_policy,
            targets_line_items=targets_line_items,
            targets_policy=targets_policy,
            retrieves_policy_detail=bool(selected_fields & SUBSTANTIVE_POLICY_FIELDS),
        )
        return facts

    def extract_observation_facts(self, observation: Any, info: Optional[Mapping[str, Any]] = None) -> ObservationFacts:
        info = info or {}
        end_reason = info.get("end_reason") if isinstance(info, Mapping) else None
        if isinstance(end_reason, Mapping):
            return ObservationFacts(failed=True)
        records = self._records_from_observation(observation)
        return ObservationFacts(failed=False, records=records, record_count=len(records))

    def _determine_stage(self) -> None:
        if not self.state.quote_retrieved:
            self.state.stage = "retrieve_quote"
            self.state.next_goal = "Retrieve the target quote."
        elif not self.state.line_items_retrieved:
            self.state.stage = "retrieve_line_items"
            self.state.next_goal = "Retrieve the quote line items."
        elif not self.state.candidate_policies:
            self.state.stage = "retrieve_candidate_policies"
            self.state.next_goal = "Find plausible quote approval policies."
        elif not self.state.inspected_policy_ids:
            self.state.stage = "inspect_candidate_policies"
            self.state.next_goal = "Inspect the contents of plausible policies."
        else:
            self.state.stage = "evaluate_policy"
            self.state.next_goal = "Compare the inspected policy conditions with the quote evidence."

    def _records_from_observation(self, observation: Any) -> list[dict]:
        parsed = observation
        if isinstance(observation, str):
            text = observation.strip()
            if not text:
                return []
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                try:
                    parsed = ast.literal_eval(text)
                except (SyntaxError, ValueError):
                    return []

        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
        if isinstance(parsed, dict):
            for key in ("records", "result", "results"):
                value = parsed.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
            return [parsed]
        return []

    def _split_fields(self, fields_text: str) -> set[str]:
        fields = set()
        for raw in fields_text.split(","):
            field_name = raw.strip().split()[0].strip()
            if field_name and "(" not in field_name:
                fields.add(field_name)
        return fields

    def _add_failed_query(self, query: str) -> None:
        normalized = normalize_query(query)
        if normalized and normalized not in self.state.failed_queries:
            self.state.failed_queries.append(normalized)
        self.state.failed_queries = self.state.failed_queries[-self.max_items :]

    def _policy_key(self, record: Mapping[str, Any]) -> str:
        for key in ("Id", "KnowledgeArticleId", "Title", "Name", "UrlName"):
            value = record.get(key)
            if value:
                return str(value)
        return f"policy_{len(self.state.candidate_policies) + 1}"

    def _record_id(self, record: Mapping[str, Any]) -> Optional[str]:
        value = record.get("Id")
        return str(value) if value else None

    def _record_has_policy_detail(self, record: Mapping[str, Any]) -> bool:
        keys = set(record.keys())
        if not keys - TITLE_ONLY_FIELDS:
            return False
        return bool(keys & SUBSTANTIVE_POLICY_FIELDS)

    def _compact_record(self, record: Mapping[str, Any]) -> dict:
        compact = {}
        for key, value in record.items():
            if isinstance(value, (dict, list)):
                compact[key] = self._compact_text(str(value), 180)
            elif isinstance(value, str):
                compact[key] = self._compact_text(value, 240)
            else:
                compact[key] = value
        return compact

    def _invalid(self, error_code: str, feedback: str) -> VerificationResult:
        return VerificationResult(
            valid=False,
            error_code=error_code,
            feedback=feedback,
            status="INVALID",
            rule="quote_clipboard_response_gate",
        )

    def _fit(self, text: str) -> str:
        if len(text) <= self.max_chars:
            return text
        return text[: self.max_chars - 3].rstrip() + "..."

    def _compact_text(self, text: str, limit: int) -> str:
        text = " ".join(str(text or "").split())
        if len(text) <= limit:
            return text
        return text[: limit - 3].rstrip() + "..."
