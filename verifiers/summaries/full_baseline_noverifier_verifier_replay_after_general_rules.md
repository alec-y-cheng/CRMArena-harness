# CRMArena Syntactic Verifier Replay

- Generated: 2026-07-22T20:22:22
- Analyzed files: 5
- Skipped non-result JSON files: 0
- Analyzed assistant steps: 6756

Correctly identified and missed query failures are inferred from saved Salesforce observations immediately after `execute` actions. The script looks for recorded Salesforce error markers such as `MALFORMED_QUERY`, `INVALID_FIELD`, and `ERROR at Row`; it does not re-run live queries.

## Overall Step Counts

| scope | steps | parser_failures | parsed_execute | parsed_respond | env_query_errors | verifier_rejects | correctly_identified_query_failures | missed_query_failures | unconfirmed_rejects |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| overall | 6756 | 1167 | 4044 | 1545 | 736 | 732 | 691 | 45 | 41 |

## Step Counts By Task

| task_type | steps | parser_failures | parsed_execute | parsed_respond | env_query_errors | verifier_rejects | correctly_identified_query_failures | missed_query_failures | unconfirmed_rejects |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| case_routing | 1616 | 174 | 1111 | 331 | 182 | 184 | 180 | 2 | 4 |
| conversion_rate_comprehension | 2040 | 772 | 951 | 317 | 357 | 351 | 351 | 6 | 0 |
| lead_qualification | 1218 | 91 | 805 | 322 | 107 | 102 | 85 | 22 | 17 |
| private_customer_information | 836 | 62 | 515 | 259 | 46 | 56 | 39 | 7 | 17 |
| quote_approval | 1046 | 68 | 662 | 316 | 44 | 39 | 36 | 8 | 3 |

## Step Counts By Trajectory Outcome

| trajectory_outcome | steps | parser_failures | parsed_execute | parsed_respond | env_query_errors | verifier_rejects | correctly_identified_query_failures | missed_query_failures | unconfirmed_rejects |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| failure | 5810 | 1126 | 3426 | 1258 | 662 | 653 | 622 | 40 | 31 |
| success | 946 | 41 | 618 | 287 | 74 | 79 | 69 | 5 | 10 |

## Trajectory-Level Invalid Action Impact

| trajectory_outcome | trajectories | trajectories_with_parser_failure | trajectories_with_verifier_reject | trajectories_with_env_query_error | trajectories_with_correctly_identified_query_failure | trajectories_with_missed_query_failure | trajectories_ended_invalid_action | trajectories_ended_query_error | reported_model_calls | reported_env_steps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| failure | 397 | 180 | 245 | 241 | 232 | 34 | 44 | 1 | 0 | 0 |
| success | 77 | 25 | 42 | 40 | 40 | 5 | 0 | 0 | 0 | 0 |

## Verifier Error Codes

| error_code | count |
| --- | --- |
| INVALID_SOQL_SYNTAX | 251 |
| INVALID_DATE_LITERAL | 134 |
| NON_FILTERABLE_FIELD | 132 |
| UNKNOWN_FIELD | 76 |
| REPEATED_FAILED_QUERY | 56 |
| UNSUPPORTED_SEMIJOIN | 50 |
| INVALID_SOSL_SEARCH_TERM | 21 |
| UNSEARCHABLE_SOSL_OBJECT | 4 |
| UNKNOWN_OBJECT | 4 |
| UNBALANCED_QUOTES | 2 |
| INVALID_ID_LITERAL | 1 |
| INVALID_QUERY_TYPE | 1 |
