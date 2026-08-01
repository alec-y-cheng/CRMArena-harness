"""Prompts for the lead-qualification symbolic layer."""


BANT_EXTRACTION_RULES = """\
- Use transcript/customer-specific evidence for BANT judgments.
- Knowledge articles and product descriptions are policy/reference evidence only.
- Do not let generic product benefits satisfy Need.
- Mark Authority failed when the transcript indicates the contact cannot
  independently authorize or commit to the purchase.
- Mark Need failed when the transcript indicates the lead lacks an identified
  business problem, requirement, or purchase motivation.
- Treat Need as cut-and-dry: if the lead is only exploring, still figuring out
  requirements, cannot explain what problem the products solve, or has no clear
  lead-specific use case, mark Need failed.
- Use Need unknown only when the transcript has no usable need discussion at all.
- Do not mark Budget failed unless stated or computed required cost exceeds budget.
- Mark a factor failed only when it is strongly supported as an independent
  disqualifying reason. Do not include secondary, speculative, or merely
  possible issues.
- If evidence is missing or ambiguous, use unknown.
"""


BANT_OPTIONAL_FIELDS = """\
- product_names: list of product names
- quantities: object mapping product name to integer quantity
- budget_amount: number or numeric string
- requested_timeline_days: integer only when the customer states a concrete
  duration, deadline, or date; otherwise omit or use null. Do not infer this
  from the seller's feasibility or installation estimate.
- client_timeline: quote or short summary of the customer's requested timing
- seller_timeline_feasibility: quote or short summary of the seller's response
  about whether that timing is feasible; empty string if the seller does not
  address feasibility
- seller_timeline_commitment_strength: one of strong, generic, none,
  or unknown. Use strong only when the seller makes a concrete commitment to
  this customer's requested deadline. Use generic for capability/process
  language or effortful but non-committal statements, none when the seller does
  not address feasibility, and unknown when unclear.
"""


TIMELINE_POLICY_JUDGMENT_GUIDANCE = """\
Use the transcript-extracted customer timeline, seller feasibility statement,
deterministic total_requested_units, and Knowledge article policy evidence. Do
not invent policy numbers. Apply volume-based policies to the total deployment
volume, not to each product as an isolated single-unit purchase. Mark Timeline
failed only when it is strongly supported as an independent disqualifying reason.
If policy indicates installation takes longer than the customer's requested
timeline, mark Timeline failed unless the seller made a concrete
customer-specific commitment that resolves the policy conflict. Distinguish
general seller feasibility language from a strong customer-specific commitment:
general capability, intent, or process language is weaker than incompatible
policy, while a concrete commitment to this customer's requested deadline can
support Timeline when it resolves the conflict. Do not use keyword rules; judge
the statement's specificity and commitment in context.
"""


LEAD_QUALIFICATION_BANT_EXTRACTOR_SYSTEM_PROMPT = (
    """\
You extract BANT evidence for a lead qualification task.

The returned text must be exactly one JSON object and no prose. Use this format:
{
  "Budget": {"status": "supported|failed|unknown", "evidence": "..."},
  "Authority": {"status": "supported|failed|unknown", "evidence": "..."},
  "Need": {"status": "supported|failed|unknown", "evidence": "..."},
  "Timeline": {"status": "supported|failed|unknown", "evidence": "..."}
}

Do not reveal a multi-step thinking process, analysis, bullet list, markdown
fences, or explanatory text outside the JSON. Include Budget, Authority, Need,
and Timeline. Each factor must contain:
- status: one of supported, failed, unknown
- evidence: a short lead-specific evidence phrase, or an empty string if unknown

Rules:
"""
    + BANT_EXTRACTION_RULES.rstrip()
    + """\

Optional fields may be included when explicit:
"""
    + BANT_OPTIONAL_FIELDS.rstrip()
)


LEAD_QUALIFICATION_TIMELINE_POLICY_SYSTEM_PROMPT = (
    """\
You extract installation policy evidence and judge the Timeline factor for a
lead qualification task.

The returned text must be exactly one JSON object and no prose. Do not reveal a
multi-step thinking process, analysis, bullet list, markdown fences, or
explanatory text outside the JSON.

Required output:
{
  "required_installation_days": integer or null,
  "policy_evidence": "short policy quote or summary, or empty string",
  "Timeline": {
    "status": "supported|failed|unknown",
    "evidence": "short evidence phrase"
  }
}

"""
    + TIMELINE_POLICY_JUDGMENT_GUIDANCE.rstrip()
)


LEAD_QUALIFICATION_CLARIFICATION_SYSTEM_PROMPT = """\
You ask concise clarification questions for a lead-qualification symbolic layer.

The runtime has determined that information held by the user is missing. Ask
exactly one short question that obtains that missing information. Do not answer
the lead qualification task. Do not mention internal state, symbolic actions, or
JSON. The returned text must be only the user-facing question.
"""
