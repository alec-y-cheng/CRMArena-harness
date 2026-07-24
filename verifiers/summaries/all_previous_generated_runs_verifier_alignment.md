# CRMArena Syntactic Verifier Replay

- Generated: 2026-07-23T16:30:22
- Analyzed files: 35
- Skipped non-result JSON files: 0
- Analyzed assistant steps: 25806

Correctly identified and missed query failures are inferred from saved Salesforce observations immediately after `execute` actions. The script looks for recorded Salesforce error markers such as `MALFORMED_QUERY`, `INVALID_FIELD`, and `ERROR at Row`; it does not re-run live queries.

## Overall Step Counts

| scope | steps | parser_failures | parsed_execute | parsed_respond | env_query_errors | verifier_rejects | verifier_unknowns | correctly_identified_query_failures | missed_query_failures | unknown_env_failures | unconfirmed_rejects |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| overall | 25806 | 3217 | 16602 | 5987 | 3214 | 3216 | 32 | 2991 | 198 | 25 | 225 |

## Step Counts By Task

| task_type | steps | parser_failures | parsed_execute | parsed_respond | env_query_errors | verifier_rejects | verifier_unknowns | correctly_identified_query_failures | missed_query_failures | unknown_env_failures | unconfirmed_rejects |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| best_region_identification | 388 | 8 | 376 | 4 | 192 | 192 | 0 | 192 | 0 | 0 | 0 |
| case_routing | 4919 | 498 | 3451 | 970 | 538 | 546 | 5 | 528 | 9 | 1 | 18 |
| confidential_company_knowledge | 1303 | 56 | 735 | 512 | 71 | 78 | 2 | 66 | 3 | 2 | 12 |
| conversion_rate_comprehension | 2432 | 955 | 1096 | 381 | 407 | 403 | 0 | 403 | 4 | 0 | 0 |
| handle_time | 366 | 4 | 358 | 4 | 182 | 182 | 0 | 182 | 0 | 0 | 0 |
| internal_operation_data | 2143 | 618 | 1163 | 362 | 208 | 214 | 10 | 186 | 12 | 10 | 28 |
| knowledge_qa | 885 | 5 | 612 | 268 | 174 | 156 | 0 | 156 | 18 | 0 | 0 |
| lead_qualification | 3378 | 229 | 2169 | 980 | 260 | 277 | 0 | 225 | 35 | 0 | 52 |
| monthly_trend_analysis | 379 | 29 | 336 | 14 | 188 | 165 | 0 | 164 | 24 | 0 | 1 |
| named_entity_disambiguation | 286 | 4 | 282 | 0 | 86 | 92 | 0 | 86 | 0 | 0 | 6 |
| policy_violation_identification | 341 | 6 | 325 | 10 | 21 | 13 | 0 | 13 | 8 | 0 | 0 |
| private_customer_information | 4447 | 444 | 2693 | 1310 | 249 | 304 | 6 | 212 | 33 | 4 | 92 |
| quote_approval | 3815 | 350 | 2296 | 1169 | 145 | 127 | 7 | 123 | 16 | 6 | 4 |
| top_issue_identification | 375 | 10 | 363 | 2 | 297 | 259 | 2 | 259 | 36 | 2 | 0 |
| transfer_count | 349 | 1 | 347 | 1 | 196 | 208 | 0 | 196 | 0 | 0 | 12 |

## Step Counts By Trajectory Outcome

| trajectory_outcome | steps | parser_failures | parsed_execute | parsed_respond | env_query_errors | verifier_rejects | verifier_unknowns | correctly_identified_query_failures | missed_query_failures | unknown_env_failures | unconfirmed_rejects |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| failure | 20798 | 2891 | 13469 | 4438 | 2880 | 2854 | 22 | 2704 | 159 | 17 | 150 |
| success | 5008 | 326 | 3133 | 1549 | 334 | 362 | 10 | 287 | 39 | 8 | 75 |

## Trajectory-Level Invalid Action Impact

| trajectory_outcome | trajectories | trajectories_with_parser_failure | trajectories_with_verifier_reject | trajectories_with_verifier_unknown | trajectories_with_env_query_error | trajectories_with_correctly_identified_query_failure | trajectories_with_missed_query_failure | trajectories_ended_invalid_action | trajectories_ended_query_error | reported_model_calls | reported_env_steps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| failure | 2629 | 616 | 1451 | 15 | 1468 | 1411 | 138 | 131 | 286 | 9182 | 7512 |
| success | 376 | 141 | 181 | 4 | 171 | 162 | 28 | 0 | 0 | 3778 | 3445 |

## Verifier Alignment Overall

| scope | query_steps | environment_invalid | environment_valid | invalid_decisions | unknown_decisions | true_positive | false_positive | false_negative_strict | true_negative | unknown_env_invalid | unknown_env_valid | invalid_precision | strict_recall | review_coverage | false_positive_rate | false_negative_rate_strict | unknown_rate | environment_calls_avoided |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| overall | 16602 | 3214 | 13388 | 3216 | 32 | 2991 | 225 | 223 | 13156 | 25 | 7 | 0.930 | 0.931 | 0.938 | 0.017 | 0.069 | 0.002 | 2991 |

## Verifier Alignment By Task

| scope | query_steps | environment_invalid | environment_valid | invalid_decisions | unknown_decisions | true_positive | false_positive | false_negative_strict | true_negative | unknown_env_invalid | unknown_env_valid | invalid_precision | strict_recall | review_coverage | false_positive_rate | false_negative_rate_strict | unknown_rate | environment_calls_avoided |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| best_region_identification | 376 | 192 | 184 | 192 | 0 | 192 | 0 | 0 | 184 | 0 | 0 | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 | 0.000 | 192 |
| case_routing | 3451 | 538 | 2913 | 546 | 5 | 528 | 18 | 10 | 2891 | 1 | 4 | 0.967 | 0.981 | 0.983 | 0.006 | 0.019 | 0.001 | 528 |
| confidential_company_knowledge | 735 | 71 | 664 | 78 | 2 | 66 | 12 | 5 | 652 | 2 | 0 | 0.846 | 0.930 | 0.958 | 0.018 | 0.070 | 0.003 | 66 |
| conversion_rate_comprehension | 1096 | 407 | 689 | 403 | 0 | 403 | 0 | 4 | 689 | 0 | 0 | 1.000 | 0.990 | 0.990 | 0.000 | 0.010 | 0.000 | 403 |
| handle_time | 358 | 182 | 176 | 182 | 0 | 182 | 0 | 0 | 176 | 0 | 0 | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 | 0.000 | 182 |
| internal_operation_data | 1163 | 208 | 955 | 214 | 10 | 186 | 28 | 22 | 927 | 10 | 0 | 0.869 | 0.894 | 0.942 | 0.029 | 0.106 | 0.009 | 186 |
| knowledge_qa | 612 | 174 | 438 | 156 | 0 | 156 | 0 | 18 | 438 | 0 | 0 | 1.000 | 0.897 | 0.897 | 0.000 | 0.103 | 0.000 | 156 |
| lead_qualification | 2169 | 260 | 1909 | 277 | 0 | 225 | 52 | 35 | 1857 | 0 | 0 | 0.812 | 0.865 | 0.865 | 0.027 | 0.135 | 0.000 | 225 |
| monthly_trend_analysis | 336 | 188 | 148 | 165 | 0 | 164 | 1 | 24 | 147 | 0 | 0 | 0.994 | 0.872 | 0.872 | 0.007 | 0.128 | 0.000 | 164 |
| named_entity_disambiguation | 282 | 86 | 196 | 92 | 0 | 86 | 6 | 0 | 190 | 0 | 0 | 0.935 | 1.000 | 1.000 | 0.031 | 0.000 | 0.000 | 86 |
| policy_violation_identification | 325 | 21 | 304 | 13 | 0 | 13 | 0 | 8 | 304 | 0 | 0 | 1.000 | 0.619 | 0.619 | 0.000 | 0.381 | 0.000 | 13 |
| private_customer_information | 2693 | 249 | 2444 | 304 | 6 | 212 | 92 | 37 | 2350 | 4 | 2 | 0.697 | 0.851 | 0.867 | 0.038 | 0.149 | 0.002 | 212 |
| quote_approval | 2296 | 145 | 2151 | 127 | 7 | 123 | 4 | 22 | 2146 | 6 | 1 | 0.969 | 0.848 | 0.890 | 0.002 | 0.152 | 0.003 | 123 |
| top_issue_identification | 363 | 297 | 66 | 259 | 2 | 259 | 0 | 38 | 66 | 2 | 0 | 1.000 | 0.872 | 0.879 | 0.000 | 0.128 | 0.006 | 259 |
| transfer_count | 347 | 196 | 151 | 208 | 0 | 196 | 12 | 0 | 139 | 0 | 0 | 0.942 | 1.000 | 1.000 | 0.079 | 0.000 | 0.000 | 196 |

## Verifier Error Codes

| error_code | count |
| --- | --- |
| INVALID_SOQL_GRAMMAR | 965 |
| INVALID_DATE_LITERAL | 919 |
| NON_FILTERABLE_FIELD | 577 |
| UNKNOWN_FIELD | 332 |
| REPEATED_FAILED_QUERY | 181 |
| UNSUPPORTED_SEMIJOIN | 92 |
| INVALID_SOSL_SEARCH_TERM | 73 |
| UNKNOWN_RELATIONSHIP | 32 |
| UNKNOWN_OBJECT | 27 |
| INVALID_SOQL_SYNTAX | 11 |
| UNSEARCHABLE_SOSL_OBJECT | 11 |
| INVALID_RELATIONSHIP | 9 |
| UNSUPPORTED_SOSL_FIELD_GROUP | 7 |
| UNBALANCED_QUOTES | 4 |
| UNGROUPED_SELECTED_FIELD | 2 |
| INVALID_ID_LITERAL | 2 |
| INVALID_QUERY_TYPE | 2 |
| UNBALANCED_SEARCH_BRACES | 1 |
| UNBALANCED_PARENTHESES | 1 |

## Examples

### parser_failure

- `knowledge_qa` task_id=680 turn=2 success=False code=EMPTY_ACTION
- `knowledge_qa` task_id=697 turn=8 success=False code=EMPTY_ACTION
- `knowledge_qa` task_id=703 turn=3 success=False code=EMPTY_ACTION

### verifier_true_positive

- `knowledge_qa` task_id=682 turn=1 success=False code=NON_FILTERABLE_FIELD
  - action: `SELECT Title, Summary, FAQ_Answer__c FROM Knowledge__kav WHERE Title LIKE '%AI-VeriSim Pro%' OR FAQ_Answer__c LIKE '%AI-VeriSim Pro%'`
  - observation: `Salesforce instance output: INVALID_FIELD: Title LIKE '%AI-VeriSim Pro%' OR FAQ_Answer__c LIKE '%AI-VeriSim ^ ERROR at Row:1:Column:97 field 'FAQ_Answer__c' can not be filtered in a query call`
- `knowledge_qa` task_id=682 turn=3 success=False code=INVALID_SOSL_SEARCH_TERM
  - action: `FIND {AI-VeriSim Pro} IN ALL FIELDS RETURNING Knowledge__kav(Id, Title, Summary, FAQ_Answer__c)`
  - observation: `Salesforce instance output: MALFORMED_SEARCH: FIND {AI-VeriSim Pro} IN ALL FIELDS RETURNING ^ ERROR at Row:1:Column:8 line 1:8 mismatched character '-' expecting '}'`
- `knowledge_qa` task_id=682 turn=7 success=False code=INVALID_SOSL_SEARCH_TERM
  - action: `FIND {AI-VeriSim} IN ALL FIELDS RETURNING Knowledge__kav(Id, Title, Summary, FAQ_Answer__c)`
  - observation: `Salesforce instance output: MALFORMED_SEARCH: FIND {AI-VeriSim} IN ALL FIELDS RETURNING ^ ERROR at Row:1:Column:8 line 1:8 mismatched character '-' expecting '}'`

### verifier_unknown_env_failure

- `case_routing` task_id=1487 turn=5 success=False code=UNKNOWN_RELATIONSHIP
  - action: `SELECT OpportunityId, (SELECT OwnerId FROM Opportunity) FROM OpportunityLineItem WHERE Product2Id = '01tWt000006hTUkIAM'`
  - observation: `Salesforce instance output: INVALID_TYPE: OpportunityId, (SELECT OwnerId FROM Opportunity) FROM OpportunityLineItem ^ ERROR at Row:1:Column:44 Didn't understand relationship 'Opportunity' in FROM part of query call. If you are attempting...`
- `internal_operation_data` task_id=1887 turn=1 success=False code=UNKNOWN_RELATIONSHIP
  - action: `SELECT OwnerId, CreatedDate, ClosedDate, (SELECT Id, FirstName, LastName FROM Owner) FROM Case WHERE ClosedDate != NULL AND CreatedDate != NULL`
  - observation: `Salesforce instance output: INVALID_TYPE: (SELECT Id, FirstName, LastName FROM Owner) FROM Case WHERE ClosedDate ^ ERROR at Row:1:Column:79 Didn't understand relationship 'Owner' in FROM part of query call. If you are attempting to use a...`
- `internal_operation_data` task_id=1861 turn=4 success=True code=UNKNOWN_RELATIONSHIP
  - action: `SELECT Id, CreatedDate, ClosedDate, AccountId, (SELECT ShippingState FROM Account) FROM Case WHERE ClosedDate >= 2019-12-01T00:00:00Z AND ClosedDate <= 2020-02-29T23:59:59Z AND ClosedDate != null LIMIT 50`
  - observation: `Salesforce instance output: INVALID_TYPE: AccountId, (SELECT ShippingState FROM Account) FROM Case WHERE ClosedDate ^ ERROR at Row:1:Column:75 Didn't understand relationship 'Account' in FROM part of query call. If you are attempting to ...`

### verifier_missed_env_failure

- `lead_qualification` task_id=10 turn=5 success=False code=none
  - action: `SELECT Id, Subject, Status, Priority, CreatedDate, Description FROM Case WHERE ContactId IN (SELECT Id FROM Contact WHERE LeadId__c = '00QWt00000895FGMAY')`
  - observation: `Salesforce instance output: INVALID_FIELD: (SELECT Id FROM Contact WHERE LeadId__c = '00QWt00000895FGMAY') ^ ERROR at Row:1:Column:123 No such column 'LeadId__c' on entity 'Contact'. If you are attempting to use a custom field, be sure t...`
- `lead_qualification` task_id=17 turn=3 success=False code=none
  - action: `SELECT Id, Subject, TextBody, MessageDate FROM EmailMessage WHERE (ToIds LIKE '%liam.johnson@innospherelabs.com%' OR FromAddress LIKE '%liam.johnson@innospherelabs.com%') ORDER BY MessageDate DESC`
  - observation: `Salesforce instance output: INVALID_FIELD: MessageDate FROM EmailMessage WHERE (ToIds LIKE '%liam.johnson@innospherelabs.com%' ^ ERROR at Row:1:Column:68 No such column 'ToIds' on entity 'EmailMessage'. If you are attempting to use a cus...`
- `case_routing` task_id=1491 turn=4 success=False code=none
  - action: `SELECT Id, Subject, Description, OwnerId, OwnerId FROM Case WHERE Id IN ('500Wt00000DDzMLIA1', '500Wt00000DDzr2IAD', '500Wt00000DE0ThIAL')`
  - observation: `Salesforce instance output: INVALID_FIELD: Subject, Description, OwnerId, OwnerId FROM Case WHERE Id IN ('500Wt00000DDzMLIA1' ^ ERROR at Row:1:Column:43 duplicate field selected: OwnerId`

### verifier_reject_unconfirmed

- `case_routing` task_id=1491 turn=10 success=False code=UNKNOWN_FIELD
  - action: `SELECT Id, Title, Summary, CreatedById FROM Knowledge__kav WHERE Title LIKE '%PCB EcoModel%' OR Summary LIKE '%PCB EcoModel%'`
  - observation: `Salesforce instance output: [{'Id': 'ka0Wt000000EpXMIA0', 'Title': 'Advanced Workflow Automation with PCB EcoModel', 'Summary': 'Streamline your PCB design workflow with advanced automation techniques.', 'CreatedById': '005Wt000003MNyjIA...`
- `case_routing` task_id=1491 turn=16 success=False code=UNKNOWN_FIELD
  - action: `SELECT Id, Title, Summary, CreatedById FROM Knowledge__kav WHERE CreatedById = '005Wt000003MNyjIAG'`
  - observation: `Salesforce instance output: [{'Id': 'ka0Wt000000EpXNIA0', 'Title': 'Competitor: Quantum Circuits Inc', 'Summary': "Quantum Circuits Inc prides itself on its solid vendor stability and strong partnership model, ensuring enduring relations...`
- `case_routing` task_id=1491 turn=20 success=False code=UNKNOWN_FIELD
  - action: `SELECT Id, Title, Summary, CreatedById FROM Knowledge__kav WHERE Title LIKE '%PCB EcoModel%' OR Summary LIKE '%PCB EcoModel%'`
  - observation: `Salesforce instance output: [{'Id': 'ka0Wt000000EpXMIA0', 'Title': 'Advanced Workflow Automation with PCB EcoModel', 'Summary': 'Streamline your PCB design workflow with advanced automation techniques.', 'CreatedById': '005Wt000003MNyjIA...`
