import ast
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Set

from verifiers.schema_utils import normalize_query
from verifiers.types import VerificationResult


FROM_OBJECT_RE = re.compile(r"\bFROM\s+([A-Za-z_][A-Za-z0-9_]*(?:__[a-zA-Z])?)\b", re.IGNORECASE)
RETURNING_RE = re.compile(r"\bRETURNING\s+([A-Za-z_][A-Za-z0-9_]*(?:__[a-zA-Z])?)\s*\(([^)]*)\)", re.IGNORECASE)
SELECT_FIELDS_RE = re.compile(r"^\s*SELECT\s+(.*?)\s+FROM\s+", re.IGNORECASE | re.DOTALL)
MONEY_OR_QUANTITY_FIELD_RE = re.compile(r"(amount|price|total|discount|quantity|term|status)", re.IGNORECASE)
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
QUOTE_FACT_FIELDS = {
    "Id",
    "Name",
    "Status",
    "TotalPrice",
    "GrandTotal",
    "Subtotal",
    "Discount",
    "Term",
    "ExpirationDate",
    "AccountId",
    "OpportunityId",
}
LINE_ITEM_FACT_FIELDS = {
    "Id",
    "QuoteId",
    "Product2Id",
    "ProductName",
    "Name",
    "Quantity",
    "UnitPrice",
    "Discount",
    "TotalPrice",
    "Subtotal",
}
POLICY_ID_FIELDS = ("Id", "KnowledgeArticleId", "Title", "Name", "UrlName")
POLICY_RENDER_FIELDS = ("Id", "Title", "Name", "FAQ_Answer__c", "Content", "Body", "Description", "Details")
POLICY_BUCKETS = ("discount", "bundle", "item_count", "timeline", "other")
POLICY_BUCKET_LABELS = {
    "discount": "Discount/price policy evidence",
    "bundle": "Bundle/configuration policy evidence",
    "item_count": "Line-item count policy evidence",
    "timeline": "Timeline/installation policy evidence",
    "other": "Other retrieved article evidence",
}
POLICY_BUCKET_KEYWORDS = {
    "discount": (
        "discount",
        "price",
        "pricing",
        "cost",
        "amount",
        "total",
        "volume",
        "tier",
        "threshold",
        "percent",
        "%",
    ),
    "bundle": (
        "bundle",
        "bundles",
        "bundled",
        "mandatory",
        "partner",
        "partners",
        "requires",
        "must also include",
        "configuration",
        "configured",
        "product combination",
    ),
    "item_count": (
        "line item",
        "line items",
        "number of items",
        "item count",
        "single quote",
        "maximum number",
        "more than",
    ),
    "timeline": (
        "timeline",
        "installation",
        "install",
        "deployment",
        "setup time",
        "schedule",
        "days",
    ),
}
REQUEST_DIMENSION_KEYWORDS = {
    "discount": ("discount", "price", "pricing", "cost", "amount", "total"),
    "item_count": ("number of items", "line items", "item count", "maximum number"),
    "bundle": ("bundle", "bundled", "partner", "product combination"),
    "timeline": ("timeline", "installation", "install", "deployment"),
}
MISSING_QUOTE_WARNING = "No quote facts have been retrieved."
MISSING_LINE_ITEMS_WARNING = "No line-item quantity/price/discount evidence has been retrieved."
MISSING_POLICY_WARNING = "No relevant policy/article evidence has been retrieved for the requested quote-compliance dimension."
IRRELEVANT_POLICY_WARNING = "Retrieved articles may be about a different policy dimension; do not answer with them unless they match the user's requested check."
MISSING_EVIDENCE_WARNINGS = {
    MISSING_QUOTE_WARNING,
    MISSING_LINE_ITEMS_WARNING,
    MISSING_POLICY_WARNING,
    IRRELEVANT_POLICY_WARNING,
}


@dataclass
class QueryFacts:
    query_type: str = "unknown"
    objects: Set[str] = field(default_factory=set)
    selected_fields: Set[str] = field(default_factory=set)
    targets_quote: bool = False
    targets_line_items: bool = False
    targets_policy: bool = False
    retrieves_policy_detail: bool = False


@dataclass
class ObservationFacts:
    failed: bool = False
    records: List[dict] = field(default_factory=list)
    record_count: int = 0

    @property
    def has_records(self) -> bool:
        return self.record_count > 0


@dataclass
class QuoteClipboard:
    stage: str = "collect_evidence"
    next_goal: str = "Gather quote, line-item, and policy facts needed for the approval answer."
    requested_policy_dimensions: List[str] = field(default_factory=list)
    quote_facts: dict = field(default_factory=dict)
    line_items: List[dict] = field(default_factory=list)
    policy_evidence: List[dict] = field(default_factory=list)
    policy_evidence_by_type: Dict[str, List[dict]] = field(
        default_factory=lambda: {bucket: [] for bucket in POLICY_BUCKETS}
    )
    unresolved: List[str] = field(default_factory=list)
    failed_queries: List[str] = field(default_factory=list)


class QuoteApprovalClipboard:
    """Compact deterministic evidence ledger for quote approval tasks."""

    def __init__(self, max_chars: int = 1000, max_items: int = 5) -> None:
        self.max_chars = max(400, max_chars)
        self.max_items = max(2, max_items)
        self.state = QuoteClipboard()

    def reset(self, query: str = "", routing_result: Optional[Mapping[str, Any]] = None) -> None:
        self.state = QuoteClipboard()
        self.state.requested_policy_dimensions = self._infer_requested_policy_dimensions(query)
        self._refresh_guidance()

    def record_verifier_failure(self, action: Optional[Mapping[str, str]], error_code: Optional[str]) -> None:
        if action and action.get("name") == "execute":
            self._add_failed_query(str(action.get("content", "")))
        if error_code:
            self._append_unique(self.state.unresolved, f"Last rejected action: {error_code}.")
        self._refresh_guidance()

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
            self._append_unique(self.state.unresolved, "Last query failed; revise rather than repeat it.")
            self._refresh_guidance()
            return

        if not observation_facts.has_records:
            self._append_unique(self.state.unresolved, "Last query returned no records; confirm whether this evidence is unnecessary before answering.")
            self._refresh_guidance()
            return

        if query_facts.targets_quote:
            self._update_quote_facts(observation_facts.records)

        if query_facts.targets_line_items:
            self._update_line_items(observation_facts.records)

        if query_facts.targets_policy:
            self._update_policy_evidence(observation_facts.records)

        if not any((query_facts.targets_quote, query_facts.targets_line_items, query_facts.targets_policy)):
            self._update_opportunistic_facts(observation_facts.records)

        self._refresh_guidance()

    def response_gate(self, action: Optional[Mapping[str, str]]) -> VerificationResult:
        if not action or str(action.get("name", "")).lower() != "respond":
            return VerificationResult(valid=True)
        return VerificationResult(
            valid=True,
            status="UNKNOWN",
            error_code="QUOTE_CLIPBOARD_WARNINGS_ONLY",
            feedback="Quote clipboard is advisory only. It does not block responses or judge semantic correctness.",
            rule="quote_clipboard_advisory",
        )

    def render(self) -> str:
        quote_lines = self._render_mapping(self.state.quote_facts, "none yet")
        line_item_lines = self._render_line_items()
        policy_lines = self._render_policy_evidence()
        requested = ", ".join(self.state.requested_policy_dimensions) if self.state.requested_policy_dimensions else "unspecified"
        unresolved = self._join_items(self.state.unresolved, "none listed")
        failed = self._join_items([self._compact_text(query, 120) for query in self.state.failed_queries], "none")
        lines = [
            "# Quote approval clipboard",
            "",
            "Purpose: compact evidence ledger, not a policy judge.",
            f"Next goal: {self.state.next_goal}",
            "",
            f"Quote facts: {quote_lines}",
            f"Line-item facts: {line_item_lines}",
            f"Requested policy dimension: {requested}",
            "Policy evidence:",
            policy_lines,
            f"Unresolved warnings: {unresolved}",
            f"Failed queries: {failed}",
            "",
            "Use this with the quote scaffold. Final answer must be exactly one Knowledge__kav Id or None; do not answer approve/reject.",
        ]
        return self._fit("\n".join(lines))

    def as_dict(self) -> dict:
        return {
            "stage": self.state.stage,
            "next_goal": self.state.next_goal,
            "requested_policy_dimensions": list(self.state.requested_policy_dimensions),
            "quote_facts": dict(self.state.quote_facts),
            "line_items": list(self.state.line_items),
            "policy_evidence": list(self.state.policy_evidence),
            "policy_evidence_by_type": {
                bucket: list(items) for bucket, items in self.state.policy_evidence_by_type.items()
            },
            "unresolved": list(self.state.unresolved),
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
        return QueryFacts(
            query_type=query_type,
            objects=objects,
            selected_fields=selected_fields,
            targets_quote=("Quote" in objects or "quote" in lowered) and not targets_line_items and not targets_policy,
            targets_line_items=targets_line_items,
            targets_policy=targets_policy,
            retrieves_policy_detail=bool(selected_fields & SUBSTANTIVE_POLICY_FIELDS),
        )

    def extract_observation_facts(self, observation: Any, info: Optional[Mapping[str, Any]] = None) -> ObservationFacts:
        info = info or {}
        end_reason = info.get("end_reason") if isinstance(info, Mapping) else None
        if isinstance(end_reason, Mapping):
            return ObservationFacts(failed=True)
        records = self._records_from_observation(observation)
        return ObservationFacts(failed=False, records=records, record_count=len(records))

    def _update_quote_facts(self, records: List[dict]) -> None:
        if not records:
            return
        record = records[0]
        for key, value in record.items():
            if key in QUOTE_FACT_FIELDS or MONEY_OR_QUANTITY_FIELD_RE.search(key):
                self.state.quote_facts[key] = self._compact_value(value)

    def _update_line_items(self, records: List[dict]) -> None:
        for record in records:
            compact = {}
            for key, value in record.items():
                if key in LINE_ITEM_FACT_FIELDS or MONEY_OR_QUANTITY_FIELD_RE.search(key):
                    compact[key] = self._compact_value(value)
            if compact:
                self._upsert_list_item(self.state.line_items, compact)
        self.state.line_items = self.state.line_items[-self.max_items :]

    def _update_policy_evidence(self, records: List[dict]) -> None:
        for record in records:
            evidence = {}
            for key in POLICY_RENDER_FIELDS:
                if key in record and record[key] not in (None, ""):
                    evidence[key] = self._compact_value(record[key], 360 if key in SUBSTANTIVE_POLICY_FIELDS else 180)
            if not evidence:
                for key, value in record.items():
                    if key in POLICY_ID_FIELDS or key in SUBSTANTIVE_POLICY_FIELDS:
                        evidence[key] = self._compact_value(value)
            if evidence:
                bucket = self._classify_policy_evidence(evidence)
                self._upsert_list_item(self.state.policy_evidence_by_type[bucket], evidence)
        for bucket in POLICY_BUCKETS:
            self.state.policy_evidence_by_type[bucket] = self.state.policy_evidence_by_type[bucket][-self.max_items :]
        self._refresh_relevant_policy_evidence()

    def _update_opportunistic_facts(self, records: List[dict]) -> None:
        for record in records:
            keys = set(record.keys())
            if "QuoteId" in keys or keys & LINE_ITEM_FACT_FIELDS:
                self._update_line_items([record])
            elif keys & set(POLICY_RENDER_FIELDS):
                self._update_policy_evidence([record])

    def _refresh_guidance(self) -> None:
        self.state.unresolved = [item for item in self.state.unresolved if item not in MISSING_EVIDENCE_WARNINGS]
        warnings = []
        if not self.state.quote_facts:
            warnings.append(MISSING_QUOTE_WARNING)
        if not self.state.line_items:
            warnings.append(MISSING_LINE_ITEMS_WARNING)
        self._refresh_relevant_policy_evidence()
        if not self._has_relevant_policy_evidence():
            warnings.append(MISSING_POLICY_WARNING)
            if self._has_any_policy_evidence():
                warnings.append(IRRELEVANT_POLICY_WARNING)
        for warning in warnings:
            self._append_unique(self.state.unresolved, warning)

        if not self.state.quote_facts:
            self.state.next_goal = "Retrieve the target quote facts, especially id/name/status/amount when available."
        elif not self.state.line_items:
            self.state.next_goal = "Retrieve line-item product, quantity, price, and discount facts if needed for the decision."
        elif not self._has_relevant_policy_evidence():
            self.state.next_goal = self._policy_search_goal()
        else:
            self.state.next_goal = "Compare quote facts, line-item facts, and relevant policy evidence; answer with exactly one article Id or None."
        self.state.stage = "evidence_ready" if self.state.quote_facts or self.state.line_items or self._has_any_policy_evidence() else "collect_evidence"
        self.state.unresolved = self.state.unresolved[-self.max_items :]

    def _records_from_observation(self, observation: Any) -> List[dict]:
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

    def _split_fields(self, fields_text: str) -> Set[str]:
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

    def _upsert_list_item(self, items: List[dict], item: dict) -> None:
        key = self._stable_item_key(item)
        for index, existing in enumerate(items):
            if self._stable_item_key(existing) == key:
                merged = dict(existing)
                merged.update(item)
                items[index] = merged
                return
        items.append(item)

    def _stable_item_key(self, item: Mapping[str, Any]) -> str:
        for key in ("Id", "QuoteId", "Product2Id", "KnowledgeArticleId", "Title", "Name"):
            value = item.get(key)
            if value:
                return f"{key}:{value}"
        return str(sorted(item.items()))[:120]

    def _render_mapping(self, value: Mapping[str, Any], fallback: str) -> str:
        if not value:
            return fallback
        parts = [f"{key}={self._compact_text(str(val), 80)}" for key, val in list(value.items())[: self.max_items]]
        return "; ".join(parts)

    def _render_line_items(self) -> str:
        if not self.state.line_items:
            return "none yet"
        rendered = []
        for item in self.state.line_items[: self.max_items]:
            rendered.append(self._render_mapping(item, "empty"))
        return " | ".join(rendered)

    def _render_policy_evidence(self) -> str:
        sections = []
        requested = set(self.state.requested_policy_dimensions)
        for bucket in POLICY_BUCKETS:
            items = self.state.policy_evidence_by_type.get(bucket, [])
            if not items:
                continue
            label = POLICY_BUCKET_LABELS[bucket]
            if requested and bucket not in requested and bucket != "other":
                label += " (not the requested policy dimension)"
            rendered = " | ".join(self._render_mapping(item, "empty") for item in items[: self.max_items])
            sections.append(f"{label}: {rendered}")
        return "\n".join(sections) if sections else "Policy evidence: none yet"

    def _refresh_relevant_policy_evidence(self) -> None:
        relevant = []
        requested = self.state.requested_policy_dimensions
        if requested:
            for bucket in requested:
                relevant.extend(self.state.policy_evidence_by_type.get(bucket, []))
        else:
            for bucket in POLICY_BUCKETS:
                relevant.extend(self.state.policy_evidence_by_type.get(bucket, []))
        self.state.policy_evidence = relevant[-self.max_items :]

    def _has_relevant_policy_evidence(self) -> bool:
        self._refresh_relevant_policy_evidence()
        return bool(self.state.policy_evidence)

    def _has_any_policy_evidence(self) -> bool:
        return any(self.state.policy_evidence_by_type.get(bucket) for bucket in POLICY_BUCKETS)

    def _classify_policy_evidence(self, evidence: Mapping[str, Any]) -> str:
        text = " ".join(str(value) for value in evidence.values() if value not in (None, ""))
        lowered = text.lower()
        scores = {
            bucket: sum(1 for keyword in keywords if keyword in lowered)
            for bucket, keywords in POLICY_BUCKET_KEYWORDS.items()
        }
        best_bucket = max(scores, key=scores.get)
        return best_bucket if scores[best_bucket] > 0 else "other"

    def _infer_requested_policy_dimensions(self, query: str) -> List[str]:
        lowered = (query or "").lower()
        dimensions = [
            bucket
            for bucket, keywords in REQUEST_DIMENSION_KEYWORDS.items()
            if any(keyword in lowered for keyword in keywords)
        ]
        return dimensions

    def _policy_search_goal(self) -> str:
        requested = self.state.requested_policy_dimensions
        if "discount" in requested:
            return "Retrieve discount, pricing, cost, amount, or volume-based policy evidence before considering bundle/configuration articles."
        if "item_count" in requested:
            return "Retrieve policy evidence about line-item count or maximum items per quote."
        if "bundle" in requested:
            return "Retrieve bundle/configuration policy evidence and verify it matches the requested product-combination check."
        if "timeline" in requested:
            return "Retrieve timeline, installation, or deployment policy evidence if that is the requested compliance check."
        return "Retrieve relevant quote approval policy/article evidence, or use explicit user-supplied policy rules."

    def _join_items(self, items: List[str], fallback: str) -> str:
        compact_items = [self._compact_text(item, 120) for item in items if item]
        return "; ".join(compact_items) if compact_items else fallback

    def _append_unique(self, items: List[str], item: str) -> None:
        item = self._compact_text(item, 180)
        if item and item not in items:
            items.append(item)

    def _compact_record(self, record: Mapping[str, Any]) -> dict:
        return {key: self._compact_value(value) for key, value in record.items()}

    def _compact_value(self, value: Any, limit: int = 240) -> Any:
        if isinstance(value, str):
            return self._compact_text(value, limit)
        if isinstance(value, (dict, list)):
            return self._compact_text(str(value), limit)
        return value

    def _fit(self, text: str) -> str:
        if len(text) <= self.max_chars:
            return text
        return text[: self.max_chars - 3].rstrip() + "..."

    def _compact_text(self, text: str, limit: int) -> str:
        text = " ".join(str(text or "").split())
        if len(text) <= limit:
            return text
        return text[: limit - 3].rstrip() + "..."
