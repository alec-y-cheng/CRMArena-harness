# CRMArena Syntactic Verifier Replay

- Generated: 2026-07-23T17:14:59
- Analyzed files: 36
- Skipped non-result JSON files: 0
- Analyzed assistant steps: 26782

Correctly identified and missed query failures are inferred from saved Salesforce observations immediately after `execute` actions. The script looks for recorded Salesforce error markers such as `MALFORMED_QUERY`, `INVALID_FIELD`, and `ERROR at Row`; it does not re-run live queries.

## Overall Step Counts

| scope | steps | parser_failures | parsed_execute | parsed_respond | env_query_errors | verifier_rejects | verifier_unknowns | correctly_identified_query_failures | missed_query_failures | unknown_env_failures | unconfirmed_rejects |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| overall | 26782 | 3299 | 17212 | 6271 | 3291 | 3129 | 32 | 3050 | 216 | 25 | 79 |

## Step Counts By Task

| task_type | steps | parser_failures | parsed_execute | parsed_respond | env_query_errors | verifier_rejects | verifier_unknowns | correctly_identified_query_failures | missed_query_failures | unknown_env_failures | unconfirmed_rejects |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| best_region_identification | 388 | 8 | 376 | 4 | 192 | 192 | 0 | 192 | 0 | 0 | 0 |
| case_routing | 4919 | 498 | 3451 | 970 | 538 | 535 | 5 | 528 | 9 | 1 | 7 |
| confidential_company_knowledge | 1303 | 56 | 735 | 512 | 71 | 71 | 2 | 65 | 4 | 2 | 6 |
| conversion_rate_comprehension | 2432 | 955 | 1096 | 381 | 407 | 403 | 0 | 403 | 4 | 0 | 0 |
| handle_time | 366 | 4 | 358 | 4 | 182 | 182 | 0 | 182 | 0 | 0 | 0 |
| internal_operation_data | 2143 | 618 | 1163 | 362 | 208 | 189 | 10 | 186 | 12 | 10 | 3 |
| knowledge_qa | 885 | 5 | 612 | 268 | 174 | 156 | 0 | 156 | 18 | 0 | 0 |
| lead_qualification | 4017 | 263 | 2601 | 1153 | 325 | 294 | 0 | 273 | 52 | 0 | 21 |
| monthly_trend_analysis | 379 | 29 | 336 | 14 | 188 | 164 | 0 | 164 | 24 | 0 | 0 |
| named_entity_disambiguation | 286 | 4 | 282 | 0 | 86 | 92 | 0 | 86 | 0 | 0 | 6 |
| policy_violation_identification | 341 | 6 | 325 | 10 | 21 | 13 | 0 | 13 | 8 | 0 | 0 |
| private_customer_information | 4447 | 444 | 2693 | 1310 | 249 | 244 | 6 | 212 | 33 | 4 | 32 |
| quote_approval | 4152 | 398 | 2474 | 1280 | 157 | 139 | 7 | 135 | 16 | 6 | 4 |
| top_issue_identification | 375 | 10 | 363 | 2 | 297 | 259 | 2 | 259 | 36 | 2 | 0 |
| transfer_count | 349 | 1 | 347 | 1 | 196 | 196 | 0 | 196 | 0 | 0 | 0 |

## Step Counts By Trajectory Outcome

| trajectory_outcome | steps | parser_failures | parsed_execute | parsed_respond | env_query_errors | verifier_rejects | verifier_unknowns | correctly_identified_query_failures | missed_query_failures | unknown_env_failures | unconfirmed_rejects |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| failure | 21595 | 2969 | 13959 | 4667 | 2936 | 2796 | 22 | 2746 | 173 | 17 | 50 |
| success | 5187 | 330 | 3253 | 1604 | 355 | 333 | 10 | 304 | 43 | 8 | 29 |

## Trajectory-Level Invalid Action Impact

| trajectory_outcome | trajectories | trajectories_with_parser_failure | trajectories_with_verifier_reject | trajectories_with_verifier_unknown | trajectories_with_env_query_error | trajectories_with_correctly_identified_query_failure | trajectories_with_missed_query_failure | trajectories_ended_invalid_action | trajectories_ended_query_error | reported_model_calls | reported_env_steps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| failure | 2696 | 647 | 1451 | 15 | 1497 | 1438 | 148 | 132 | 286 | 9976 | 8228 |
| success | 391 | 145 | 175 | 4 | 178 | 167 | 32 | 0 | 0 | 3957 | 3620 |

## Verifier Alignment Overall

| scope | query_steps | environment_invalid | environment_valid | invalid_decisions | unknown_decisions | true_positive | false_positive | false_negative_strict | true_negative | unknown_env_invalid | unknown_env_valid | invalid_precision | strict_recall | review_coverage | false_positive_rate | false_negative_rate_strict | unknown_rate | environment_calls_avoided |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| overall | 17212 | 3291 | 13921 | 3129 | 32 | 3050 | 79 | 241 | 13835 | 25 | 7 | 0.975 | 0.927 | 0.934 | 0.006 | 0.073 | 0.002 | 3050 |

## Verifier Alignment By Task

| scope | query_steps | environment_invalid | environment_valid | invalid_decisions | unknown_decisions | true_positive | false_positive | false_negative_strict | true_negative | unknown_env_invalid | unknown_env_valid | invalid_precision | strict_recall | review_coverage | false_positive_rate | false_negative_rate_strict | unknown_rate | environment_calls_avoided |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| best_region_identification | 376 | 192 | 184 | 192 | 0 | 192 | 0 | 0 | 184 | 0 | 0 | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 | 0.000 | 192 |
| case_routing | 3451 | 538 | 2913 | 535 | 5 | 528 | 7 | 10 | 2902 | 1 | 4 | 0.987 | 0.981 | 0.983 | 0.002 | 0.019 | 0.001 | 528 |
| confidential_company_knowledge | 735 | 71 | 664 | 71 | 2 | 65 | 6 | 6 | 658 | 2 | 0 | 0.915 | 0.915 | 0.944 | 0.009 | 0.085 | 0.003 | 65 |
| conversion_rate_comprehension | 1096 | 407 | 689 | 403 | 0 | 403 | 0 | 4 | 689 | 0 | 0 | 1.000 | 0.990 | 0.990 | 0.000 | 0.010 | 0.000 | 403 |
| handle_time | 358 | 182 | 176 | 182 | 0 | 182 | 0 | 0 | 176 | 0 | 0 | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 | 0.000 | 182 |
| internal_operation_data | 1163 | 208 | 955 | 189 | 10 | 186 | 3 | 22 | 952 | 10 | 0 | 0.984 | 0.894 | 0.942 | 0.003 | 0.106 | 0.009 | 186 |
| knowledge_qa | 612 | 174 | 438 | 156 | 0 | 156 | 0 | 18 | 438 | 0 | 0 | 1.000 | 0.897 | 0.897 | 0.000 | 0.103 | 0.000 | 156 |
| lead_qualification | 2601 | 325 | 2276 | 294 | 0 | 273 | 21 | 52 | 2255 | 0 | 0 | 0.929 | 0.840 | 0.840 | 0.009 | 0.160 | 0.000 | 273 |
| monthly_trend_analysis | 336 | 188 | 148 | 164 | 0 | 164 | 0 | 24 | 148 | 0 | 0 | 1.000 | 0.872 | 0.872 | 0.000 | 0.128 | 0.000 | 164 |
| named_entity_disambiguation | 282 | 86 | 196 | 92 | 0 | 86 | 6 | 0 | 190 | 0 | 0 | 0.935 | 1.000 | 1.000 | 0.031 | 0.000 | 0.000 | 86 |
| policy_violation_identification | 325 | 21 | 304 | 13 | 0 | 13 | 0 | 8 | 304 | 0 | 0 | 1.000 | 0.619 | 0.619 | 0.000 | 0.381 | 0.000 | 13 |
| private_customer_information | 2693 | 249 | 2444 | 244 | 6 | 212 | 32 | 37 | 2410 | 4 | 2 | 0.869 | 0.851 | 0.867 | 0.013 | 0.149 | 0.002 | 212 |
| quote_approval | 2474 | 157 | 2317 | 139 | 7 | 135 | 4 | 22 | 2312 | 6 | 1 | 0.971 | 0.860 | 0.898 | 0.002 | 0.140 | 0.003 | 135 |
| top_issue_identification | 363 | 297 | 66 | 259 | 2 | 259 | 0 | 38 | 66 | 2 | 0 | 1.000 | 0.872 | 0.879 | 0.000 | 0.128 | 0.006 | 259 |
| transfer_count | 347 | 196 | 151 | 196 | 0 | 196 | 0 | 0 | 151 | 0 | 0 | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 | 0.000 | 196 |

## Verifier Error Codes

| error_code | count |
| --- | --- |
| INVALID_SOQL_GRAMMAR | 973 |
| INVALID_DATE_LITERAL | 919 |
| NON_FILTERABLE_FIELD | 601 |
| UNKNOWN_FIELD | 186 |
| REPEATED_FAILED_QUERY | 183 |
| UNSUPPORTED_SEMIJOIN | 102 |
| INVALID_SOSL_SEARCH_TERM | 74 |
| UNKNOWN_OBJECT | 37 |
| UNKNOWN_RELATIONSHIP | 32 |
| INVALID_RELATIONSHIP | 12 |
| UNSEARCHABLE_SOSL_OBJECT | 12 |
| INVALID_SOQL_SYNTAX | 11 |
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

### verifier_true_positive

- `knowledge_qa` task_id=682 turn=1 success=False code=NON_FILTERABLE_FIELD
  - action: `SELECT Title, Summary, FAQ_Answer__c FROM Knowledge__kav WHERE Title LIKE '%AI-VeriSim Pro%' OR FAQ_Answer__c LIKE '%AI-VeriSim Pro%'`
  - observation: `Salesforce instance output: INVALID_FIELD: Title LIKE '%AI-VeriSim Pro%' OR FAQ_Answer__c LIKE '%AI-VeriSim ^ ERROR at Row:1:Column:97 field 'FAQ_Answer__c' can not be filtered in a query call`
- `knowledge_qa` task_id=682 turn=3 success=False code=INVALID_SOSL_SEARCH_TERM
  - action: `FIND {AI-VeriSim Pro} IN ALL FIELDS RETURNING Knowledge__kav(Id, Title, Summary, FAQ_Answer__c)`
  - observation: `Salesforce instance output: MALFORMED_SEARCH: FIND {AI-VeriSim Pro} IN ALL FIELDS RETURNING ^ ERROR at Row:1:Column:8 line 1:8 mismatched character '-' expecting '}'`

### verifier_unknown_env_failure

- `case_routing` task_id=1487 turn=5 success=False code=UNKNOWN_RELATIONSHIP
  - action: `SELECT OpportunityId, (SELECT OwnerId FROM Opportunity) FROM OpportunityLineItem WHERE Product2Id = '01tWt000006hTUkIAM'`
  - observation: `Salesforce instance output: INVALID_TYPE: OpportunityId, (SELECT OwnerId FROM Opportunity) FROM OpportunityLineItem ^ ERROR at Row:1:Column:44 Didn't understand relationship 'Opportunity' in FROM part of query call. If you are attempting...`
- `internal_operation_data` task_id=1887 turn=1 success=False code=UNKNOWN_RELATIONSHIP
  - action: `SELECT OwnerId, CreatedDate, ClosedDate, (SELECT Id, FirstName, LastName FROM Owner) FROM Case WHERE ClosedDate != NULL AND CreatedDate != NULL`
  - observation: `Salesforce instance output: INVALID_TYPE: (SELECT Id, FirstName, LastName FROM Owner) FROM Case WHERE ClosedDate ^ ERROR at Row:1:Column:79 Didn't understand relationship 'Owner' in FROM part of query call. If you are attempting to use a...`

### verifier_missed_env_failure

- `lead_qualification` task_id=10 turn=5 success=False code=none
  - action: `SELECT Id, Subject, Status, Priority, CreatedDate, Description FROM Case WHERE ContactId IN (SELECT Id FROM Contact WHERE LeadId__c = '00QWt00000895FGMAY')`
  - observation: `Salesforce instance output: INVALID_FIELD: (SELECT Id FROM Contact WHERE LeadId__c = '00QWt00000895FGMAY') ^ ERROR at Row:1:Column:123 No such column 'LeadId__c' on entity 'Contact'. If you are attempting to use a custom field, be sure t...`
- `lead_qualification` task_id=17 turn=3 success=False code=none
  - action: `SELECT Id, Subject, TextBody, MessageDate FROM EmailMessage WHERE (ToIds LIKE '%liam.johnson@innospherelabs.com%' OR FromAddress LIKE '%liam.johnson@innospherelabs.com%') ORDER BY MessageDate DESC`
  - observation: `Salesforce instance output: INVALID_FIELD: MessageDate FROM EmailMessage WHERE (ToIds LIKE '%liam.johnson@innospherelabs.com%' ^ ERROR at Row:1:Column:68 No such column 'ToIds' on entity 'EmailMessage'. If you are attempting to use a cus...`

### verifier_reject_unconfirmed

- `internal_operation_data` task_id=1888 turn=31 success=False code=UNKNOWN_FIELD
  - action: `SELECT Id, Subject, Status, CreatedDate, Description FROM Case WHERE ParentId = '0Q0Wt000001WMUhKAO'`
  - observation: `Salesforce instance output: []`
- `private_customer_information` task_id=1594 turn=4 success=True code=UNKNOWN_FIELD
  - action: `SELECT Id, FirstName, LastName, Email, Phone, AccountId, CreatedDate, LastModifiedDate FROM Contact WHERE Id = '003Wt00000JqyA1IAJ'`
  - observation: `Salesforce instance output: [{'Id': '003Wt00000JqyA1IAJ', 'FirstName': 'Zara', 'LastName': 'Mohsin', 'Email': 'zara.mohsin@urbantechdevelopments.com', 'Phone': '170-555-0202', 'AccountId': '001Wt00000PGb5OIAT', 'CreatedDate': '2025-04-20...`
