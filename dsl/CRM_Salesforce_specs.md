# CRMArena Symbolic Layer / DSL Design Context

## Project Goal

We are exploring a symbolic layer for CRMArena-Pro.

The purpose of this layer is to:

* represent CRM entities, evidence, relationships, and task state formally;
* restrict agents to typed, grounded actions;
* model deterministic belief-state transitions;
* trigger known workflow steps when there is no meaningful uncertainty*;
* expose valid actions to the agent when strategic choice is still required;
* verify action parameters, evidence provenance, policy constraints, and final answers;
* reduce unsupported actions and hallucinated conclusions.

The LLM agent remains responsible for interpreting natural-language prompts, records, knowledge articles, transcripts, and user responses. It translates these into formal evidence claims. The symbolic layer then operates over those structured claims. Eventually, a formalized deterministic translator and parser will take the place of the LLM in parsing user responses and tool call observaitons.

---

## CRMArena-Pro Environment

### Benchmark Repository

* [Repository](https://github.com/SalesforceAIResearch/CRMArena)
* [Entity and Objects Schema Link](https://huggingface.co/datasets/Salesforce/CRMArenaPro/viewer)
* [Paper Appendix: Prompts and Final answer contracts (18-29), Dependency Graph (29), Data Generation (31)](https://arxiv.org/pdf/2505.18878)
* [Example trajectories for each task](https://github.com/SalesforceAIResearch/CRMArena/tree/main/results/shared/b2b/multi-turn)
* [Tool call formatting : SOQL/SOSL](https://developer.salesforce.com/docs/atlas.en-us.apexcode.meta/apexcode/langCon_apex_SOQL.htm)

### Environment Interface (Interactive)

The primary CRMArena chat environment exposes two high-level agent actions (This is for the interactive version of the benchmark where the LLM user witholds important information from the model initially):

```text
internal: execute(SOQL_or_SOSL)
external: respond(natural_language)
```

An `execute` action sends a SOQL or SOSL query to Salesforce and returns:

* matching records;
* an empty result;
* or a query/schema error.

A `respond` action either:

* submits the final answer;
* or communicates with the simulated user in interactive tasks.

These actions would compile into the benchmark’s underlying `execute` and `respond` interface.

In the original CRM Arena, the default option was based on tool-calls rather than the ReAct framework. The following list were the possible tool calls to select from:

```
TOOLS = [
    get_agents_with_max_cases,
    get_agents_with_min_cases,
    calculate_average_handle_time,
    get_start_date,
    get_period,
    get_agent_handled_cases_by_period,
    get_qualified_agent_ids_by_case_count,
    get_cases,
    get_non_transferred_case_ids,
    get_agent_transferred_cases_by_period,
    get_shipping_state,
    calculate_region_average_closure_times,
    get_order_item_ids_by_product,
    get_issue_counts,
    find_id_with_max_value,
    find_id_with_min_value,
    get_account_id_by_contact_id,
    get_purchase_history,
    get_month_to_case_count,
    search_knowledge_articles,
    search_products,
    get_issues,
    respond,
    get_livechat_transcript_by_case_id,
    get_email_messages_by_case_id
]
```
In CRMArena Pro, the ReAct framework is the default, wherein the action outputted by the model has to be a valid SOQL/SOSL query. In initial benchmarks, emitting invalid tool calls was a substantial reason for wasting agent turns and failing tasks. Having a defined action schema like the one above that can call precompiled valid SOQL queries will be useful. 

---

## Mutation and Transition Scope

CRMArena-Pro is substantially less mutation-heavy than workflow environments such as World of Workflows.

Most CRMArena tasks involve:

* reading CRM records;
* following object relationships;
* retrieving knowledge articles;
* interpreting natural-language evidence;
* answering a constrained question.

The benchmark does not primarily expose rich write actions. Therefore, the first symbolic layer should primarily model **belief-state and evidence-state transitions**, rather than complex changes to the underlying Salesforce database. The WoW symbolic layer of modeling hidden cascades triggered by actions will be less important here. Instead:

Example:

```text
transcript not retrieved
→ retrieve transcript
→ transcript stored as observed evidence
→ BANT claims extracted
→ formal BANT state updated
```

The symbolic layer should not invent the contents of unretrieved records. Before execution, it can predict:

* what object will be queried;
* which evidence slots might be resolved;
* what result type is expected;
* which outcome branches are possible;
* what dependencies or constraints apply.

Actual record values are bound only after Salesforce returns the observation.

---

## Available Schema Information

### CRM Objects

The benchmark defines 27 Salesforce objects (link in hf Entity and Objects Schema list on top). These objects depend on if evaluating over B2B or B2C schema. Example of fields for object "user". These are all the possible fields to be filled, but any of them can take the value *null*.

```
{
"fields": {
    "Alias": "Alias, usually a shortened version of the agent's name",
    "Email": "Email address of the agent",
    "EmailEncodingKey": "Email encoding, usually 'UTF-8'",
    "FirstName": "First name of the agent",
    "Id": "ID of the user",
    "LanguageLocaleKey": "Language locale, e.g., 'en_US'",
    "LastName": "Last name of the agent",
    "LocaleSidKey": "Locale, e.g., 'en_US'",
    "Phone": "Phone number of the agent",
    "ProfileId": "ID of the user profile, typically 'Standard User' or a similar profile",
    "TimeZoneSidKey": "Time zone, e.g., 'America/Los_Angeles'",
    "Username": "Unique username for the agent in Salesforce"
},
"object": "User"
},
```

### Relationship and Dependency Diagram

The paper appendix includes a diagram showing relationships among Salesforce objects (link at top).

This diagram is useful for defining the static CRM ontology:

```text
Lead
VoiceCall
VoiceCallTranscript
Quote
QuoteLineItem
Product
Case
Account
Contact
KnowledgeArticle
```

Example relationships:

```text
VoiceCallTranscript → Lead
QuoteLineItem → Quote
QuoteLineItem → Product
Case → Account
Contact → Account
```

### Data-Generation Dependency Diagram

The appendix also includes a data-generation flow or dependency graph (link at top), which can help identify:

* which objects were generated conditionally on other objects;
* which latent variables affected CRM records;
* likely causal or statistical dependencies;
* which attributes may be useful for task reasoning.

This diagram should not automatically be interpreted as runtime Salesforce workflow logic. A generation dependency does not necessarily imply that changing one object during execution automatically modifies another object.

---

### Prompt and Answer Contracts

The paper appendix contains representative prompts and required answer formats, located in the appendix of the paper as well.

For example, lead qualification expects a subset of:

```text
Budget
Authority
Need
Timeline
```

or an appropriate empty value such as:

```text
None
```

---

## Policy and Constraint Sources

Policies may come from several locations:

```text
system prompt
task prompt
task metadata
knowledge articles
CRM records
evaluator rules
```

The task prompt may identify where policy evidence should be found, but may not fully define the policy itself. For example, lead qualification may instruct the agent to inspect:

```text
voice-call transcripts
relevant lead-qualification knowledge articles
```

where the actual definitions of Budget, Authority, Need, and Timeline may need to be extracted from Salesforce knowledge records to uncover hidden policies.

---

## Symbolic Layer Components

The symbolic layer should support the following concepts.

### Entities and Relationships

Formal representation of Salesforce objects, fields, references, and record identities.

### Observed Evidence

Facts returned directly from Salesforce:

```yaml
source_id:
source_type:
field:
value:
observation_id:
```

### Derived Claims

Natural-language interpretations proposed by the agent:

```yaml
claim_type:
status:
source_id:
source_excerpt:
verification_status:
```

Observed evidence and derived claims should remain separate.

### Belief State

The current formal representation of what is known, unknown, conflicting, or unavailable.

Example:

```yaml
Budget:
  status: supported

Authority:
  status: failed

Need:
  status: unknown

Timeline:
  status: conflicting
```

### Typed Actions

Each action should define:

```yaml
name:
parameters:
parameter_types:
preconditions:
execution_template:
possible_observations:
guaranteed_updates:
observation_dependent_updates:
failure_behavior:
```

### Transitions

The layer should represent:

```text
current belief state
+ typed action
+ actual observation
→ next belief state
```

Before the observation arrives, it may represent possible branches:

```text
records returned
empty result
query error
```

### Deterministic Triggers

Some actions may run automatically when:

* the action is safe;
* it is mandatory;
* there is no meaningful strategic choice;
* all required parameters are known.

When multiple valid actions exist, control should return to the agent or controller.

### Constraints and Verifiers

The DSL should support constraints such as:

```text
record IDs must be grounded in retrieved evidence
source excerpts must exist in the cited source
actions must satisfy current-state preconditions
final answers cannot cite unsupported values
repeated failed actions may be blocked
sensitive information requires authorization
```

### Completion and Termination

Each task should define:

```text
when enough evidence exists
when a final answer is enabled
when clarification is required
when evidence sources are exhausted
when the system should abstain or terminate
```

---

## Available Trajectories

Representative trajectories are available from baseline runs or repository examples (linked above).

---

## SOQL and SOSL References

The DSL’s typed retrieval actions will eventually compile into SOQL or SOSL (documentation linked above), to be used to guide and verify syntactically accurate tool calls.

---