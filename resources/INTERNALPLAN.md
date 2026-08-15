## Internal General Runtime Plan

Scope: port `wrong_stage_rectification` and `policy_violation_identification` into the existing `ChatAgentGeneralRuntimeDSL` / `CanonicalGeneralRuntimeDriver` path. These are B2B internal-user tasks, so the external router and privacy/disclosure gates should be disabled for these workflows.

The goal is not to create new task-specific control loops. The task-specific system prompt should be materialized as a `WorkflowSpec`; the shared runtime should keep doing the generic work: frame the instance, acquire verified evidence, extract structured claims, validate the answer contract, and render the final answer.

## Task Families

### Wrong Stage Rectification

Benchmark prompt contract:

- Input usually provides an `Opportunity.Id`.
- Determine whether the current opportunity stage accurately reflects associated tasks.
- Return exactly one of: `Qualification`, `Discovery`, `Quote`, `Negotiation`, `Closed`, or `None`.
- Do not update Salesforce.

Required working objects:

- `Opportunity`: target record, current `StageName`, owner/account context if useful.
- `Task` / activity records associated with the opportunity: task subject, status, dates, description, owner, related opportunity field.
- Optional supporting objects only when needed by schema relationships: `Event`, `Contract`, `Quote`, or `OpportunityLineItem`, if the task prompt/rubric implies stage evidence can be inferred from those records.

WorkflowSpec:

- Add `dsl/general_runtime/workflow_specs/wrong_stage_rectification.json`.
- `workflow_id`: `wrong_stage_rectification`.
- `request_scope`: `internal_user`.
- `org_scope`: `b2b`.
- `answer_contract.type`: `stage_label_or_none`.
- `requirements`: target opportunity, associated task/activity evidence, inferred stage label.
- `completion.any_of`: `answer_contract_satisfied`, `clarification_paused`, `max_turns_reached`.
- Required checkpoints: `schema_validated`, `action_verified`, `answer_contract_gate`, `completion_predicates_evaluated`.
- Do not include `evidence_privacy_gate`.

Sub-agent prompts:

- Instance framer: extract the `Opportunity.Id`, requested output contract, and any explicit constraints from the user prompt or follow-up.
- Semantic extractor: read opportunity/task evidence and produce a structured claim containing current stage, task-derived stage signal, confidence, and evidence IDs/snippets.
- Final renderer: output only the stage label or `None`.
- Clarifier: ask only for missing user-held identifiers, usually the opportunity ID, if it cannot be recovered from the conversation.

### Policy Violation Identification

This is the benchmark task currently referred to as “solution violation identification” in notes. The task category in the B2B asset is `policy_violation_identification`.

Benchmark prompt contract:

- Input usually provides a `Case.Id`.
- Determine whether the agent breached a policy in the case.
- Return only the violated `Knowledge__kav.Id`, or `None` if no violation is found.

Required working objects:

- `Case`: target case record and related fields.
- Case conversation/evidence objects available in the schema, such as comments, emails, messages, or transcript-like records tied to the case.
- `Knowledge__kav`: policy articles that define allowed/prohibited support behavior.

WorkflowSpec:

- Add `dsl/general_runtime/workflow_specs/policy_violation_identification.json`.
- `workflow_id`: `policy_violation_identification`.
- `request_scope`: `internal_user`.
- `org_scope`: `b2b`.
- `answer_contract.type`: `violating_policy_article_id_or_none`.
- `requirements`: target case, case interaction evidence, candidate policy articles, violation judgment.
- `completion.any_of`: `answer_contract_satisfied`, `clarification_paused`, `max_turns_reached`.
- Required checkpoints: `schema_validated`, `action_verified`, `answer_contract_gate`, `completion_predicates_evaluated`.
- Do not include `evidence_privacy_gate`.

Sub-agent prompts:

- Instance framer: extract the `Case.Id`, requested policy-violation question, and output contract.
- Semantic extractor: compare case interaction evidence against retrieved policy articles and produce structured claims: violated article ID or `None`, policy rule, case evidence, and confidence.
- Final renderer: output only the `Knowledge__kav.Id` or `None`.
- Clarifier: ask only for missing user-held identifiers, usually the case ID, if absent.

## Action Space Changes

Keep the generic action categories. Add only narrow internal environment actions where current generic actions are too underspecified:

- `query_opportunity_by_id(object_id, fields)`: compiled `Opportunity` lookup by ID.
- `query_opportunity_activities(opportunity_id, fields)`: compiled retrieval of task/activity records related to an opportunity.
- `query_case_by_id(case_id, fields)`: compiled `Case` lookup by ID.
- `query_case_interactions(case_id, fields)`: compiled retrieval of case-related conversation/evidence records.
- `query_internal_policy_articles(search_terms, limit)`: compiled `Knowledge__kav` retrieval for internal policy evidence.

These should live in the generic action registry as environment actions, but their SOQL/SOSL templates should remain deterministic in executor handlers. The LLM supplies IDs, search terms, and semantic extraction; it should not write SOQL.

Existing symbolic actions are sufficient:

- `extract_claims`
- `compare_values`
- `rank_candidates`
- `filter_evidence`
- `render_answer`
- `return_none`
- `pause_for_clarification`

No new security action is needed for these internal workflows.

## Schema Changes

Keep `InstanceFrame` mostly unchanged. Minimal additions, if needed:

- Allow `target_entities` entries to carry typed IDs such as `Opportunity.Id` and `Case.Id`.
- Allow `required_evidence_instances` entries to name internal evidence types:
  - `opportunity_record`
  - `opportunity_activity`
  - `case_record`
  - `case_interaction`
  - `internal_policy_article`
- Add answer-contract validation for:
  - `stage_label_or_none`
  - `violating_policy_article_id_or_none`

Avoid adding task-specific fields like `stage_name` or `policy_article_id` to the global schema unless the renderer/verifier needs them. Prefer extracting those into generic `answer_candidate` / `claims` objects.

## Driver Integration

Small integration changes are enough:

- Add task dispatch in `ChatAgentGeneralRuntimeDSL.act`:
  - `wrong_stage_rectification` -> `workflow_id="wrong_stage_rectification"`.
  - `policy_violation_identification` -> `workflow_id="policy_violation_identification"`.
- Use the same model-extractor call path as the other general runtime workflows.
- Pass `external_router=None`.
- Ensure the workflow specs omit privacy gates so the driver does not call `disclosure_gate` for these workflows.

One implementation caveat: the current canonical driver still executes every environment action listed in a spec in order. For v1, keep each internal spec’s environment action list tight and deterministic. We do not need significant wrapper changes unless we want true LLM-selected next-action control flow later.

## Fairness Boundary

The workflow specs should be derived from the task prompts and available Salesforce schema, not from observed trajectories or ground-truth patterns.

Acceptable scaffolding:

- The answer contract from the benchmark prompt.
- The relevant Salesforce objects and relationships from the schema.
- Deterministic SOQL/SOSL templates that avoid syntax errors.
- Role-specific generic prompts for framing, semantic extraction, clarification, and rendering.

Avoid:

- Hardcoding specific task IDs, opportunity IDs, case IDs, policy IDs, stage labels beyond the allowed output set, or article names seen in trajectories.
- Encoding benchmark-specific failure patterns from previous runs.
- Adding a bespoke control loop per task family.
