# Routing Analysis

- org_type: `b2b`
- interactive: `False`
- agent_eval_mode: `default`
- task_category: `default_focus`
- routing_min_confidence: `0.55`
- tasks: `540`
- correct: `540`
- accuracy: `1.0000`

## By Task

| task | total | correct | accuracy | general_fallback |
| --- | --- | --- | --- | --- |
| case_routing | 100 | 100 | 1.0000 | 0 |
| confidential_company_knowledge | 80 | 80 | 1.0000 | 0 |
| internal_operation_data | 80 | 80 | 1.0000 | 0 |
| lead_qualification | 100 | 100 | 1.0000 | 0 |
| private_customer_information | 80 | 80 | 1.0000 | 0 |
| quote_approval | 100 | 100 | 1.0000 | 0 |

## Confusion Counts

| task | predicted_family | count |
| --- | --- | --- |
| case_routing | case_routing | 100 |
| confidential_company_knowledge | confidentiality | 80 |
| internal_operation_data | confidentiality | 80 |
| lead_qualification | lead_qualification | 100 |
| private_customer_information | confidentiality | 80 |
| quote_approval | quote_approval | 100 |

## Example Misses

No rows.
