"""Typed actions for the lead qualification symbolic layer.

The functions in this module are intentionally narrow. They compile symbolic
lead-qualification actions into fixed SOQL/SOSL templates and render only the
answer forms accepted by the BANT task contract.
"""

from decimal import Decimal, InvalidOperation
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional

from dsl.lead_qualification.prompts import (
    BANT_EXTRACTION_RULES,
    BANT_OPTIONAL_FIELDS,
    TIMELINE_POLICY_JUDGMENT_GUIDANCE,
)


BANT_FACTORS = ("Budget", "Authority", "Need", "Timeline")
BANT_STATUSES = ("supported", "failed", "unknown")
SELLER_TIMELINE_COMMITMENT_STRENGTHS = ("strong", "generic", "none", "unknown")
LEAD_ID_PATTERN = re.compile(r"\b00Q[0-9A-Za-z]{12}(?:[0-9A-Za-z]{3})?\b")


class FactorEvidence:
    def __init__(self, status: str = "unknown", evidence: str = ""):
        self.status = status
        self.evidence = evidence


class BANTState:
    def __init__(self):
        self.factors: Dict[str, FactorEvidence] = {
            factor: FactorEvidence() for factor in BANT_FACTORS
        }
        self.product_names: List[str] = []
        self.quantities: Dict[str, int] = {}
        self.budget_amount: Optional[Decimal] = None
        self.requested_timeline_days: Optional[int] = None
        self.client_timeline: str = ""
        self.seller_timeline_feasibility: str = ""
        self.seller_timeline_commitment_strength: str = "unknown"
        self.total_requested_units: Optional[int] = None
        self.computed_total: Optional[Decimal] = None
        self.installation_policy: List[Dict[str, Any]] = []
        self.policy_required_installation_days: Optional[int] = None
        self.policy_timeline_evidence: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "factors": {
                factor: {
                    "status": evidence.status,
                    "evidence": evidence.evidence,
                }
                for factor, evidence in self.factors.items()
            },
            "product_names": list(self.product_names),
            "quantities": dict(self.quantities),
            "budget_amount": str(self.budget_amount) if self.budget_amount is not None else None,
            "requested_timeline_days": self.requested_timeline_days,
            "client_timeline": self.client_timeline,
            "seller_timeline_feasibility": self.seller_timeline_feasibility,
            "seller_timeline_commitment_strength": self.seller_timeline_commitment_strength,
            "total_requested_units": self.total_requested_units,
            "computed_total": str(self.computed_total) if self.computed_total is not None else None,
            "installation_policy": list(self.installation_policy),
            "policy_required_installation_days": self.policy_required_installation_days,
            "policy_timeline_evidence": self.policy_timeline_evidence,
        }


class TimelinePolicyJudgment:
    def __init__(
        self,
        required_installation_days: Optional[int] = None,
        policy_evidence: str = "",
        timeline_status: str = "unknown",
        timeline_evidence: str = "",
    ):
        self.required_installation_days = required_installation_days
        self.policy_evidence = policy_evidence
        self.timeline_status = timeline_status
        self.timeline_evidence = timeline_evidence


def extract_target_lead_id(text: str) -> Optional[str]:
    """Extract the target Lead.Id from a task prompt."""

    match = LEAD_ID_PATTERN.search(text or "")
    return match.group(0) if match else None


def query_lead(lead_id: str) -> str:
    _validate_lead_id(lead_id)
    return (
        "SELECT Id, FirstName, LastName, Company, Email, Phone, Status, Title, "
        "CreatedDate, ConvertedDate, IsConverted, OwnerId "
        f"FROM Lead WHERE Id = '{lead_id}'"
    )


def query_voice_call_transcripts(lead_id: str) -> str:
    _validate_lead_id(lead_id)
    return (
        "SELECT Id, LeadId__c, Body__c, CreatedDate, EndTime__c "
        "FROM VoiceCallTranscript__c "
        f"WHERE LeadId__c = '{lead_id}'"
    )


def query_products_by_name(product_names: Iterable[str]) -> Optional[str]:
    names = _clean_names(product_names)
    if not names:
        return None
    clauses = [f"Name LIKE '%{_escape_like(name)}%'" for name in names]
    return (
        "SELECT Id, Name, Description, IsActive, External_ID__c "
        "FROM Product2 WHERE " + " OR ".join(clauses)
    )


def query_pricebook_entries(product_ids: Iterable[str]) -> Optional[str]:
    ids = [_escape_literal(item) for item in product_ids if item]
    if not ids:
        return None
    quoted_ids = ", ".join(f"'{item}'" for item in ids)
    return (
        "SELECT Id, Product2Id, Pricebook2Id, UnitPrice "
        f"FROM PricebookEntry WHERE Product2Id IN ({quoted_ids})"
    )


def query_installation_policy() -> str:
    return (
        "FIND {installation timeline policy implementation deployment} "
        "IN ALL FIELDS "
        "RETURNING Knowledge__kav(Id, Title, Summary, FAQ_Answer__c)"
    )


def respond_to_user(missing_requirement: str, context: str = "") -> str:
    """Render a clarification question for information only the user can provide."""

    if missing_requirement == "target_lead_id":
        return "Could you provide the Salesforce Lead ID for the lead you want me to qualify?"
    return "Could you provide the missing information needed to complete the lead qualification?"


def extract_bant_evidence_prompt(
    task_query: str,
    lead_records: List[Mapping[str, Any]],
    transcript_records: List[Mapping[str, Any]],
) -> str:
    transcript_blocks = []
    for record in transcript_records:
        transcript_blocks.append(
            f"Transcript {record.get('Id', '')}:\n{record.get('Body__c', '')}"
        )
    return (
        "Extract lead-specific BANT evidence from the transcripts. Return exactly one JSON object. "
        "Do not include multi-step analysis, bullet lists, markdown, or prose outside the JSON. "
        "Use status supported, failed, or unknown for each of Budget, Authority, Need, Timeline.\n\n"
        f"Rules:\n{BANT_EXTRACTION_RULES.rstrip()}\n\n"
        f"Optional fields may be included when explicit:\n{BANT_OPTIONAL_FIELDS.rstrip()}\n\n"
        f"Task:\n{task_query}\n\n"
        f"Lead records:\n{lead_records}\n\n"
        f"Transcripts:\n{chr(10).join(transcript_blocks)}"
    )


def extract_timeline_policy_judgment_prompt(
    state: BANTState,
    policy_records: List[Mapping[str, Any]],
) -> str:
    return (
        "Extract the installation timeline policy that applies to this lead and judge "
        "whether the Timeline BANT factor is supported, failed, or unknown. Return exactly "
        "one JSON object with no prose outside the JSON. "
        "Use the customer's requested timeline from the transcript, the "
        "seller's feasibility or commitment statement from the transcript, and the retrieved "
        "Knowledge policy records. Use total_requested_units from the current BANT state when "
        "applying volume-based policy to the total deployment volume; do not treat each product "
        "in a bundle as a separate single-unit installation. Do not use unstated policy numbers.\n\n"
        "Required JSON fields:\n"
        "- required_installation_days: integer if the applicable policy gives a required "
        "installation duration, otherwise null\n"
        "- policy_evidence: short quote or summary from the relevant Knowledge policy, or empty string\n"
        "- Timeline: object with status supported, failed, or unknown, and evidence string\n\n"
        f"Judgment guidance:\n{TIMELINE_POLICY_JUDGMENT_GUIDANCE.rstrip()}\n\n"
        "If there is no requested timeline or no applicable policy evidence, preserve the "
        "transcript-based Timeline judgment unless it is unsupported.\n\n"
        f"Current BANT state:\n{state.as_dict()}\n\n"
        f"Knowledge policy records:\n{policy_records}"
    )


def render_failed_bant_response(state_or_mapping: Any) -> str:
    if isinstance(state_or_mapping, BANTState):
        factors = {
            factor: evidence.status
            for factor, evidence in state_or_mapping.factors.items()
        }
    else:
        factors = {
            factor: (state_or_mapping.get(factor) or {}).get("status", "unknown")
            for factor in BANT_FACTORS
        }
    failed = [factor for factor in BANT_FACTORS if factors.get(factor) == "failed"]
    return ", ".join(failed) if failed else "None"


def compute_budget_total(
    products: List[Mapping[str, Any]],
    pricebook_entries: List[Mapping[str, Any]],
    quantities: Mapping[str, int],
) -> Optional[Decimal]:
    if not products or not pricebook_entries:
        return None

    product_id_to_name = {product.get("Id"): product.get("Name", "") for product in products}
    effective_quantities: Mapping[str, int]
    if quantities:
        effective_quantities = quantities
    else:
        effective_quantities = {
            name: 1
            for name in product_id_to_name.values()
            if name
        }
        if not effective_quantities:
            return None

    price_by_product_id: Dict[str, Decimal] = {}
    for entry in pricebook_entries:
        try:
            price_by_product_id[entry.get("Product2Id")] = Decimal(str(entry.get("UnitPrice")))
        except (InvalidOperation, TypeError):
            continue

    total = Decimal("0")
    matched = False
    for requested_name, quantity in effective_quantities.items():
        product_id = _find_product_id(requested_name, product_id_to_name)
        if product_id is None or product_id not in price_by_product_id:
            continue
        total += price_by_product_id[product_id] * Decimal(int(quantity))
        matched = True
    return total if matched else None


def apply_deterministic_overrides(state: BANTState) -> None:
    if (
        state.computed_total is not None
        and state.budget_amount is not None
        and state.computed_total > state.budget_amount
    ):
        state.factors["Budget"].status = "failed"
        state.factors["Budget"].evidence = (
            f"Computed required cost {state.computed_total} exceeds stated budget {state.budget_amount}."
        )


def apply_timeline_policy_judgment(
    state: BANTState,
    judgment: TimelinePolicyJudgment,
) -> None:
    state.policy_required_installation_days = judgment.required_installation_days
    state.policy_timeline_evidence = judgment.policy_evidence
    state.factors["Timeline"].status = judgment.timeline_status
    state.factors["Timeline"].evidence = judgment.timeline_evidence


def _validate_lead_id(lead_id: str) -> None:
    if not extract_target_lead_id(lead_id or "") == lead_id:
        raise ValueError(f"Invalid Lead.Id: {lead_id}")


def _clean_names(product_names: Iterable[str]) -> List[str]:
    seen = set()
    names = []
    for raw_name in product_names:
        name = " ".join(str(raw_name).split())
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        names.append(name)
    return names


def _escape_literal(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


def _escape_like(value: str) -> str:
    return _escape_literal(value).replace("%", "\\%").replace("_", "\\_")


def _find_product_id(
    requested_name: str,
    product_id_to_name: Mapping[str, str],
) -> Optional[str]:
    requested = requested_name.lower()
    for product_id, product_name in product_id_to_name.items():
        if requested == str(product_name).lower():
            return product_id
    for product_id, product_name in product_id_to_name.items():
        name = str(product_name).lower()
        if requested in name or name in requested:
            return product_id
    return None


class LeadActions:
    extract_target_lead_id = staticmethod(extract_target_lead_id)
    query_lead = staticmethod(query_lead)
    query_voice_call_transcripts = staticmethod(query_voice_call_transcripts)
    query_products_by_name = staticmethod(query_products_by_name)
    query_pricebook_entries = staticmethod(query_pricebook_entries)
    query_installation_policy = staticmethod(query_installation_policy)
    respond_to_user = staticmethod(respond_to_user)
    render_failed_bant_response = staticmethod(render_failed_bant_response)
    respond_failed_bant_factors = staticmethod(render_failed_bant_response)

    @staticmethod
    def respond_success():
        return "None"
