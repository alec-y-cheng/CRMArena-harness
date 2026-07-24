# CRMArena Syntactic Verifier Replay

- Generated: 2026-07-23T17:21:22
- Analyzed files: 6
- Skipped non-result JSON files: 0
- Analyzed assistant steps: 2331

Correctly identified and missed query failures are inferred from saved Salesforce observations immediately after `execute` actions. The script looks for recorded Salesforce error markers such as `MALFORMED_QUERY`, `INVALID_FIELD`, and `ERROR at Row`; it does not re-run live queries.

## Overall Step Counts

| scope | steps | parser_failures | parsed_execute | parsed_respond | env_query_errors | verifier_rejects | verifier_unknowns | correctly_identified_query_failures | missed_query_failures | unknown_env_failures | unconfirmed_rejects |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| overall | 2331 | 243 | 1445 | 643 | 190 | 228 | 2 | 180 | 8 | 2 | 48 |

## Step Counts By Task

| task_type | steps | parser_failures | parsed_execute | parsed_respond | env_query_errors | verifier_rejects | verifier_unknowns | correctly_identified_query_failures | missed_query_failures | unknown_env_failures | unconfirmed_rejects |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| case_routing | 540 | 55 | 382 | 103 | 58 | 61 | 1 | 56 | 1 | 1 | 5 |
| confidential_company_knowledge | 313 | 11 | 160 | 142 | 19 | 21 | 0 | 18 | 1 | 0 | 3 |
| internal_operation_data | 476 | 121 | 267 | 88 | 60 | 73 | 1 | 58 | 1 | 1 | 15 |
| lead_qualification | 340 | 15 | 223 | 102 | 26 | 42 | 0 | 22 | 4 | 0 | 20 |
| private_customer_information | 367 | 14 | 225 | 128 | 18 | 22 | 0 | 17 | 1 | 0 | 5 |
| quote_approval | 295 | 27 | 188 | 80 | 9 | 9 | 0 | 9 | 0 | 0 | 0 |

## Step Counts By Trajectory Outcome

| trajectory_outcome | steps | parser_failures | parsed_execute | parsed_respond | env_query_errors | verifier_rejects | verifier_unknowns | correctly_identified_query_failures | missed_query_failures | unknown_env_failures | unconfirmed_rejects |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| failure | 1607 | 196 | 1015 | 396 | 126 | 148 | 2 | 120 | 4 | 2 | 28 |
| success | 724 | 47 | 430 | 247 | 64 | 80 | 0 | 60 | 4 | 0 | 20 |

## Trajectory-Level Invalid Action Impact

| trajectory_outcome | trajectories | trajectories_with_parser_failure | trajectories_with_verifier_reject | trajectories_with_verifier_unknown | trajectories_with_env_query_error | trajectories_with_correctly_identified_query_failure | trajectories_with_missed_query_failure | trajectories_ended_invalid_action | trajectories_ended_query_error | reported_model_calls | reported_env_steps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| failure | 124 | 55 | 61 | 2 | 61 | 59 | 4 | 3 | 0 | 1490 | 1312 |
| success | 56 | 20 | 32 | 0 | 27 | 27 | 3 | 0 | 0 | 724 | 677 |

## Verifier Alignment Overall

| scope | query_steps | environment_invalid | environment_valid | invalid_decisions | unknown_decisions | true_positive | false_positive | false_negative_strict | true_negative | unknown_env_invalid | unknown_env_valid | invalid_precision | strict_recall | review_coverage | false_positive_rate | false_negative_rate_strict | unknown_rate | environment_calls_avoided |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| overall | 1445 | 190 | 1255 | 228 | 2 | 180 | 48 | 10 | 1207 | 2 | 0 | 0.789 | 0.947 | 0.958 | 0.038 | 0.053 | 0.001 | 180 |

## Verifier Alignment By Task

| scope | query_steps | environment_invalid | environment_valid | invalid_decisions | unknown_decisions | true_positive | false_positive | false_negative_strict | true_negative | unknown_env_invalid | unknown_env_valid | invalid_precision | strict_recall | review_coverage | false_positive_rate | false_negative_rate_strict | unknown_rate | environment_calls_avoided |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| case_routing | 382 | 58 | 324 | 61 | 1 | 56 | 5 | 2 | 319 | 1 | 0 | 0.918 | 0.966 | 0.983 | 0.015 | 0.034 | 0.003 | 56 |
| confidential_company_knowledge | 160 | 19 | 141 | 21 | 0 | 18 | 3 | 1 | 138 | 0 | 0 | 0.857 | 0.947 | 0.947 | 0.021 | 0.053 | 0.000 | 18 |
| internal_operation_data | 267 | 60 | 207 | 73 | 1 | 58 | 15 | 2 | 192 | 1 | 0 | 0.795 | 0.967 | 0.983 | 0.072 | 0.033 | 0.004 | 58 |
| lead_qualification | 223 | 26 | 197 | 42 | 0 | 22 | 20 | 4 | 177 | 0 | 0 | 0.524 | 0.846 | 0.846 | 0.102 | 0.154 | 0.000 | 22 |
| private_customer_information | 225 | 18 | 207 | 22 | 0 | 17 | 5 | 1 | 202 | 0 | 0 | 0.773 | 0.944 | 0.944 | 0.024 | 0.056 | 0.000 | 17 |
| quote_approval | 188 | 9 | 179 | 9 | 0 | 9 | 0 | 0 | 179 | 0 | 0 | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 | 0.000 | 9 |

## Verifier Error Codes

| error_code | count |
| --- | --- |
| INVALID_SOQL_GRAMMAR | 61 |
| NON_FILTERABLE_FIELD | 60 |
| UNKNOWN_FIELD | 58 |
| INVALID_DATE_LITERAL | 23 |
| INVALID_SOSL_SEARCH_TERM | 10 |
| UNSUPPORTED_SEMIJOIN | 5 |
| REPEATED_FAILED_QUERY | 4 |
| UNKNOWN_RELATIONSHIP | 2 |
| INVALID_SOQL_SYNTAX | 2 |
| INVALID_ID_LITERAL | 1 |
| INVALID_RELATIONSHIP | 1 |
| UNSEARCHABLE_SOSL_OBJECT | 1 |
| UNKNOWN_OBJECT | 1 |
| UNSUPPORTED_SOSL_FIELD_GROUP | 1 |

## Examples

### parser_failure

- `case_routing` task_id=1480 turn=11 success=True code=EMPTY_ACTION
- `case_routing` task_id=1482 turn=3 success=False code=EMPTY_ACTION

### verifier_true_positive

- `case_routing` task_id=1480 turn=2 success=True code=NON_FILTERABLE_FIELD
  - action: `SELECT Id, Subject, Description, Status, OwnerId FROM Case WHERE Subject LIKE '%OptiPower%' OR Description LIKE '%OptiPower%' OR Subject LIKE '%notification%' OR Description LIKE '%notification%'`
  - observation: `Salesforce instance output: INVALID_FIELD: Subject LIKE '%OptiPower%' OR Description LIKE '%OptiPower%' OR ^ ERROR at Row:1:Column:96 field 'Description' can not be filtered in a query call`
- `case_routing` task_id=1480 turn=7 success=True code=INVALID_SOQL_GRAMMAR
  - action: `SELECT OwnerId, COUNT() FROM Case WHERE Subject LIKE '%notification%' OR Description LIKE '%notification%' GROUP BY OwnerId`
  - observation: `Salesforce instance output: MALFORMED_QUERY: SELECT OwnerId, COUNT() FROM Case WHERE Subject LIKE ^ ERROR at Row:1:Column:22 unexpected token: 'COUNT()'`

### verifier_unknown_env_failure

- `case_routing` task_id=1487 turn=5 success=False code=UNKNOWN_RELATIONSHIP
  - action: `SELECT OpportunityId, (SELECT OwnerId FROM Opportunity) FROM OpportunityLineItem WHERE Product2Id = '01tWt000006hTUkIAM'`
  - observation: `Salesforce instance output: INVALID_TYPE: OpportunityId, (SELECT OwnerId FROM Opportunity) FROM OpportunityLineItem ^ ERROR at Row:1:Column:44 Didn't understand relationship 'Opportunity' in FROM part of query call. If you are attempting...`
- `internal_operation_data` task_id=1887 turn=1 success=False code=UNKNOWN_RELATIONSHIP
  - action: `SELECT OwnerId, CreatedDate, ClosedDate, (SELECT Id, FirstName, LastName FROM Owner) FROM Case WHERE ClosedDate != NULL AND CreatedDate != NULL`
  - observation: `Salesforce instance output: INVALID_TYPE: (SELECT Id, FirstName, LastName FROM Owner) FROM Case WHERE ClosedDate ^ ERROR at Row:1:Column:79 Didn't understand relationship 'Owner' in FROM part of query call. If you are attempting to use a...`

### verifier_missed_env_failure

- `case_routing` task_id=1491 turn=4 success=False code=none
  - action: `SELECT Id, Subject, Description, OwnerId, OwnerId FROM Case WHERE Id IN ('500Wt00000DDzMLIA1', '500Wt00000DDzr2IAD', '500Wt00000DE0ThIAL')`
  - observation: `Salesforce instance output: INVALID_FIELD: Subject, Description, OwnerId, OwnerId FROM Case WHERE Id IN ('500Wt00000DDzMLIA1' ^ ERROR at Row:1:Column:43 duplicate field selected: OwnerId`
- `confidential_company_knowledge` task_id=523 turn=8 success=False code=none
  - action: `SELECT Id, ProductId, Product2.Name, Product2.IsActive FROM ProductCategoryProduct WHERE ProductCategoryId = '0ZGWt0000005XcrOAE'`
  - observation: `Salesforce instance output: INVALID_FIELD: SELECT Id, ProductId, Product2.Name, Product2.IsActive ^ ERROR at Row:1:Column:23 Didn't understand relationship 'Product2' in field path. If you are attempting to use a custom relationship, be ...`

### verifier_reject_unconfirmed

- `case_routing` task_id=1491 turn=10 success=False code=UNKNOWN_FIELD
  - action: `SELECT Id, Title, Summary, CreatedById FROM Knowledge__kav WHERE Title LIKE '%PCB EcoModel%' OR Summary LIKE '%PCB EcoModel%'`
  - observation: `Salesforce instance output: [{'Id': 'ka0Wt000000EpXMIA0', 'Title': 'Advanced Workflow Automation with PCB EcoModel', 'Summary': 'Streamline your PCB design workflow with advanced automation techniques.', 'CreatedById': '005Wt000003MNyjIA...`
- `case_routing` task_id=1491 turn=16 success=False code=UNKNOWN_FIELD
  - action: `SELECT Id, Title, Summary, CreatedById FROM Knowledge__kav WHERE CreatedById = '005Wt000003MNyjIAG'`
  - observation: `Salesforce instance output: [{'Id': 'ka0Wt000000EpXNIA0', 'Title': 'Competitor: Quantum Circuits Inc', 'Summary': "Quantum Circuits Inc prides itself on its solid vendor stability and strong partnership model, ensuring enduring relations...`
