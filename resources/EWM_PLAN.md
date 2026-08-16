# EWM Generalization Plan

## Goal

The next EWM version should move away from benchmark-specific symbolic
workflows and toward a reusable enterprise runtime. The immediate target is a
read-first Salesforce architecture where:

- the LLM infers what must be done for the current request;
- the symbolic layer validates and constrains how information is acquired;
- Salesforce MCP provides the execution tool space;
- the runtime stores evidence, provenance, privacy decisions, and completion
  state;
- write operations and next-state prediction are deferred until the read system
  is working.

The central claim should be:

> EWM is not a library of benchmark-specific workflows. It is a reusable
> enterprise runtime where an LLM infers the current task frame, while the
> symbolic layer constrains how evidence is acquired, stored, verified, and
> disclosed.

This version should not hand-author task-family WorkflowSpecs for the near-term
read path. It should also avoid deterministic code paths that encode BANT, KQA,
NED, WSR, PVI, or other CRMArena task families as fixed algorithms. The runtime
should provide generic mechanics; the model should infer task requirements from
the prompt and conversation.

## Immediate Read-Based Architecture

The read-side runtime should follow this loop:

```text
user request
  -> LLM-inferred InstanceFrame
  -> EnvironmentIR / reachable information
  -> LLM selects MCP read action from available tool space
  -> runtime validates action against schema and inferred constraints
  -> Salesforce SObject Reads MCP executes
  -> observation normalized into ExecutionState
  -> evidence / disclosure / completion verifier
  -> respond, clarify, refuse, or continue
```

The LLM should not write directly against arbitrary hidden implementation
details. It can reason over the visible task, the MCP tool menu, the current
ExecutionState, and the reachable-information graph. The runtime validates that
the selected MCP call is schema-valid, compatible with inferred constraints,
and safe to execute.

Salesforce SObject Reads MCP should be the immediate execution backend for this
read path. It is acceptable for MCP tools to expose schema discovery, SOQL
query, SOSL search, relationship traversal, and user context. However, MCP does
not itself maintain EWM state. The EWM still needs a thin client/normalizer
around MCP to standardize calls, errors, observations, provenance, and
benchmark logging.

## Generic Runtime Objects

### InstanceFrame

`InstanceFrame` is inferred by the LLM for the current request. It should be
generic and instance-specific, not a hand-authored task-family workflow.

It should minimally contain:

```text
goal
request_summary
actor
entities_or_references
constraints
evidence_requirements
outcome_contract
response_contract
missing_information
```

The LLM is responsible for inferring these fields from the user-visible prompt,
system context, metadata, and conversation. The runtime is responsible for
validating that referenced objects, fields, scopes, and requested evidence
types are compatible with the environment.

`actor` captures what is known or inferred about the requester: internal user,
external customer, current-customer identity, unknown identity, or other
available metadata. This is not a task-family label. It is context used by
verifiers when deciding whether a proposed retrieval or response is appropriate.

Privacy constraints should live inside the general `constraints` field rather
than a separate top-level field. For example, the frame might contain a
constraint such as "only disclose information appropriate to the requester" or
"use public or current-customer-scoped evidence." The LLM infers these from the
privacy-aware prompt, system context, actor metadata, and user request; the
runtime validates proposed retrievals and responses against the inferred
constraints and evidence provenance.

`evidence_requirements` and `missing_information` are different:

- `evidence_requirements` describe what the system must retrieve or verify from
  the environment to answer safely, such as a public policy article, a current
  customer's order history, a target Account record, or related Opportunity
  context.
- `missing_information` describes user-held or prompt-missing details needed to
  proceed, such as which customer, which product, which timeframe, or which
  record reference.

In other words, evidence requirements are questions for Salesforce or the
enterprise environment. Missing information is what the user may need to
clarify before those environment reads can be targeted.

`outcome_contract` and `response_contract` should replace a narrow
`output_contract`.

- `outcome_contract` describes what must be true for the task goal to be
  satisfied. In a read task, that may mean "answer is supported by selected
  evidence." In a write task, that may mean "the intended Salesforce state
  transition was executed and verified."
- `response_contract` describes what should be returned to the user once the
  outcome is satisfied or blocked. For reads, this may be a short factual
  answer. For writes, it may be a success confirmation, a blocked-action
  explanation, or an approval request.

This keeps the same frame usable for both read and write workflows. Rendering a
final answer is only one possible terminal communication step; it should not be
the definition of task completion.

### ExecutionState

`ExecutionState` is the mutable wrapper for the current trajectory. It contains
the current `InstanceFrame` plus the accumulated record of what the runtime has
done, observed, derived, verified, and proposed.

It should minimally track:

```text
frame
history
collected
  observations
  evidence
resolved
  entities
  facts
  unresolved
derived
  claims
  summaries
actions
  planned
  executed
  failed
verifier_results
candidates
  outcome
  response
completion_state
metrics
  model_calls
  env_calls
  errors
```

The LLM may populate semantic fields through structured outputs, but the runtime
owns the state transitions. An MCP observation is not just appended to chat
history; it is normalized into evidence and claims that later model calls can
inspect without reconstructing provenance from prose.

The grouping is intentional:

- `frame` is the current best interpretation of the request. It can be updated
  after clarification or new context.
- `history` stores raw conversation and action history for audit and replay.
- `collected.observations` stores raw MCP/tool outputs, while
  `collected.evidence` stores normalized, citable units derived from those
  outputs.
- `resolved.entities` stores pinned objects or IDs; `resolved.facts` stores
  non-entity facts; `resolved.unresolved` tracks remaining unknowns.
- `derived.claims` and `derived.summaries` store interpretations over evidence.
- `actions` records proposed, executed, and failed actions.
- `verifier_results` stores all verifier outputs, including disclosure,
  evidence-support, constraint, outcome, response, and write-safety checks.
- `candidates.outcome` and `candidates.response` store what the controller wants
  to achieve and say before verifiers approve completion.

### EnvironmentIR

`EnvironmentIR` represents what can be known or reached in the enterprise
environment. For read tasks, it should focus on information reachability rather
than workflow-specific control flow.

It should contain:

```text
object index
field metadata
relationship graph
queryable/searchable affordances
picklist/value metadata when available
scope annotations when available
MCP tool schemas
```

The key function is:

```python
reachable_information(state, env_ir, depth=1) -> list[ReachableInfo]
```

For example, if the current state contains an Opportunity, the reachability
view may expose related Account, Contact, Quote, Task, Event, Owner, Contract,
and line-item paths. It does not say that a benchmark-specific task must query
all of them. It gives the LLM a grounded local map of what can be queried next.

### EvidenceItem and Claim

`EvidenceItem` is a normalized retrieved record, text span, or MCP observation
with provenance:

```text
evidence_id
source_tool
source_object
record_id
subject_scope
payload
provenance
```

`Claim` is the LLM's structured interpretation of evidence:

```text
claim_id
claim_text
status
value
supporting_evidence_ids
confidence
reason
```

The runtime should require claims to cite valid evidence IDs. This is the
evidence-centered distinction from plain ReAct: answers are checked against
selected/cited evidence from the collected and derived state, not only against
the model's final prose.

The difference between an `EvidenceItem` and a `Claim` depends on the task.

For semantic tasks, the distinction is important. A large Knowledge article may
be retrieved as one `EvidenceItem`; the `Claim` is the extracted interpretation
or answer-supporting span, such as "phone support is available for premium
customers during business hours."

For direct lookup tasks, the distinction can be thin. If the question is "what
Account ID is this Contact associated with?", the `EvidenceItem` may be the
Contact record and the `Claim` may simply normalize one field from it:

```text
EvidenceItem: Contact record with AccountId = 001...
Claim: associated_account_id = 001..., supported by evidence_id=ev_1
```

The runtime should still create the claim because it gives the renderer and
verifiers a uniform interface. The claim may be a direct field projection rather
than a subjective interpretation.

### CompletionState

`CompletionState` is a generic loop-control object produced by the runtime and
verifiers. It should answer "is the workflow ready to finish, and if not, what
kind of next step is needed?" It should not encode benchmark-specific terminal
labels such as policy, permission, or refusal as top-level states. Those belong
in verifier results.

A minimal shape is:

```text
ready: bool
status: running | needs_information | needs_action | needs_verification | ready_to_respond | completed | blocked
needed:
  source: user | environment | verifier | action | none
  description: ...
next_action: optional planned action or clarification
verifier_summary: allowed | blocked | not_applicable | unknown
reason: ...
```

The completion evaluator should inspect the InstanceFrame, ExecutionState,
evidence requirements, explicit constraints, hidden environment constraints,
verifier results, outcome contract, and response contract.

The distinction between explicit and hidden constraints matters:

- explicit constraints come from the user request, system prompt, task prompt,
  or conversation, and should be represented in `InstanceFrame.constraints`;
- hidden environment constraints come from Salesforce schema, permissions,
  field-level security, validation rules, Flows, approval processes, triggers,
  and relationship structure, and should be represented in `EnvironmentIR`, MCP
  schemas, permission metadata, and later the symbolic flow graph.

The LLM does not need to know every hidden business rule. The symbolic layer
should evaluate hidden constraints and expose their verdicts or consequences to
the runtime.

Some completion predicates are deterministic: required fields exist, cited
evidence IDs are valid, a field is writable, a picklist value is valid, a
disclosure verifier blocked the response, an intended state delta was verified,
response format matches the response contract, or no enabled MCP action remains. Other
predicates are semantic: whether retrieved evidence actually supports the
requested outcome, or whether the proposed response faithfully explains the
state. Those semantic checks should be made by bounded LLM verifiers or
extractors that return structured claims and confidence; the runtime maps those
outputs into the generic `ready`, `status`, `needed`, and `next_action` fields.

Disclosure should be a generic verifier over the inferred frame and selected
evidence, not a deterministic branch keyed by task family. The verifier should
receive:

```text
actor metadata from ExecutionState.frame
constraints from ExecutionState.frame
selected/cited evidence from ExecutionState.collected / derived state
candidate outcome from ExecutionState.candidates
candidate response from ExecutionState.candidates
```

It should return a structured result such as `allowed`, `blocked`, or
`not_applicable`. If no disclosure-relevant constraint or sensitive selected
evidence is present, the verifier can return `not_applicable`. If selected
evidence or the candidate response would expose information inappropriate for
the actor and constraints, it returns `blocked`; the runtime records that in
`verifier_results` and sets completion to `blocked` or asks for a safer
candidate response.

This keeps completion generalizable. The runtime does not need hardcoded
benchmark completion rules. It only needs to distinguish whether it should
gather more information, perform more actions, verify the candidate outcome,
respond, or stop because a verifier blocked the current path. If the outcome is
not supported, the default should be to continue with another validated action
when one is available, not to immediately return `None`.

For read tasks:

```text
outcome_contract = answer supported by evidence
response_contract = return the requested answer format
completion = ready=true, status=ready_to_respond -> completed
```

For write tasks:

```text
outcome_contract = target state change is safe, executed, and verified
response_contract = confirm success or explain why blocked
completion = needs_action -> needs_verification -> ready_to_respond -> completed
```

## Directory Skeleton

Create a new top-level `ewm/` package for this redesigned runtime instead of
continuing to grow the CRMArena-specific `dsl/` folders.

```text
ewm/
  ir/
    __init__.py
    frame.py          # InstanceFrame, OutcomeContract, ResponseContract, EvidenceRequirement
    state.py          # ExecutionState, EvidenceItem, Claim, Observation
    environment.py    # EnvironmentIR, ObjectSchema, RelationshipGraph, ReachableInfo

  mcp/
    __init__.py
    client.py         # MCP client protocol / interface
    salesforce_reads.py
    normalizer.py     # MCP observation -> EvidenceItem / Observation
    salesforce_mutations.py   # later stub only

  runtime/
    __init__.py
    read_driver.py
    action_selector.py
    verifier.py
    privacy.py
    completion.py
    renderer.py

  mining/
    __init__.py
    schema_miner.py
    relationship_miner.py
    exhaust_importer.py
    workflow_template_miner.py

  dynamics/
    __init__.py
    flow_parser.py            # later write-side symbolic graph
    transition_collector.py   # later S_t, a_t, S_t+1 collection
    next_state_predictor.py   # later Qwen world-model interface
```

The existing `dsl/general_runtime/` implementation can remain as a reference
and benchmark harness while this new architecture is built. The new `ewm/`
package should not depend on hand-authored task-family WorkflowSpecs for the
read path.

## Initial Function Stubs

The first implementation should initialize the module layout with small,
typed stubs. The stubs should express interfaces before optimizing behavior.

```python
def infer_instance_frame(messages, env_summary) -> InstanceFrame: ...

def build_environment_ir_from_mcp_schema(client) -> EnvironmentIR: ...

def reachable_information(
    state: ExecutionState,
    env_ir: EnvironmentIR,
    depth: int = 1,
) -> list[ReachableInfo]: ...

def select_mcp_read_action(
    frame: InstanceFrame,
    state: ExecutionState,
    reachable: list[ReachableInfo],
    tools: list[MCPToolSchema],
) -> MCPCall: ...

def validate_mcp_call(
    call: MCPCall,
    state: ExecutionState,
    env_ir: EnvironmentIR,
    tool_schema: MCPToolSchema,
) -> ValidationResult: ...

def execute_mcp_call(client, call: MCPCall) -> MCPObservation: ...

def normalize_observation(
    call: MCPCall,
    observation: MCPObservation,
) -> list[EvidenceItem]: ...

def extract_claims(
    frame: InstanceFrame,
    state: ExecutionState,
    evidence: list[EvidenceItem],
) -> list[Claim]: ...

def evaluate_completion(
    frame: InstanceFrame,
    state: ExecutionState,
) -> CompletionState: ...

def render_response(
    frame: InstanceFrame,
    state: ExecutionState,
    completion: CompletionState,
) -> str: ...
```

These are intentionally generic. There should not be separate first-class
functions such as `extract_bant`, `route_kqa`, or `solve_wsr` in the new read
runtime. If task-specific patterns are useful, they should eventually emerge as
mined priors or reusable templates, not hardcoded benchmark branches.

## Incremental Implementation Order

### Phase 0: Understand and document Salesforce MCP

Before implementation, create a short MCP exploration note and small
non-mutating demo script. The goal is to make the execution substrate concrete
before wiring it into EWM.

The exploration should answer:

- how to authenticate to the Salesforce SObject Reads MCP server;
- which endpoint is used for production versus sandbox/scratch orgs;
- what tools the server exposes;
- what each tool's JSON schema looks like;
- how an LLM is expected to format a tool call;
- how tool results are returned;
- how schema discovery differs from record query/search;
- what errors look like for invalid object names, invalid fields, invalid SOQL,
  permission failures, and empty results.

The demo should show read-only examples for:

```text
list available MCP tools
get object/schema index
get detailed schema for one object
run one SOQL query
run one SOSL search
get current user context
```

The output of this phase should be a concise note, sample requests/responses,
and a confirmed mapping from MCP tool names to the future EWM call objects.

Initial artifacts:

- `resources/SALESFORCE_MCP_PHASE0.md`
- `scripts/probe_salesforce_mcp_reads.py`

### Phase 0.5: Mirror the Salesforce Hosted SObject Reads Interface Locally

I have contacted the CRMArena administrators to request access to the
CRMArena-Pro B2B Salesforce org with the privileges needed to evaluate the
official Salesforce Hosted MCP `platform/sobject-reads` server. Hosted MCP
requires org-level activation and an External Client App for OAuth
authentication, so the public benchmark API credentials alone are not
sufficient to enable the hosted server. While waiting for that access, the
read-side EWM should not be blocked on Hosted MCP configuration.

Instead, implement a local MCP-compatible Salesforce read adapter backed by
the Salesforce API credentials already provided by CRMArena. The goal is not
to create a CRMArena-specific tool interface. The adapter should mirror the
generic capabilities exposed by Salesforce's official Hosted SObject Reads
server as closely as practical.

Salesforce's standard `platform/sobject-reads` server is itself generic across
Salesforce orgs: the MCP tool definitions remain the same, while the
authenticated org determines the objects, fields, relationships, records, and
permissions visible through those tools. The local adapter should follow the
same principle. It should contain no CRMArena task-family knowledge, benchmark
routing logic, hardcoded object paths, or task-specific query sequences.

The initial local MCP surface should mirror the documented Hosted SObject Reads
tools:

```text
getObjectSchema
soqlQuery
find
getUserInfo
listRecentSobjectRecords
getRelatedRecords
```

The official Salesforce server defines these as generic read operations:
`getObjectSchema` discovers queryable objects, fields, values, and
relationships; `soqlQuery` retrieves records using SOQL; `find` performs SOSL
search across objects; `getUserInfo` returns authenticated-user context;
`listRecentSobjectRecords` returns recently viewed records of a requested
object type; and `getRelatedRecords` traverses a known relationship from a
resolved parent record. The official server is deterministic: the MCP server
does not decide which query the task requires. The agent selects a tool and
its arguments, and Salesforce returns the corresponding structured
observation. ([Developer][1])

The local implementation should preserve the same separation of
responsibilities:

```text
LLM / EWM
    |
    | chooses a generic read action
    v
Local Salesforce MCP Adapter
    |
    | translates MCP tool -> Salesforce API operation
    v
CRMArena-Pro B2B Salesforce Org
    |
    | returns actual org data/schema
    v
MCP Observation
    |
    v
ExecutionState / Evidence normalization
```

The MCP adapter should not infer the benchmark task or determine which records
the model ought to retrieve. For example, `soqlQuery` should execute a
model-proposed read-only SOQL query; it should not contain rules such as "if
this is a WSR task, query Opportunities and Quotes." Likewise,
`getRelatedRecords` should expose a generic relationship traversal rather than
hardcoding benchmark-relevant entity chains.

This distinction is important for the generalization claim. The architecture
may contain platform-specific adapters because Salesforce, ServiceNow, and
other enterprise systems expose different APIs and data models. It may also
construct environment-specific representations because different Salesforce
orgs contain different schemas and relationships. What it should avoid is
task- or benchmark-specific solution logic.

The desired boundary is:

```text
platform-specific       acceptable
    Salesforce APIs, SOQL, SOSL, SObjects

environment-specific    acceptable when discovered dynamically
    objects, fields, relationships, permissions in the connected org

task-specific           avoid
    KQA/WSR/NED/BANT branches
    fixed query sequences
    benchmark-authored WorkflowSpecs
```

The local Salesforce adapter should therefore be **org-agnostic within
Salesforce**. Connecting it to another Salesforce org should require different
credentials, not changes to the tool implementation. On connection, schema
discovery should determine what objects and relationships exist in that org.

This also provides the input for the read-side `EnvironmentIR`.
`getObjectSchema` or the corresponding Salesforce Describe APIs can be used to
construct the complete schema and relationship graph. Given the entities
currently resolved in `ExecutionState`, the EWM can then derive a local
information-reachability view describing what information is structurally
available next.

For example:

```text
ExecutionState
    resolved Opportunity O17
            |
            v
EnvironmentIR
    Opportunity
      -> Account
      -> Owner
      -> Quotes
      -> Contact Roles
      -> Activities
            |
            v
LLM chooses which direction is relevant to the goal
```

This is intentionally not a read WorkflowSpec. The symbolic layer models the
space of reachable observations, while the LLM performs the task-specific
reasoning required to choose among them. In this sense, the read-side symbolic
model is analogous to the write-side workflow graph: write workflows expose
reachable environment-state consequences, while the read representation
exposes reachable knowledge-state transitions.

The local MCP adapter should be treated as a temporary backend implementation,
not as a different EWM architecture. The EWM runtime should depend on a
generic MCP client/interface so that the backend can later be replaced with
Salesforce Hosted MCP without changing `InstanceFrame`, `ExecutionState`,
`EnvironmentIR`, action selection, evidence normalization, or verifier logic.

```text
                         EWM Runtime
                              |
                       MCP Read Interface
                              |
                  +-----------+-----------+
                  |                       |
             current backend          future backend
                  |                       |
        Local API-backed MCP     Salesforce Hosted MCP
                  |                       |
        Salesforce REST/API           Salesforce
                  |                       |
                  +------ target org ----+
```

The local implementation does not need to reproduce every Salesforce-managed
feature of Hosted MCP. In particular, the hosted `getObjectSchema` response can
include admin-authored contextual guidance in addition to standard schema
information. The goal is therefore not byte-for-byte emulation, but an
MCP-compatible Salesforce read adapter with the same core generic capability
surface. ([Developer][1])

If the CRMArena administrators grant the required Hosted MCP access, validate
the local adapter against the official `platform/sobject-reads` server and
replace or add the hosted implementation as a second backend. Salesforce's
Hosted MCP setup requires activation of the server in the target org and
registration of an External Client App with the appropriate OAuth
configuration. ([Developer][2])

Acceptance criteria for Phase 0.5:

* the MCP adapter exposes the core generic SObject Reads capabilities;
* all operations are read-only;
* the adapter uses live CRMArena Salesforce APIs rather than simulated data;
* no CRMArena task-family names or benchmark-specific query workflows appear
  in the MCP implementation;
* object and relationship information is discovered dynamically from the org;
* the same adapter can connect to a different Salesforce org by changing
  credentials/configuration rather than code;
* the baseline and EWM can be given exactly the same MCP tool surface;
* the EWM runtime does not depend on whether the backend is the local adapter
  or Salesforce Hosted MCP;
* `getObjectSchema`/schema discovery provides the initial source for building
  the read-side `EnvironmentIR`;
* once official Hosted MCP access is available, the local and hosted
  implementations can be compared for interface and behavioral compatibility.

One small naming suggestion: call the implementation something like **`SalesforceReadMCPAdapter`** rather than `CRMArenaMCP`. That reinforces in the codebase itself that CRMArena is merely the first connected org, not what the tool layer was designed around. 

Initial artifacts:

- `ewm/mcp/salesforce_read_adapter.py`
- `scripts/run_local_salesforce_mcp_reads.py`
- `ewm/mcp/tests/test_salesforce_read_adapter.py`

[1]: https://developer.salesforce.com/docs/platform/hosted-mcp-servers/references/reference/sobject-reads.html "SObject Reads | Reference | Hosted MCP Servers | Salesforce Developers"
[2]: https://developer.salesforce.com/docs/platform/hosted-mcp-servers/guide/setup-overview.html "Set Up Your Org | Hosted MCP Servers | Salesforce Developers"

### Phase 1: Rewrite plan and create skeleton modules

Update this plan and initialize the `ewm/` directory with empty modules and
interface stubs. Do not migrate benchmark runs yet.

Initial artifacts:

- `ewm/ir/` for `InstanceFrame`, `ExecutionState`, `EnvironmentIR`, evidence,
  claims, contracts, and reachability containers;
- `ewm/mcp/` for generic MCP calls, observations, validation results, the
  Salesforce read adapter, read-client wrapper, observation normalizer, and
  deferred mutation placeholder;
- `ewm/runtime/` for generic read-driver, action-selection, verifier,
  disclosure, completion, and rendering stubs;
- `ewm/mining/` for future schema, relationship, exhaust, and workflow-prior
  mining hooks;
- `ewm/dynamics/` for future Flow parsing, transition collection, and
  next-state prediction hooks;
- `ewm/tests/test_phase1_scaffold.py` for import and serialization health
  checks.

### Phase 2: Generic IR objects

Implement `InstanceFrame`, `OutcomeContract`, `ResponseContract`,
`EvidenceRequirement`, `ExecutionState`, `EvidenceItem`, `Claim`,
`Observation`, `EnvironmentIR`, and `ReachableInfo`.

Acceptance criteria:

- the same IR classes can represent KQA, NED, internal record lookup, and
  confidentiality-style requests;
- no CRMArena task-family names are required in the data model;
- all state objects serialize to JSON for logging and replay.

### Phase 3: Salesforce SObject Reads MCP integration

Implement a thin MCP client wrapper and Salesforce SObject Reads backend.

The wrapper should expose:

```text
list_tools
get_object_schema
soql_query
sosl_search
get_user_context
```

It should preserve raw MCP observations while also returning normalized
observations for the EWM runtime.

### Phase 4: EnvironmentIR and reachability

Build `EnvironmentIR` from MCP schema discovery.

The reachability layer should:

- expose valid objects, fields, and relationship paths;
- indicate which objects are reachable from known IDs or records;
- expose searchable objects when direct object choice is uncertain;
- avoid implying task-specific mandatory paths.

### Phase 5: Generic read driver

Implement the main read loop:

```text
infer InstanceFrame
build/update reachable information
ask LLM to select an MCP read action
validate action
execute MCP call
normalize observation
update ExecutionState
extract evidence-backed claims
evaluate completion
respond / clarify / refuse / continue
```

The LLM should choose among MCP tools and reachable information, but the runtime
must validate the call before execution.

### Phase 6: Verifiers

Implement generic verifiers:

- schema validity;
- MCP tool-call shape;
- inferred constraint compatibility;
- evidence support;
- disclosure;
- outcome contract;
- response contract;
- completion state.

These verifiers should be reusable across read tasks and should not encode
benchmark answers or task-specific branch logic.

### Phase 7: Matched MCP baselines

Run a matched comparison:

```text
Baseline: LLM + Salesforce SObject Reads MCP
EWM:      LLM + SObject Reads MCP + IR + ExecutionState + reachability + verifiers
```

This is a cleaner experiment than comparing raw ReAct SOQL/SOSL against the EWM
runtime, because both systems use the same Salesforce execution substrate.

### Phase 8: Mining-based workflow priors

After the generic read loop works, add mining modules that can propose reusable
workflow priors from schema, logs, successful traces, and enterprise exhaust.

The output should be suggestions such as:

```text
common entity types
common object paths
common evidence requirements
common outcome contracts
common response contracts
common completion patterns
```

These priors can guide the LLM and validators, but they should be derived from
data rather than hand-authored benchmark algorithms.

### Phase 9: Write-side dynamics later

Develop write support only after the read path is stable.

Use a separate Salesforce Developer Edition, scratch org, or sandbox. Do not
mutate the CRMArena benchmark org.

The write-side path should add:

- Salesforce SObject Mutations MCP;
- Flow metadata parsing;
- symbolic trigger/cascade graph;
- controlled mutation collector;
- `(S_t, a_t, S_{t+1}, delta S)` datasets;
- learned next-state predictor interface;
- action verifier that compares symbolic and learned predictions before
  execution.

The learned world model should be trained on Salesforce-generated transition
targets, not LLM-generated labels.

## Design Guardrails

- MCP is the execution interface, but not the whole EWM. EWM still adds state,
  provenance, validation, disclosure control, completion, outcome control, and
  response control.
- Avoid hand-authored benchmark WorkflowSpecs in the new read path.
- Avoid deterministic task-family solvers for benchmark tasks.
- Let the LLM infer task requirements, evidence needs, outcome contract, and
  response contract per instance.
- Keep deterministic code focused on schema validity, action validity,
  reachability, evidence bookkeeping, hidden environment constraints, and final
  outcome/response contract checks.
- Do not trigger disclosure checks from benchmark task labels. Use actor
  metadata, inferred constraints, selected/cited evidence from collected state,
  and candidate response.
- Expect the first generic read version to lose some benchmark-specific
  performance relative to the handcrafted DSL, but gain a much stronger
  generalization story.
- Do not claim learned next-state prediction for read-only CRMArena tasks.
- Use write-side world modeling only when actions can mutate enterprise state
  and consequences need to be predicted before execution.

## Test Plan

Unit tests:

- `InstanceFrame` accepts generic goals, constraints, evidence requirements,
  missing information, outcome contracts, and response contracts.
- `ExecutionState` serializes observations, evidence, claims, actions, and
  completion state.
- `EnvironmentIR` builds object and relationship graphs from mocked MCP schema
  responses.
- `reachable_information` returns only schema-valid objects, fields, and
  relationships.
- MCP call validation rejects nonexistent objects, nonexistent fields, invalid
  relationship paths, malformed filters, and retrievals incompatible with
  inferred constraints.
- Observation normalization converts MCP query/search results into
  `EvidenceItem`s with provenance.
- Completion evaluation produces a generic `ready`, `status`, `needed`,
  `next_action`, `verifier_summary`, and `reason` object.

Integration smoke tests:

- public knowledge-style question through SObject Reads MCP;
- purchase/entity lookup through customer-scoped evidence;
- internal opportunity/case lookup through reachable related objects;
- confidentiality-style request rejected by disclosure verifier based on actor,
  inferred constraints, selected/cited evidence, and candidate response;
- unsupported or underspecified request asks for clarification rather than
  fabricating an answer.

Ablations:

```text
LLM + MCP
LLM + MCP + InstanceFrame / ExecutionState
LLM + MCP + EnvironmentIR
LLM + MCP + EnvironmentIR + verifiers
```

The ablation goal is to show which parts of EWM improve reliability beyond the
MCP tool interface itself.
