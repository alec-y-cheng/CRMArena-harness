# Lead Qualification Symbolic Layer Plan

## Goal

Build a task-specific symbolic layer for CRMArena-Pro lead qualification that:

* represents BANT evidence in a formal belief state;
* restricts the agent to typed actions;
* executes deterministic actions when the next step is unambiguous;
* lets the agent choose when multiple valid actions remain;
* predicts structural next-state effects without inventing database contents;
* verifies evidence grounding, action validity, and final answers.

The first version should model **evidence collection and belief-state transitions**, not every Salesforce workflow.

---

## Phase 1: Define the exact benchmark task

Collect every lead-qualification task instance and identify:

* prompt format;
* lead ID location;
* expected answer format;
* possible ground-truth values;
* reward metric;
* interactive versus noninteractive variants;
* user persona behavior;
* whether `None` represents a fully qualified lead.

Create a task contract:

```yaml
task_type: lead_qualification

input:
  lead_id: Lead.Id

output:
  type: set
  allowed_values:
    - Budget
    - Authority
    - Need
    - Timeline
  empty_value: None
  explanation_allowed: false
```

**Deliverable:** `specs/lead_qualification/task_contract.yaml`

---

## Phase 2: Map the relevant CRM schema

Identify the objects, fields, and relationships needed to retrieve evidence.

Likely entities:

```text
Lead
VoiceCall
Call transcript
Knowledge article
Possibly Task, Event, activity, or note records
```

For every relevant field, record:

* object name;
* API field name;
* field type;
* selectable status;
* filterable status;
* sortable status;
* parent or child relationships.

Example:

```yaml
VoiceCall:
  key: Id
  fields:
    Id:
      type: crm_id
    LeadId:
      type: reference
      references: Lead
    CallStartDateTime:
      type: datetime
    Transcript:
      type: text
      filterable: false
```

Use the CRMArena-Pro published schema and, when possible, Salesforce metadata. Use traces only to supplement this—not as the sole authority.

**Deliverable:** `specs/lead_qualification/schema.yaml`

---

## Phase 3: Collect and formalize the qualification policy

Retrieve the knowledge articles or benchmark guidance defining lead qualification.

For each BANT factor, document:

* what supports the factor;
* what causes it to fail;
* what counts as insufficient evidence;
* exceptions;
* ambiguous cases.

Example:

```yaml
Authority:
  supported_when:
    - lead has final purchasing authority
    - lead is an authorized decision maker

  failed_when:
    - another person must give final approval
    - lead only recommends or evaluates

  unresolved_when:
    - role in decision process is unclear
```

Keep the exact article ID and source excerpts attached to every formal rule.

**Deliverable:** `specs/lead_qualification/bant_policy.yaml`

---

## Phase 4: Design the formal belief state

Separate raw observations from semantic interpretations.

```python
@dataclass
class EvidenceClaim:
    factor: str
    status: str
    source_id: str
    source_excerpt: str
    verification_status: str
    extractor: str


@dataclass
class LeadQualificationState:
    lead_id: str

    lead_record: dict | None
    qualification_guides: list[dict]
    voice_calls: list[dict]
    transcripts: list[dict]

    bant: dict[str, str]
    claims: list[EvidenceClaim]

    attempted_actions: list[dict]
    failed_actions: list[dict]
    exhausted_sources: set[str]
    contradictions: list[dict]

    task_status: str
```

Recommended BANT states:

```text
unknown
supported
failed
conflicting
insufficient_evidence
```

Do not let the agent write trusted BANT statuses directly. It should propose evidence claims with provenance.

**Deliverable:** `symbolic/state.py`

---

## Phase 5: Define the typed action space

Start with a small action set:

```text
retrieve_lead
search_qualification_guides
inspect_qualification_guide
retrieve_voice_calls
inspect_transcript
search_additional_activity
propose_bant_claim
ask_user_for_clarification
submit_failed_factors
```

Each action needs:

```yaml
name:
parameters:
preconditions:
execution:
possible_outcomes:
guaranteed_updates:
observation_dependent_updates:
failure_behavior:
```

Example:

```yaml
name: retrieve_voice_calls

parameters:
  lead_id:
    type: Lead.Id

preconditions:
  - lead_id is known
  - voice_call_source is not exhausted

execution:
  type: soql_template
  template: retrieve_voice_calls.sql

possible_outcomes:
  - records_returned
  - empty_result
  - query_error

guaranteed_updates:
  - record_action_attempt

observation_dependent_updates:
  records_returned:
    - store_voice_calls
    - mark_voice_calls_checked

  empty_result:
    - mark_voice_calls_checked
    - mark_voice_call_source_exhausted

  query_error:
    - record_failed_action
```

The agent emits the typed action. The runtime compiles it into SOQL.

**Deliverables:**

```text
symbolic/actions.py
specs/lead_qualification/actions.yaml
queries/retrieve_voice_calls.sql
```

---

## Phase 6: Implement deterministic transition logic

Create a transition function:

```python
next_state = transition(
    current_state,
    typed_action,
    observation,
)
```

Before execution, the symbolic layer should predict only what is actually knowable:

```yaml
action: retrieve_voice_calls

guaranteed:
  target_object: VoiceCall
  expected_result_type: list[VoiceCall]
  retrieval_attempted: true

possible_branches:
  - records_returned
  - empty_result
  - query_error

unknown:
  - returned_record_ids
  - transcript_contents
  - resulting_bant_evidence
```

After the real observation arrives, the transition becomes deterministic.

```text
state + action + observation
→ updated formal state
```

Do not predict record IDs, proper nouns, or transcript contents that are not already known.

**Deliverable:** `symbolic/transitions.py`

---

## Phase 7: Add deterministic triggers

Automatically execute an action only when:

1. it is safe;
2. it is required;
3. exactly one reasonable action is enabled.

Examples:

```text
Lead ID known and lead not retrieved
→ retrieve_lead

All four BANT factors resolved
→ enable submit_failed_factors

Proposed answer includes unsupported factor
→ reject submission

Repeated query produced no new evidence
→ block exact repetition
```

When multiple meaningful options exist, return control to the agent:

```text
Timeline unresolved

Valid options:
- inspect another transcript
- search activity notes
- ask user for clarification
```

Avoid enforcing a fixed order such as:

```text
lead → guide → calls → transcripts → answer
```

Use evidence dependencies instead.

**Deliverable:** `symbolic/triggers.py`

---

## Phase 8: Implement natural-language evidence extraction

The agent should translate transcript and article language into formal claims.

Input:

```text
“Our CFO makes the final purchasing decision.”
```

Output:

```json
{
  "factor": "Authority",
  "status": "failed",
  "source_id": "0LQ...",
  "source_excerpt": "Our CFO makes the final purchasing decision."
}
```

Validate each claim deterministically:

* factor is one of the four allowed values;
* status is valid;
* source ID was actually retrieved;
* source excerpt appears verbatim in the source;
* claim does not reference unseen records;
* duplicate or contradictory claims are detected.

Initially, the semantic correctness can remain an agent responsibility. Later, add a second semantic verifier if needed.

**Deliverables:**

```text
extractors/bant_extractor.py
verifiers/evidence_claim_verifier.py
```

---

## Phase 9: Define evidence precedence and contradictions

Specify what happens when sources disagree.

Initial conservative rule:

```text
Supported claim + failed claim for same factor
→ factor becomes conflicting
→ final submission disabled
→ retrieve another source or ask for clarification
```

Track:

* source timestamp;
* source type;
* whether the statement came from the user or CRM;
* exact excerpt;
* whether the policy article supports the interpretation.

Do not silently let the newest or highest-confidence claim overwrite the other one in version one.

**Deliverable:** `symbolic/evidence_resolution.py`

---

## Phase 10: Define completion and termination rules

Completion:

```text
All four factors resolved
→ final answer may be submitted
```

Recovery:

```text
Factor unresolved and unchecked sources remain
→ retrieve more evidence

Factor unresolved and no sources remain
→ ask user for clarification

Contradictory evidence
→ inspect another source or ask clarification
```

Safety limits:

```text
Repeated action with no new evidence
→ reject repetition

Maximum environment steps reached
→ terminate with unresolved status

Maximum clarification turns reached
→ abstain or use benchmark-compatible fallback
```

Be careful with the benchmark: if it does not permit an `unable_to_determine` answer, keep that as an internal state and decide how the benchmark-facing system should handle it.

**Deliverable:** `symbolic/termination.py`

---

## Phase 11: Implement the verifier stack

Use separate verifiers for separate concerns.

### Action-schema verifier

Checks:

* action exists;
* parameters have correct types;
* required parameters are present.

### Grounding verifier

Checks:

* lead ID matches the task;
* record IDs were retrieved;
* source excerpts exist;
* proposed answer factors have evidence.

### State-precondition verifier

Checks:

* action is enabled in the current state;
* source is not exhausted;
* final answer is not premature.

### Final-answer verifier

Checks:

* only allowed BANT factors or `None`;
* no repeated factors;
* every returned factor has formal failed status;
* no known failed factor is omitted;
* no explanation is appended.

**Deliverables:**

```text
verifiers/action_verifier.py
verifiers/state_verifier.py
verifiers/final_answer_verifier.py
```

---

## Phase 12: Decide how the agent chooses actions

Start with this control policy:

```text
If exactly one deterministic mandatory action exists:
    symbolic runtime executes it.

Otherwise:
    DSL exposes valid typed actions.
    agent selects one.

Verifier checks the selection.
If valid:
    execute it.
If invalid:
    return structured repair feedback.
```

Agent input should include:

```text
Current formal belief state
Known evidence
Unresolved factors
Available sources
Valid actions
Blocked actions and reasons
```

The agent remains responsible for strategic choices under uncertainty, but it cannot invent arbitrary actions.

**Deliverable:** `controller/lead_qualification_controller.py`

---

## Phase 13: Mine existing trajectories

Use successful and failed runs to identify:

* commonly queried objects and fields;
* alternate valid retrieval strategies;
* repeated empty-result patterns;
* query errors;
* premature final answers;
* frequently confused BANT factors;
* user follow-ups;
* paths your DSL does not support.

For every trajectory, replay only the actions and observations:

```text
saved action
+ saved observation
→ symbolic transition
```

Measure:

* action coverage;
* unsupported valid actions;
* incorrectly blocked actions;
* state-update accuracy;
* final-answer consistency;
* loops and unnecessary actions.

Do not use success frequency as proof that a workflow step is required.

**Deliverable:** `analysis/replay_lead_qualification.py`

---

## Phase 14: Build an edge-case test suite

Include cases for:

* lead not found;
* no calls found;
* multiple transcripts;
* one transcript covering all four factors;
* no knowledge article;
* user supplies policy details directly;
* indirect BANT evidence;
* contradictory evidence;
* all factors supported;
* one failed factor;
* multiple failed factors;
* one permanently unresolved factor;
* malformed agent claim;
* fabricated source ID;
* repeated failed query.

**Deliverable:** `tests/test_lead_symbolic_layer.py`

---

## Phase 15: Run the ablation

Compare:

1. baseline CRMArena agent;
2. BANT prompt scaffold;
3. scaffold plus evidence clipboard;
4. typed actions plus formal belief state;
5. typed actions plus belief state plus symbolic triggers;
6. full version with verifier and final-answer control.

Measure:

* benchmark task success;
* unsupported BANT claims;
* premature submissions;
* omitted failed factors;
* invented evidence;
* query errors;
* repeated actions;
* environment steps;
* agent generations;
* user turns;
* token usage;
* verifier false positives.

The most important comparison is:

> Does the symbolic layer improve task success and grounding beyond simply giving the agent a better BANT prompt?

---

## Suggested code structure

```text
lead_symbolic/
├── specs/
│   └── lead_qualification/
│       ├── task_contract.yaml
│       ├── schema.yaml
│       ├── bant_policy.yaml
│       └── actions.yaml
├── symbolic/
│   ├── state.py
│   ├── transitions.py
│   ├── triggers.py
│   ├── evidence_resolution.py
│   └── termination.py
├── extractors/
│   └── bant_extractor.py
├── verifiers/
│   ├── action_verifier.py
│   ├── evidence_claim_verifier.py
│   ├── state_verifier.py
│   └── final_answer_verifier.py
├── controller/
│   └── lead_qualification_controller.py
├── queries/
│   ├── retrieve_lead.sql
│   ├── search_guides.sql
│   └── retrieve_voice_calls.sql
├── analysis/
│   └── replay_lead_qualification.py
└── tests/
    └── test_lead_symbolic_layer.py
```

## Recommended implementation order

Implement only this minimal vertical slice first:

```text
1. Task contract
2. Formal BANT state
3. retrieve_lead action
4. retrieve_voice_calls action
5. Observation-based belief updates
6. Agent-generated evidence claims with provenance
7. BANT state resolution
8. Final-answer verifier
9. Replay on existing trajectories
```

After that works, add:

```text
10. Qualification-guide retrieval
11. Contradiction handling
12. Additional activity sources
13. Automatic deterministic triggers
14. Interactive clarification
```

That prevents the project from becoming a full DSL-engine implementation before you know whether the core idea improves the benchmark.
