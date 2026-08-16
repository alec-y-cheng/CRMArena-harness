# Salesforce MCP Phase 0 Notes

This note makes the Salesforce MCP execution substrate concrete before wiring it
into the generic EWM runtime.

## Scope

The immediate EWM read backend should target Salesforce Hosted MCP
`platform/sobject-reads`, not the local Salesforce DX MCP server.

`platform/sobject-reads` is the correct first target because it is read-only and
directly exposes the capabilities needed for a generic evidence/retrieval
runtime:

- schema discovery;
- SOQL record queries;
- SOSL text search;
- current user context;
- recently viewed records;
- related-record traversal.

The Salesforce DX MCP server is adjacent but different. It is useful for
developer workflows such as org metadata, users, tests, deployments, and code
analysis. It should not be the default EWM data backend unless the task is
developer/admin-oriented.

## Endpoints

Hosted SObject Reads endpoint:

```text
Production:
https://api.salesforce.com/platform/mcp/v1/platform/sobject-reads

Sandbox or scratch:
https://api.salesforce.com/platform/mcp/v1/sandbox/platform/sobject-reads
```

The endpoint choice should become environment configuration, not prompt text.

## Authentication

Salesforce Hosted MCP uses OAuth through an External Client App.

Required setup:

- enable the hosted MCP server in Salesforce Setup / API Catalog;
- create an External Client App for the MCP client;
- include OAuth scopes:
  - `mcp_api`;
  - `refresh_token`;
- use OAuth authorization code with PKCE;
- issue JWT-based access tokens for named users.

For EWM, this means MCP calls should run as the authenticated user. The runtime
should treat Salesforce permissions, sharing rules, and field-level security as
part of the environment constraints surfaced by MCP, not as something the LLM
can override.

## Hosted SObject Reads Capabilities

The official SObject Reads reference documents these read-only capabilities.
Exact tool names must still be confirmed from the live `tools/list` response,
because MCP clients consume server-advertised tool names and JSON schemas.

| EWM call object | Salesforce capability | Expected arguments |
| --- | --- | --- |
| `DiscoverSchemaIndex` | schema index for queryable business objects | none |
| `DiscoverObjectSchema` | field-level schema for one object | `object-name` |
| `RunSoqlQuery` | SOQL read query | `query` |
| `RunSoslSearch` | SOSL text search | `search` |
| `GetUserContext` | authenticated user identity/context | none |
| `GetRecentRecords` | recently viewed/modified records | `sobject-name` |
| `GetRelatedRecords` | child records from parent relationship | `sobject-name`, `id`, `relationship-path` |

The EWM runtime should not hardcode these names until the live tool list is
captured. Instead, map live MCP tool names into stable internal EWM call
objects.

## LLM Tool-Call Shape

The LLM should not write raw HTTP or JSON-RPC. It should select an internal EWM
action from the reachable action menu and provide typed arguments.

Conceptually:

```json
{
  "action": "RunSoqlQuery",
  "arguments": {
    "query": "SELECT Id, Name FROM Account WHERE Name = 'Acme' LIMIT 10"
  }
}
```

The EWM MCP adapter maps that action to the live MCP tool name:

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "<live soql tool name from tools/list>",
    "arguments": {
      "query": "SELECT Id, Name FROM Account WHERE Name = 'Acme' LIMIT 10"
    }
  }
}
```

The adapter, not the LLM, should own:

- MCP protocol details;
- server URL;
- auth headers;
- live tool-name mapping;
- JSON-RPC IDs;
- response normalization;
- retries for transport errors.

## Result Handling

Every MCP result should enter `ExecutionState` in two stages:

1. Store the raw result as `collected.observations`.
2. Normalize useful pieces into `collected.evidence` only when they matter for
   support, verification, disclosure, audit, or response rendering.

Examples:

- schema index response -> observation plus `EnvironmentIR` update;
- object schema response -> observation plus field/relationship metadata;
- SOQL response -> observation plus one evidence item per relevant record/field
  span;
- SOSL response -> observation plus grouped search-hit evidence;
- user context response -> observation plus actor/context facts in the frame or
  resolved state;
- related records response -> observation plus relationship evidence.

## Schema Discovery vs Query/Search

Schema discovery is for affordance construction. It answers:

- which objects exist;
- which fields exist;
- which fields are filterable/queryable/searchable;
- what picklist values are valid;
- what relationships connect objects.

SOQL/SOSL calls are for evidence acquisition. They answer:

- what records or text actually exist for this request;
- which retrieved values support or contradict the candidate outcome;
- whether more targeted lookup is needed.

The EWM driver should build `EnvironmentIR` from schema calls before trusting LLM
proposed record queries.

## Error Classes to Capture

The phase 0 probe should collect examples of the following errors from a test
org:

- invalid object name;
- invalid field name;
- invalid relationship path;
- malformed SOQL;
- malformed SOSL;
- missing `WHERE` or `LIMIT` when the server enforces query hygiene;
- permission / field-level security failure;
- unauthenticated or expired token;
- empty result set;
- too-broad query or timeout.

The runtime should preserve raw MCP errors as observations and normalize them
into action failures under `ExecutionState.actions.failed`.

## Phase 0 Probe

Use:

```bash
cd /work/hdd/bgtb/acheng11/CRMArena
SF_MCP_URL="https://api.salesforce.com/platform/mcp/v1/platform/sobject-reads" \
SF_MCP_BEARER_TOKEN="<token>" \
python scripts/probe_salesforce_mcp_reads.py --out /tmp/sf_mcp_probe.json
```

For sandbox/scratch orgs, use:

```bash
SF_MCP_URL="https://api.salesforce.com/platform/mcp/v1/sandbox/platform/sobject-reads"
```

Optional read-only calls:

```bash
python scripts/probe_salesforce_mcp_reads.py \
  --object Account \
  --query "SELECT Id, Name FROM Account WHERE Name != null LIMIT 5" \
  --search "FIND {Acme} IN NAME FIELDS RETURNING Account(Id, Name) LIMIT 5"
```

The probe intentionally does not mutate data. Its main purpose is to record
`tools/list` output and sample result/error envelopes so the EWM adapter can be
implemented against real schemas instead of guessed tool names.

## Phase 0.5 Local SObject Reads Shim

While Hosted MCP access is pending, the repo includes a local MCP-compatible
read shim backed by the CRMArena Salesforce API credentials:

```text
ewm/mcp/salesforce_read_adapter.py
scripts/run_local_salesforce_mcp_reads.py
```

It exposes the same generic read-side tool names as the documented Hosted
SObject Reads server:

```text
getObjectSchema
soqlQuery
find
getUserInfo
listRecentSobjectRecords
getRelatedRecords
```

Run a non-mutating B2B demo:

```bash
cd /work/hdd/bgtb/acheng11/CRMArena
source .venv-crm-modern/bin/activate
set -a
source .env
set +a

python scripts/run_local_salesforce_mcp_reads.py --org-type b2b --demo --demo-object Account
```

Run as a stdio JSON-RPC MCP-like server:

```bash
python scripts/run_local_salesforce_mcp_reads.py --org-type b2b
```

Example line-delimited JSON-RPC request:

```json
{"jsonrpc":"2.0","id":1,"method":"tools/list"}
```

Example tool call:

```json
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"soqlQuery","arguments":{"query":"SELECT Id, Name FROM Account WHERE Name != null LIMIT 5"}}}
```

The local shim is not byte-for-byte Hosted MCP emulation. It is an
MCP-compatible adapter with the same core read capability surface. The EWM
runtime should depend on this generic interface so the backend can later switch
from the local Simple Salesforce implementation to Salesforce Hosted MCP.

## Open Questions for Live Probe

- What exact tool names does `tools/list` return for the hosted
  `platform/sobject-reads` server?
- Does Salesforce require the MCP `initialize` handshake before `tools/list`
  for this endpoint?
- What protocol version does the endpoint advertise?
- Are tool input schemas exactly the argument names shown in the docs, including
  hyphenated names such as `object-name` and `sobject-name`?
- What is the exact JSON shape of successful SOQL/SOSL results?
- What is the exact JSON shape of Salesforce permission and validation errors?
- Does `get current user context` include enough actor metadata for the first
  disclosure verifier, or do we need an additional user/profile lookup?

## Sources

- Salesforce SObject Reads reference:
  https://developer.salesforce.com/docs/platform/hosted-mcp-servers/references/reference/sobject-reads.html
- Salesforce Hosted MCP standard servers reference:
  https://developer.salesforce.com/docs/platform/hosted-mcp-servers/guide/servers-reference.html
- Salesforce Hosted MCP setup overview:
  https://developer.salesforce.com/docs/platform/hosted-mcp-servers/guide/setup-overview.html
- Salesforce External Client App setup:
  https://developer.salesforce.com/docs/platform/hosted-mcp-servers/guide/create-external-client-app.html
- Salesforce DX MCP server:
  https://github.com/salesforcecli/mcp
