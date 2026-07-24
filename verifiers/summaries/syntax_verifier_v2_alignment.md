# CRMArena Syntactic Verifier Replay

- Generated: 2026-07-23T19:30:06
- Analyzed files: 5
- Skipped non-result JSON files: 0
- Analyzed assistant steps: 1613

Correctly identified and missed query failures are inferred from saved Salesforce observations immediately after `execute` actions. The script looks for recorded Salesforce error markers such as `MALFORMED_QUERY`, `INVALID_FIELD`, and `ERROR at Row`; it does not re-run live queries.

## Overall Step Counts

| scope | steps | parser_failures | parsed_execute | parsed_respond | env_query_errors | verifier_rejects | verifier_unknowns | correctly_identified_query_failures | missed_query_failures | unknown_env_failures | unconfirmed_rejects |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| overall | 1613 | 253 | 910 | 450 | 18 | 0 | 5 | 0 | 13 | 5 | 0 |

## Step Counts By Task

| task_type | steps | parser_failures | parsed_execute | parsed_respond | env_query_errors | verifier_rejects | verifier_unknowns | correctly_identified_query_failures | missed_query_failures | unknown_env_failures | unconfirmed_rejects |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| case_routing | 403 | 53 | 251 | 99 | 2 | 0 | 0 | 0 | 2 | 0 | 0 |
| internal_operation_data | 349 | 104 | 185 | 60 | 9 | 0 | 5 | 0 | 4 | 5 | 0 |
| lead_qualification | 257 | 9 | 151 | 97 | 4 | 0 | 0 | 0 | 4 | 0 | 0 |
| private_customer_information | 314 | 64 | 153 | 97 | 1 | 0 | 0 | 0 | 1 | 0 | 0 |
| quote_approval | 290 | 23 | 170 | 97 | 2 | 0 | 0 | 0 | 2 | 0 | 0 |

## Step Counts By Trajectory Outcome

| trajectory_outcome | steps | parser_failures | parsed_execute | parsed_respond | env_query_errors | verifier_rejects | verifier_unknowns | correctly_identified_query_failures | missed_query_failures | unknown_env_failures | unconfirmed_rejects |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| failure | 1237 | 240 | 670 | 327 | 9 | 0 | 2 | 0 | 7 | 2 | 0 |
| success | 376 | 13 | 240 | 123 | 9 | 0 | 3 | 0 | 6 | 3 | 0 |

## Trajectory-Level Invalid Action Impact

| trajectory_outcome | trajectories | trajectories_with_parser_failure | trajectories_with_verifier_reject | trajectories_with_verifier_unknown | trajectories_with_env_query_error | trajectories_with_correctly_identified_query_failure | trajectories_with_missed_query_failure | trajectories_ended_invalid_action | trajectories_ended_query_error | reported_model_calls | reported_env_steps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| failure | 110 | 42 | 0 | 2 | 7 | 0 | 5 | 9 | 0 | 1297 | 951 |
| success | 32 | 10 | 0 | 1 | 6 | 0 | 5 | 0 | 0 | 428 | 363 |

## Verifier Alignment Overall

| scope | query_steps | environment_invalid | environment_valid | invalid_decisions | unknown_decisions | true_positive | false_positive | false_negative_strict | true_negative | unknown_env_invalid | unknown_env_valid | invalid_precision | strict_recall | review_coverage | false_positive_rate | false_negative_rate_strict | unknown_rate | environment_calls_avoided |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| overall | 910 | 18 | 892 | 0 | 5 | 0 | 0 | 18 | 892 | 5 | 0 |  | 0.000 | 0.278 | 0.000 | 1.000 | 0.005 | 0 |

## Verifier Alignment By Task

| scope | query_steps | environment_invalid | environment_valid | invalid_decisions | unknown_decisions | true_positive | false_positive | false_negative_strict | true_negative | unknown_env_invalid | unknown_env_valid | invalid_precision | strict_recall | review_coverage | false_positive_rate | false_negative_rate_strict | unknown_rate | environment_calls_avoided |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| case_routing | 251 | 2 | 249 | 0 | 0 | 0 | 0 | 2 | 249 | 0 | 0 |  | 0.000 | 0.000 | 0.000 | 1.000 | 0.000 | 0 |
| internal_operation_data | 185 | 9 | 176 | 0 | 5 | 0 | 0 | 9 | 176 | 5 | 0 |  | 0.000 | 0.556 | 0.000 | 1.000 | 0.027 | 0 |
| lead_qualification | 151 | 4 | 147 | 0 | 0 | 0 | 0 | 4 | 147 | 0 | 0 |  | 0.000 | 0.000 | 0.000 | 1.000 | 0.000 | 0 |
| private_customer_information | 153 | 1 | 152 | 0 | 0 | 0 | 0 | 1 | 152 | 0 | 0 |  | 0.000 | 0.000 | 0.000 | 1.000 | 0.000 | 0 |
| quote_approval | 170 | 2 | 168 | 0 | 0 | 0 | 0 | 2 | 168 | 0 | 0 |  | 0.000 | 0.000 | 0.000 | 1.000 | 0.000 | 0 |

## Verifier Error Codes

| error_code | count |
| --- | --- |
| UNKNOWN_RELATIONSHIP | 5 |

## Examples

### parser_failure

- `case_routing` task_id=1483 turn=3 success=False code=EMPTY_ACTION
  - raw: `<thought> I found several cases related to AI Feature Malfunction. Now I need to get the user details for the owners of these cases to understand which agents have handled similar issues. Let me query the User object to get their names a...`
- `case_routing` task_id=1484 turn=5 success=False code=EMPTY_ACTION
- `case_routing` task_id=1484 turn=7 success=False code=EMPTY_ACTION
  - raw: `<thought> I found many OpportunityLineItems associated with CloudLink Designer. Now I need to get the Opportunity records to find the OwnerId (agent) for each opportunity. Let me query the Opportunity object to get the OwnerId for all th...`

### verifier_unknown_env_failure

- `internal_operation_data` task_id=1862 turn=2 success=False code=UNKNOWN_RELATIONSHIP
  - action: `SELECT Case__r.OwnerId, COUNT(Id) FROM CaseHistory__c WHERE Field__c = 'Owner Assignment' GROUP BY Case__r.OwnerId`
  - observation: `Salesforce instance output: INVALID_FIELD: SELECT Case__r.OwnerId, COUNT(Id) FROM ^ ERROR at Row:1:Column:8 Didn't understand relationship 'Case__r' in field path. If you are attempting to use a custom relationship, be sure to append the...`
- `internal_operation_data` task_id=1863 turn=2 success=True code=UNKNOWN_RELATIONSHIP
  - action: `SELECT Opportunity.Name, Opportunity.StageName, (SELECT Id FROM Cases) FROM Opportunity`
  - observation: `Salesforce instance output: INVALID_TYPE: Opportunity.StageName, (SELECT Id FROM Cases) FROM Opportunity ^ ERROR at Row:1:Column:65 Didn't understand relationship 'Cases' in FROM part of query call. If you are attempting to use a custom ...`
- `internal_operation_data` task_id=1863 turn=4 success=True code=UNKNOWN_RELATIONSHIP
  - action: `SELECT StageName, (SELECT Id FROM Cases) FROM Opportunity`
  - observation: `Salesforce instance output: INVALID_TYPE: SELECT StageName, (SELECT Id FROM Cases) FROM Opportunity ^ ERROR at Row:1:Column:35 Didn't understand relationship 'Cases' in FROM part of query call. If you are attempting to use a custom relat...`

### verifier_missed_env_failure

- `case_routing` task_id=1501 turn=12 success=False code=none
  - action: `FIND {PCB EcoModel} IN ALL FIELDS RETURNING OpportunityLineItem(Id, OpportunityId, Product2Id)`
  - observation: `Salesforce instance output: MALFORMED_SEARCH: entity type OpportunityLineItem does not support search`
- `case_routing` task_id=1501 turn=14 success=False code=none
  - action: `FIND {PCB EcoModel} IN ALL FIELDS RETURNING OrderItem(Id, OrderId, Product2Id)`
  - observation: `Salesforce instance output: MALFORMED_SEARCH: entity type OrderItem does not support search`
- `internal_operation_data` task_id=1860 turn=10 success=True code=none
  - action: `SELECT Id, Subject, Description, ActivityDate, WhoId, WhatId FROM Task WHERE (Description LIKE '%security%' OR Subject LIKE '%security%') AND ActivityDate >= 2023-10-01T00:00:00Z AND ActivityDate <= 2023-12-31T23:59:59Z ORDER BY Activity...`
  - observation: `Salesforce instance output: INVALID_FIELD: WhoId, WhatId FROM Task WHERE (Description LIKE '%security%' OR ^ ERROR at Row:1:Column:79 field 'Description' can not be filtered in a query call`
