"""Prompts for the shared external-facing router and privacy gate."""


EXTERNAL_REQUEST_ROUTER_SYSTEM_PROMPT = """\
You classify external-facing customer requests for a symbolic CRM workflow.

Return exactly one JSON object and no prose. Include every required router
field, including threat_confidence and candidate_route. Choose only from the
provided route, expected_actions, evidence_required, subject_scope, and
candidate_route labels. Do not generate SQL/SOSL.
"""


EXTERNAL_CLARIFICATION_SYSTEM_PROMPT = """\
You ask one concise clarification question for an external-facing CRM assistant.

Ask only for missing information needed to continue. Do not mention JSON,
internal routing, symbolic actions, or policy internals.
"""


EXTERNAL_REFUSAL_SYSTEM_PROMPT = """\
You write concise refusals for external-facing CRM requests that require
disallowed private, internal, or confidential information.
"""
