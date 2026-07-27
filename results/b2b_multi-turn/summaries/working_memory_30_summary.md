# CRMArena Result Summary

Source: `CRMArena/results/b2b_multi-turn/react_openai_Qwen3.5-35B-A3B_ablation30_q35_859621_llama_859619_working_memory_only_noverifier_wm/results_openai`

## Overall

- Tasks: 180
- Successes: 56
- Success rate: 0.3111
- API errors: 11
- SOQL/SOSL query-error endings: 2
- Invalid-action endings: 9
- Verifier rejection events: 0

## By Task

| task_type | n | successes | success_rate | submitted | max_turns | query_errors | invalid_actions | empty_content | api_errors | avg_reward | avg_em | avg_f1 | nonzero_rewards | avg_model_calls | avg_env_steps | avg_prompt_tokens | avg_completion_tokens | avg_total_tokens | verifier_failure_tasks | verifier_failure_events | top_end_reasons |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| case_routing | 30 | 2 | 0.0667 | 22 | 2 | 0 | 2 | 2 | 4 | 0.0667 |  |  | 2 | 18.3077 | 14.8846 | 350119.4231 | 7833.1538 | 357952.5769 | 0 | 0 | Submit action:22; Error: 'Subject':3; Invalid action:2; Max turns reached:2 |
| confidential_company_knowledge | 30 | 19 | 0.6333 | 28 | 0 | 0 | 0 | 0 | 2 | 0.6333 |  |  | 19 | 10.5714 | 10.2857 | 114240.5714 | 3539.0000 | 117779.5714 | 0 | 0 | Submit action:28; Error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 262144 tokens. However, you requested 950 output tokens and your prompt contains at least 261195 input tokens, for a total of at least 262145 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=261195):1; Error: 'Name':1 |
| internal_operation_data | 30 | 11 | 0.3667 | 19 | 4 | 1 | 5 | 4 | 1 | 0.3667 |  |  | 11 | 17.4828 | 13.7931 | 426979.2759 | 7838.7241 | 434818.0000 | 0 | 0 | Submit action:19; Invalid action:5; Max turns reached:4; Error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 262144 tokens. However, you requested 950 output tokens and your prompt contains at least 261195 input tokens, for a total of at least 262145 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=261195):1 |
| lead_qualification | 30 | 9 | 0.3000 | 26 | 3 | 0 | 0 | 0 | 1 | 0.3000 |  |  | 9 | 12.3103 | 11.8621 | 246630.4138 | 4417.7241 | 251048.1379 | 0 | 0 | Submit action:26; Max turns reached:3; Error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 262144 tokens. However, you requested 950 output tokens and your prompt contains at least 261195 input tokens, for a total of at least 262145 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=261195):1 |
| private_customer_information | 30 | 12 | 0.4000 | 26 | 0 | 0 | 2 | 2 | 2 | 0.4000 |  |  | 12 | 12.0714 | 10.3214 | 114728.6071 | 4731.7857 | 119460.3929 | 0 | 0 | Submit action:26; Invalid action:2; Error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 262144 tokens. However, you requested 950 output tokens and your prompt contains at least 261195 input tokens, for a total of at least 262145 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=261195):1; Error: 'AccountId':1 |
| quote_approval | 30 | 3 | 0.1000 | 28 | 0 | 1 | 0 | 0 | 1 | 0.1000 |  |  | 3 | 11.3793 | 10.1034 | 371092.5172 | 4713.8966 | 375806.4138 | 0 | 0 | Submit action:28; Error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 262144 tokens. However, you requested 950 output tokens and your prompt contains at least 261195 input tokens, for a total of at least 262145 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=261195):1; SOQL/SOSL query error:1 |

## Top API/Run Errors

- 6: Error: litellm.ContextWindowExceededError: litellm.BadRequestError: ContextWindowExceededError: OpenAIException - This model's maximum context length is 262144 tokens. However, you requested 950 output tokens and your prompt contains at least 261195 input tokens, for a total of at least 262145 tokens. Please reduce the length of the input prompt or the number of requested output tokens. (parameter=input_tokens, value=261195)
- 3: Error: 'Subject'
- 1: Error: 'Name'
- 1: Error: 'AccountId'
