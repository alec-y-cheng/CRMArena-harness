"""Prompts for the named_entity_disambiguation symbolic layer."""


NED_SLOT_EXTRACTION_SYSTEM_PROMPT = """\
You extract product/entity and purchase-time slots from a customer-facing
request.

Return exactly one JSON object and no prose. Do not generate SQL/SOSL.
"""


NED_CANDIDATE_SELECTION_SYSTEM_PROMPT = """\
You select the product/entity candidate that best matches the customer's request
and retrieved current-customer purchase evidence.

Return exactly one JSON object and no prose.
"""


NED_CLARIFICATION_SYSTEM_PROMPT = """\
You write one concise customer-facing clarification question for a
purchased-product lookup.

Return exactly one JSON object and no prose. Do not answer the original request.
"""
