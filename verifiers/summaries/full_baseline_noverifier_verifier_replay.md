# CRMArena Syntactic Verifier Replay

- Generated: 2026-07-22T18:51:50
- Analyzed files: 5
- Skipped non-result JSON files: 0
- Analyzed assistant steps: 6756

Correctly identified and missed query failures are inferred from saved Salesforce observations immediately after `execute` actions. The script looks for recorded Salesforce error markers such as `MALFORMED_QUERY`, `INVALID_FIELD`, and `ERROR at Row`; it does not re-run live queries.

## Overall Step Counts

| scope | steps | parser_failures | parsed_execute | parsed_respond | env_query_errors | verifier_rejects | correctly_identified_query_failures | missed_query_failures | unconfirmed_rejects |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| overall | 6756 | 1167 | 4044 | 1545 | 736 | 595 | 304 | 432 | 291 |

## Step Counts By Task

| task_type | steps | parser_failures | parsed_execute | parsed_respond | env_query_errors | verifier_rejects | correctly_identified_query_failures | missed_query_failures | unconfirmed_rejects |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| case_routing | 1616 | 174 | 1111 | 331 | 182 | 82 | 35 | 147 | 47 |
| conversion_rate_comprehension | 2040 | 772 | 951 | 317 | 357 | 203 | 200 | 157 | 3 |
| lead_qualification | 1218 | 91 | 805 | 322 | 107 | 150 | 38 | 69 | 112 |
| private_customer_information | 836 | 62 | 515 | 259 | 46 | 144 | 20 | 26 | 124 |
| quote_approval | 1046 | 68 | 662 | 316 | 44 | 16 | 11 | 33 | 5 |

## Step Counts By Trajectory Outcome

| trajectory_outcome | steps | parser_failures | parsed_execute | parsed_respond | env_query_errors | verifier_rejects | correctly_identified_query_failures | missed_query_failures | unconfirmed_rejects |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| failure | 5810 | 1126 | 3426 | 1258 | 662 | 529 | 289 | 373 | 240 |
| success | 946 | 41 | 618 | 287 | 74 | 66 | 15 | 59 | 51 |

## Trajectory-Level Invalid Action Impact

| trajectory_outcome | trajectories | trajectories_with_parser_failure | trajectories_with_verifier_reject | trajectories_with_env_query_error | trajectories_with_correctly_identified_query_failure | trajectories_with_missed_query_failure | trajectories_ended_invalid_action | trajectories_ended_query_error |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| failure | 397 | 180 | 181 | 241 | 126 | 198 | 44 | 1 |
| success | 77 | 25 | 29 | 40 | 12 | 36 | 0 | 0 |

## Verifier Error Codes

| error_code | count |
| --- | --- |
| UNKNOWN_FIELD | 525 |
| REPEATED_FAILED_QUERY | 56 |
| UNKNOWN_OBJECT | 11 |
| UNBALANCED_QUOTES | 2 |
| INVALID_QUERY_TYPE | 1 |

## Examples

### parser_failure

- `case_routing` task_id=1480 turn=3 success=False code=EMPTY_ACTION
  - raw: `<thought> I have a list of Opportunity IDs that contain the OptiPower Manager product. Now I need to get the OwnerId for each of these opportunities to determine which agent has handled the most opportunities with this product. </thought...`

### verifier_true_positive

- `case_routing` task_id=1484 turn=14 success=False code=REPEATED_FAILED_QUERY
  - action: `SELECT OwnerId, COUNT() FROM Case WHERE OwnerId IN ('005Wt000003NInLIAW', '005Wt000003NEtOIAW') GROUP BY OwnerId`
  - observation: `Salesforce instance output: MALFORMED_QUERY: SELECT OwnerId, COUNT() FROM Case WHERE OwnerId IN ('005Wt000003NInLIAW' ^ ERROR at Row:1:Column:22 unexpected token: 'COUNT()'`

### verifier_missed_env_failure

- `case_routing` task_id=1480 turn=8 success=False code=none
  - action: `SELECT OwnerId, COUNT(Id) FROM Case WHERE (Subject LIKE '%notification%' OR Description LIKE '%notification%') AND Status = 'Closed' GROUP BY OwnerId ORDER BY COUNT(Id) DESC`
  - observation: `Salesforce instance output: INVALID_FIELD: (Subject LIKE '%notification%' OR Description LIKE '%notification%') ^ ERROR at Row:1:Column:77 field 'Description' can not be filtered in a query call`

### verifier_reject_unconfirmed

- `case_routing` task_id=1480 turn=5 success=False code=UNKNOWN_FIELD
  - action: `SELECT Opportunity.OwnerId, COUNT(Id) FROM OpportunityLineItem WHERE Product2Id = '01tWt000006hV9xIAE' GROUP BY Opportunity.OwnerId ORDER BY COUNT(Id) DESC`
  - observation: `Salesforce instance output: [{'OwnerId': '005Wt000003NInKIAW', 'expr0': 9}, {'OwnerId': '005Wt000003NJjNIAW', 'expr0': 8}, {'OwnerId': '005Wt000003NIAdIAO', 'expr0': 8}, {'OwnerId': '005Wt000003NBcBIAW', 'expr0': 7}, {'OwnerId': '005Wt00...`
