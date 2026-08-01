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
LEAD_ID_RE = re.compile(r"\b00Q[A-Za-z0-9]{12,15}\b")

BANT_FACTORS = ("Budget", "Authority", "Need", "Timeline")
BANT_KEYWORDS = {
    "Budget": (
        "budget",
        "price",
        "cost",
        "spend",
        "allocated",
        "funding",
        "afford",
        "procurement",
        "purchase order",
    ),
    "Authority": (
        "authority",
        "approve",
        "approval",
        "decision maker",
        "cfo",
        "cto",
        "ceo",
        "vp",
        "manager",
        "procurement",
        "sign off",
        "final say",
    ),
    "Need": (
        "need",
        "pain",
        "problem",
        "challenge",
        "requirement",
        "requires",
        "looking for",
        "current system",
        "cannot",
        "support",
        "improve",
    ),
    "Timeline": (
        "timeline",
        "deadline",
        "deploy",
        "deployment",
        "go live",
        "quarter",
        "q1",
        "q2",
        "q3",
        "q4",
        "month",
        "week",
        "before",
        "by ",
        "asap",
    ),
}
GUIDE_OBJECT_HINTS = ("Knowledge", "Knowledge__kav", "FAQ__kav")
GUIDE_FIELDS = ("Id", "KnowledgeArticleId", "Title", "Name", "Summary", "FAQ_Answer__c", "Body", "Description")
LEAD_FACT_FIELDS = (
    "Id",
    "Name",
    "FirstName",
    "LastName",
    "Company",
    "Title",
    "Status",
    "Rating",
    "LeadSource",
    "Industry",
    "AnnualRevenue",
    "NumberOfEmployees",
    "OwnerId",
)
TRANSCRIPT_OBJECT_HINTS = ("Task", "Event", "Activity", "Call", "Transcript", "Note", "ContentNote", "EmailMessage")
TRANSCRIPT_FIELDS = (
    "Id",
    "Subject",
    "Description",
    "Body",
    "TextBody",
    "HtmlBody",
    "Comments",
    "CallDisposition",
    "ActivityDate",
    "CreatedDate",
)
TRANSCRIPT_SIGNAL_FIELDS = set(TRANSCRIPT_FIELDS) - {"Id", "CreatedDate"}
MISSING_LEAD_WARNING = "No lead facts have been retrieved."
MISSING_GUIDE_WARNING = "No qualification guide or policy evidence has been retrieved."
MISSING_TRANSCRIPT_WARNING = "No transcript/activity evidence has been retrieved."
MISSING_EVIDENCE_WARNINGS = {
    MISSING_LEAD_WARNING,
    MISSING_GUIDE_WARNING,
    MISSING_TRANSCRIPT_WARNING,
}


@dataclass
class LeadQueryFacts:
    query_type: str = "unknown"
    objects: Set[str] = field(default_factory=set)
    selected_fields: Set[str] = field(default_factory=set)
    targets_lead: bool = False
    targets_guide: bool = False
    targets_transcript: bool = False


@dataclass
class LeadObservationFacts:
    failed: bool = False
    records: List[dict] = field(default_factory=list)
    record_count: int = 0

    @property
    def has_records(self) -> bool:
        return self.record_count > 0


@dataclass
class LeadClipboard:
    stage: str = "collect_evidence"
    next_goal: str = "Gather lead facts, qualification guide evidence, and BANT-relevant customer evidence."
    lead_id: Optional[str] = None
    lead_facts: dict = field(default_factory=dict)
    qualification_guides: List[dict] = field(default_factory=list)
    transcript_evidence: List[dict] = field(default_factory=list)
    bant_evidence: Dict[str, List[str]] = field(
        default_factory=lambda: {factor: [] for factor in BANT_FACTORS}
    )
    unresolved: List[str] = field(default_factory=list)
    failed_queries: List[str] = field(default_factory=list)
    no_result_queries: List[str] = field(default_factory=list)


class LeadQualificationClipboard:
    """Compact deterministic evidence ledger for lead qualification tasks."""

    def __init__(self, max_chars: int = 1000, max_items: int = 5) -> None:
        self.max_chars = max(400, max_chars)
        self.max_items = max(2, max_items)
        self.state = LeadClipboard()

    def reset(self, query: str = "", routing_result: Optional[Mapping[str, Any]] = None) -> None:
        self.state = LeadClipboard()
        lead_id = self._extract_lead_id(query)
        if lead_id:
            self.state.lead_id = lead_id
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

    def update(self, query: str, query_facts: LeadQueryFacts, observation_facts: LeadObservationFacts) -> None:
        if observation_facts.failed:
            self._add_failed_query(query)
            self._append_unique(self.state.unresolved, "Last query failed; revise rather than repeat it.")
            self._refresh_guidance()
            return

        if not observation_facts.has_records:
            self._add_no_result_query(query)
            self._append_unique(self.state.unresolved, "Last query returned no records; broaden or change the evidence search before repeating it.")
            self._refresh_guidance()
            return

        if query_facts.targets_lead:
            self._update_lead_facts(observation_facts.records)

        if query_facts.targets_guide:
            self._update_guides(observation_facts.records)

        if query_facts.targets_transcript:
            self._update_transcripts(observation_facts.records)

        if not any((query_facts.targets_lead, query_facts.targets_guide, query_facts.targets_transcript)):
            self._update_opportunistic_facts(observation_facts.records)

        self._refresh_guidance()

    def response_gate(self, action: Optional[Mapping[str, str]]) -> VerificationResult:
        if not action or str(action.get("name", "")).lower() != "respond":
            return VerificationResult(valid=True)
        return VerificationResult(
            valid=True,
            status="UNKNOWN",
            error_code="LEAD_CLIPBOARD_WARNINGS_ONLY",
            feedback="Lead qualification clipboard is advisory only. It tracks retrieved evidence but does not decide BANT outcomes.",
            rule="lead_clipboard_advisory",
        )

    def render(self) -> str:
        guide_lines = self._render_list(self.state.qualification_guides, "none yet")
        transcript_lines = self._render_list(self.state.transcript_evidence, "none yet")
        lead_lines = self._render_mapping(self.state.lead_facts, "none yet")
        bant_lines = []
        for factor in BANT_FACTORS:
            evidence = self.state.bant_evidence.get(factor, [])
            bant_lines.append(f"{factor}: {self._join_items(evidence, 'none yet')}")
        unresolved = self._join_items(self.state.unresolved, "none listed")
        failed = self._join_items([self._compact_text(query, 120) for query in self.state.failed_queries], "none")
        empty = self._join_items([self._compact_text(query, 120) for query in self.state.no_result_queries], "none")
        lines = [
            "# Lead qualification clipboard",
            "",
            "Purpose: compact BANT evidence ledger, not a qualification judge.",
            f"Next goal: {self.state.next_goal}",
            "",
            f"Lead facts: {lead_lines}",
            f"Qualification guide evidence: {guide_lines}",
            f"Transcript/activity evidence: {transcript_lines}",
            "",
            "# BANT evidence snippets",
            *bant_lines,
            "",
            f"Unresolved warnings: {unresolved}",
            f"Failed queries: {failed}",
            f"No-result queries: {empty}",
            "",
            "Use this with the lead scaffold. If asked for failed BANT factors, return only Budget, Authority, Need, Timeline, comma-separated, or None.",
        ]
        return self._fit("\n".join(lines))

    def as_dict(self) -> dict:
        return {
            "stage": self.state.stage,
            "next_goal": self.state.next_goal,
            "lead_id": self.state.lead_id,
            "lead_facts": dict(self.state.lead_facts),
            "qualification_guides": list(self.state.qualification_guides),
            "transcript_evidence": list(self.state.transcript_evidence),
            "bant_evidence": {factor: list(items) for factor, items in self.state.bant_evidence.items()},
            "unresolved": list(self.state.unresolved),
            "failed_queries": list(self.state.failed_queries),
            "no_result_queries": list(self.state.no_result_queries),
        }

    def extract_query_facts(self, query: str) -> LeadQueryFacts:
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
        object_text = " ".join(objects).lower()
        return LeadQueryFacts(
            query_type=query_type,
            objects=objects,
            selected_fields=selected_fields,
            targets_lead=("lead" in object_text or " lead " in f" {lowered} "),
            targets_guide=any(hint.lower() in object_text for hint in GUIDE_OBJECT_HINTS)
            or "qualification" in lowered
            or "bant" in lowered
            or "guide" in lowered
            or "policy" in lowered,
            targets_transcript=any(hint.lower() in object_text for hint in TRANSCRIPT_OBJECT_HINTS)
            or "transcript" in lowered
            or "call" in lowered
            or "activity" in lowered
            or "note" in lowered,
        )

    def extract_observation_facts(self, observation: Any, info: Optional[Mapping[str, Any]] = None) -> LeadObservationFacts:
        info = info or {}
        end_reason = info.get("end_reason") if isinstance(info, Mapping) else None
        if isinstance(end_reason, Mapping):
            return LeadObservationFacts(failed=True)
        records = self._records_from_observation(observation)
        return LeadObservationFacts(failed=False, records=records, record_count=len(records))

    def _update_lead_facts(self, records: List[dict]) -> None:
        if not records:
            return
        record = records[0]
        lead_id = record.get("Id") or self._extract_lead_id(str(record))
        if lead_id:
            self.state.lead_id = str(lead_id)
        for key, value in record.items():
            if key in LEAD_FACT_FIELDS or self._field_is_bant_relevant(key):
                self.state.lead_facts[key] = self._compact_value(value)
        self._assign_bant_evidence(record)

    def _update_guides(self, records: List[dict]) -> None:
        for record in records:
            compact = {}
            for key in GUIDE_FIELDS:
                if key in record and record[key] not in (None, ""):
                    compact[key] = self._compact_value(record[key], 360 if key == "FAQ_Answer__c" else 180)
            if not compact:
                compact = self._compact_record(record)
            if compact:
                self._upsert_list_item(self.state.qualification_guides, compact)
                self._assign_bant_evidence(record)
        self.state.qualification_guides = self.state.qualification_guides[-self.max_items :]

    def _update_transcripts(self, records: List[dict]) -> None:
        for record in records:
            compact = {}
            for key in TRANSCRIPT_FIELDS:
                if key in record and record[key] not in (None, ""):
                    compact[key] = self._compact_value(record[key], 300)
            if not compact:
                compact = self._compact_record(record)
            if compact:
                self._upsert_list_item(self.state.transcript_evidence, compact)
                self._assign_bant_evidence(record)
        self.state.transcript_evidence = self.state.transcript_evidence[-self.max_items :]

    def _update_opportunistic_facts(self, records: List[dict]) -> None:
        for record in records:
            keys = set(record.keys())
            if "LeadId" in keys or "WhoId" in keys or keys & TRANSCRIPT_SIGNAL_FIELDS:
                self._update_transcripts([record])
            elif keys & set(GUIDE_FIELDS):
                self._update_guides([record])
            elif "Company" in keys or "LeadSource" in keys or keys & set(LEAD_FACT_FIELDS):
                self._update_lead_facts([record])

    def _assign_bant_evidence(self, record: Mapping[str, Any]) -> None:
        text_parts = []
        for key, value in record.items():
            if value in (None, ""):
                continue
            if isinstance(value, (dict, list)):
                value_text = str(value)
            else:
                value_text = str(value)
            text_parts.append(f"{key}: {value_text}")
        text = " ".join(text_parts)
        lowered = text.lower()
        if not lowered:
            return
        snippet = self._compact_text(text, 180)
        for factor, keywords in BANT_KEYWORDS.items():
            if any(keyword in lowered for keyword in keywords):
                self._append_unique(self.state.bant_evidence[factor], snippet)
                self.state.bant_evidence[factor] = self.state.bant_evidence[factor][-self.max_items :]

    def _refresh_guidance(self) -> None:
        self.state.unresolved = [item for item in self.state.unresolved if item not in MISSING_EVIDENCE_WARNINGS]
        if not self.state.lead_facts:
            self._append_unique(self.state.unresolved, MISSING_LEAD_WARNING)
        if not self.state.qualification_guides:
            self._append_unique(self.state.unresolved, MISSING_GUIDE_WARNING)
        if not self.state.transcript_evidence and not any(self.state.bant_evidence.values()):
            self._append_unique(self.state.unresolved, MISSING_TRANSCRIPT_WARNING)

        empty_factors = [factor for factor in BANT_FACTORS if not self.state.bant_evidence.get(factor)]
        if not self.state.lead_facts:
            self.state.next_goal = "Retrieve the target Lead record and identifiers needed to find activities or transcripts."
        elif not self.state.qualification_guides:
            self.state.next_goal = "Retrieve the lead qualification guide or policy before judging BANT factors."
        elif empty_factors:
            self.state.next_goal = f"Find evidence for missing BANT factors: {', '.join(empty_factors)}."
        else:
            self.state.next_goal = "Compare BANT evidence against the qualification guide; answer in the requested format."
        self.state.stage = "evidence_ready" if self.state.lead_facts or self.state.qualification_guides or any(self.state.bant_evidence.values()) else "collect_evidence"
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

    def _add_no_result_query(self, query: str) -> None:
        normalized = normalize_query(query)
        if normalized and normalized not in self.state.no_result_queries:
            self.state.no_result_queries.append(normalized)
        self.state.no_result_queries = self.state.no_result_queries[-self.max_items :]

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
        for key in ("Id", "LeadId", "WhoId", "KnowledgeArticleId", "Title", "Name", "Subject"):
            value = item.get(key)
            if value:
                return f"{key}:{value}"
        return str(sorted(item.items()))[:120]

    def _render_mapping(self, value: Mapping[str, Any], fallback: str) -> str:
        if not value:
            return fallback
        parts = [f"{key}={self._compact_text(str(val), 80)}" for key, val in list(value.items())[: self.max_items]]
        return "; ".join(parts)

    def _render_list(self, items: List[dict], fallback: str) -> str:
        if not items:
            return fallback
        rendered = []
        for item in items[: self.max_items]:
            rendered.append(self._render_mapping(item, "empty"))
        return " | ".join(rendered)

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

    def _extract_lead_id(self, text: str) -> Optional[str]:
        match = LEAD_ID_RE.search(text or "")
        return match.group(0) if match else None

    def _field_is_bant_relevant(self, field_name: str) -> bool:
        lowered = field_name.lower()
        return any(keyword.strip().replace(" ", "") in lowered for keywords in BANT_KEYWORDS.values() for keyword in keywords)
