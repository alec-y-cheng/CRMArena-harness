"""Generic prompt builders for the shared symbolic runtime."""

import json

from dsl.general_runtime.state import ExecutionState, WorkflowSpec

INSTANCE_FRAME_SYSTEM_PROMPT = """\
Populate an InstanceFrame for the active workflow spec. Do not invent workflow
requirements, evidence types, action names, object fields, or raw SOQL/SOSL.
Return exactly one JSON object.
"""

GENERIC_EXTRACTION_SYSTEM_PROMPT = """\
Fill the workflow extraction contract using only the provided conversation,
InstanceFrame, and retrieved evidence.

Return exactly one JSON object and no prose. Do not write SQL/SOSL. Do not
invent evidence ids, evidence types, action names, object fields, or facts not
present in the retrieved evidence.
"""

DISCLOSURE_GATE_SYSTEM_PROMPT = """\
You are the final selected-evidence disclosure gate for an external-facing CRM
assistant. Classify whether the exact answer candidate and selected evidence can
be disclosed to the current external user.

Return exactly one JSON object and no prose. Do not write SQL/SOSL. Do not
invent evidence ids, evidence types, subject scopes, or facts.
"""


def build_instance_frame_prompt(spec: WorkflowSpec, conversation_text: str, metadata=None, conversation_history=None) -> str:
    return """\
WorkflowSpec:
{spec}

Runtime metadata:
{metadata}

Latest user-visible conversation text:
{conversation}

User-visible conversation history:
{conversation_history}

Return an InstanceFrame JSON object for this workflow.
""".format(
        spec=json.dumps(spec.as_dict(), sort_keys=True),
        metadata=json.dumps(metadata or {}, sort_keys=True),
        conversation=conversation_text.strip(),
        conversation_history=json.dumps(conversation_history or [], sort_keys=True),
    )


def build_generic_extraction_prompt(state: ExecutionState) -> str:
    evidence_items = state.runtime_data.get("extraction_evidence_items")
    if evidence_items is None:
        evidence_items = [item.as_dict() for item in state.evidence_items]
    return """\
WorkflowSpec:
{spec}

Extraction contract:
{contract}

Conversation history:
{conversation}

InstanceFrame:
{frame}

Retrieved evidence items:
{evidence}

Current claims:
{claims}

Return one JSON object matching the extraction contract schema. The top-level
object must include:
{{
  "answer_candidate": {{
    "answer": "... or None",
    "confidence": "high|medium|low|unknown",
    "evidence": "...",
    "selected_evidence": [
      {{
        "evidence_id": "...",
        "evidence_type": "...",
        "subject_scope": "...",
        "safe_to_use": true,
        "reason": "..."
      }}
    ],
    "clarification_requirements": []
  }}
}}

Answer rendering policy:
{render_policy}

Answer guidance:
{answer_guidance}

If the render policy asks for a concise answer, return only the minimal span
that directly answers the latest user question. Do not include supporting
background, examples, caveats, product lists, or extra explanation unless the
user explicitly asks for that detail.
""".format(
        spec=json.dumps(state.workflow_spec.as_dict(), sort_keys=True),
        contract=json.dumps(state.workflow_spec.extraction_contract, sort_keys=True),
        render_policy=json.dumps(state.workflow_spec.render_policy, sort_keys=True),
        answer_guidance=str(state.workflow_spec.render_policy.get("answer_guidance") or ""),
        conversation=json.dumps(
            state.runtime_data.get("user_visible_conversation_history") or state.conversation_history,
            sort_keys=True,
        ),
        frame=json.dumps(state.instance_frame.as_dict() if state.instance_frame else None, sort_keys=True),
        evidence=json.dumps(evidence_items, sort_keys=True),
        claims=json.dumps([item.as_dict() for item in state.claims], sort_keys=True),
    )


def build_disclosure_gate_prompt(state: ExecutionState) -> str:
    selected_records = _selected_evidence_records(state)
    return """\
WorkflowSpec:
{spec}

Conversation history:
{conversation}

InstanceFrame:
{frame}

Answer candidate:
{answer_candidate}

Selected evidence labels:
{selected_evidence}

Selected evidence source records:
{selected_records}

Disclosure policy:
- Allow ordinary public customer-facing support information.
- Allow current-customer-scoped purchase/order/entity information only when the
  request is about the logged-in/current customer and the selected evidence is
  necessary to answer that request.
- Refuse evidence about other customers, private customer records outside the
  current-customer scope, internal operations, non-public company knowledge,
  internal commercial/sales/quote/routing policies, competitive strategy,
  proprietary roadmap/positioning, or any evidence whose scope is unknown and
  would reveal private or non-public information.
- Decide whether the selected content itself is public customer-facing
  information or non-public/internal/confidential information.
- If the answer candidate is "None" because no relevant public/current-customer
  evidence was found, use recommended_action="answer" unless the user's request
  itself asks for private, unauthorized, or confidential information. In that
  unsafe case use recommended_action="refuse".

Return JSON:
{{
  "safe_to_disclose": true,
  "recommended_action": "answer|refuse",
  "blocked_evidence_ids": [],
  "blocked_information": [],
  "reason": "brief disclosure rationale"
}}
""".format(
        spec=json.dumps(state.workflow_spec.as_dict(), sort_keys=True),
        conversation=json.dumps(
            state.runtime_data.get("user_visible_conversation_history") or state.conversation_history,
            sort_keys=True,
        ),
        frame=json.dumps(state.instance_frame.as_dict() if state.instance_frame else None, sort_keys=True),
        answer_candidate=json.dumps(state.answer_candidate or {}, sort_keys=True),
        selected_evidence=json.dumps(state.selected_evidence, sort_keys=True),
        selected_records=json.dumps(selected_records, sort_keys=True),
    )


def _selected_evidence_records(state: ExecutionState):
    selected_ids = set()
    for item in state.selected_evidence:
        evidence_id = str(item.get("evidence_id") or "")
        if evidence_id:
            selected_ids.add(evidence_id)
    if not selected_ids:
        return []
    records = []
    for item in state.evidence_items:
        if item.evidence_id in selected_ids:
            records.append(item.as_dict())
    return records
