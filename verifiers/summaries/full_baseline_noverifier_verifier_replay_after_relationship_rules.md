# CRMArena Syntactic Verifier Replay

- Generated: 2026-07-22T20:57:52
- Analyzed files: 5
- Skipped non-result JSON files: 0
- Analyzed assistant steps: 6756

Correctly identified and missed query failures are inferred from saved Salesforce observations immediately after `execute` actions. The script looks for recorded Salesforce error markers such as `MALFORMED_QUERY`, `INVALID_FIELD`, and `ERROR at Row`; it does not re-run live queries.

## Overall Step Counts

| scope | steps | parser_failures | parsed_execute | parsed_respond | env_query_errors | verifier_rejects | correctly_identified_query_failures | missed_query_failures | unconfirmed_rejects |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| overall | 6756 | 1167 | 4044 | 1545 | 736 | 736 | 695 | 41 | 41 |

## Step Counts By Task

| task_type | steps | parser_failures | parsed_execute | parsed_respond | env_query_errors | verifier_rejects | correctly_identified_query_failures | missed_query_failures | unconfirmed_rejects |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| case_routing | 1616 | 174 | 1111 | 331 | 182 | 184 | 180 | 2 | 4 |
| conversion_rate_comprehension | 2040 | 772 | 951 | 317 | 357 | 352 | 352 | 5 | 0 |
| lead_qualification | 1218 | 91 | 805 | 322 | 107 | 106 | 87 | 20 | 19 |
| private_customer_information | 836 | 62 | 515 | 259 | 46 | 56 | 39 | 7 | 17 |
| quote_approval | 1046 | 68 | 662 | 316 | 44 | 38 | 37 | 7 | 1 |

## Step Counts By Trajectory Outcome

| trajectory_outcome | steps | parser_failures | parsed_execute | parsed_respond | env_query_errors | verifier_rejects | correctly_identified_query_failures | missed_query_failures | unconfirmed_rejects |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| failure | 5810 | 1126 | 3426 | 1258 | 662 | 656 | 626 | 36 | 30 |
| success | 946 | 41 | 618 | 287 | 74 | 80 | 69 | 5 | 11 |

## Trajectory-Level Invalid Action Impact

| trajectory_outcome | trajectories | trajectories_with_parser_failure | trajectories_with_verifier_reject | trajectories_with_env_query_error | trajectories_with_correctly_identified_query_failure | trajectories_with_missed_query_failure | trajectories_ended_invalid_action | trajectories_ended_query_error | reported_model_calls | reported_env_steps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| failure | 397 | 180 | 246 | 241 | 234 | 30 | 44 | 1 | 0 | 0 |
| success | 77 | 25 | 43 | 40 | 40 | 5 | 0 | 0 | 0 | 0 |

## Verifier Error Codes

| error_code | count |
| --- | --- |
| INVALID_SOQL_SYNTAX | 251 |
| INVALID_DATE_LITERAL | 134 |
| NON_FILTERABLE_FIELD | 132 |
| UNKNOWN_FIELD | 71 |
| REPEATED_FAILED_QUERY | 56 |
| UNSUPPORTED_SEMIJOIN | 50 |
| INVALID_SOSL_SEARCH_TERM | 21 |
| UNKNOWN_RELATIONSHIP | 5 |
| UNSEARCHABLE_SOSL_OBJECT | 4 |
| UNKNOWN_OBJECT | 4 |
| INVALID_RELATIONSHIP | 4 |
| UNBALANCED_QUOTES | 2 |
| INVALID_ID_LITERAL | 1 |
| INVALID_QUERY_TYPE | 1 |

## Examples

### parser_failure

- `case_routing` task_id=1480 turn=3 success=False code=EMPTY_ACTION
  - raw: `<thought> I have a list of Opportunity IDs that contain the OptiPower Manager product. Now I need to get the OwnerId for each of these opportunities to determine which agent has handled the most opportunities with this product. </thought...`

### verifier_true_positive

- `case_routing` task_id=1480 turn=8 success=False code=NON_FILTERABLE_FIELD
  - action: `SELECT OwnerId, COUNT(Id) FROM Case WHERE (Subject LIKE '%notification%' OR Description LIKE '%notification%') AND Status = 'Closed' GROUP BY OwnerId ORDER BY COUNT(Id) DESC`
  - observation: `Salesforce instance output: INVALID_FIELD: (Subject LIKE '%notification%' OR Description LIKE '%notification%') ^ ERROR at Row:1:Column:77 field 'Description' can not be filtered in a query call`

### verifier_missed_env_failure

- `case_routing` task_id=1531 turn=11 success=False code=none
  - action: `SELECT OwnerId, COUNT(Id) FROM Case WHERE Subject LIKE '%SecureFlow Suite%' OR Subject LIKE '%SecureFlow%' AND (Subject LIKE '%installation%' OR Subject LIKE '%install%') GROUP BY OwnerId`
  - observation: `Salesforce instance output: MALFORMED_QUERY: OR Subject LIKE '%SecureFlow%' AND (Subject LIKE '%installation%' ^ ERROR at Row:1:Column:107 unexpected token: 'AND'`

### verifier_reject_unconfirmed

- `case_routing` task_id=1521 turn=5 success=False code=UNKNOWN_FIELD
  - action: `SELECT Id, Name FROM OpportunityLineItem WHERE Product2Id = '01tWt000006hUUwIAM'`
  - observation: `Salesforce instance output: [{'Id': '00kWt000002HLRvIAO', 'Name': 'Advanced EDA Solutions for BlueSky Aerospace SimuFlow Xtreme'}, {'Id': '00kWt000002HMpTIAW', 'Name': 'BlueSky Aerospace Partnership SimuFlow Xtreme'}, {'Id': '00kWt000002...`
