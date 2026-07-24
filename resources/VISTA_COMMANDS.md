## Directory
cd /work/11669/aleccheng/vista/CRMArena

## Export OPEN_APIKey to VLLM
export OPENAI_API_KEY=dummy
export OPENAI_API_BASE=http://127.0.0.1:8001/v1
export OPENAI_BASE_URL=http://127.0.0.1:8001/v1

## Run Tasks
```bash
python -u run_tasks.py \
 --model openai/Qwen3.5-35B-A3B \
 --task_category all \
 --agent_eval_mode aided \
 --log_dir results/original/react_qwen35 \
 --agent_strategy react \
 --max_turns 5 \
 --llm_provider openai \
 --reuse_results \
 --privacy_aware_prompt false \
 --org_type original
 ```

```bash
python -u run_tasks.py \
 --model openai/Qwen3.5-35B-A3B \
 --task_category knowledge_qa \
 --agent_eval_mode aided \
 --log_dir results/original/react_qwen35_smoke \
 --agent_strategy react \
 --llm_provider openai \
 --max_turns 5 \
 --reuse_results \
 --privacy_aware_prompt false \
 --org_type original
```

## Take over a compute node
```bash
srun --jobid=857301 --overlap -p gh -N 1 -n 1 -c 2 -t 1:00:00 -A ECS24025 --pty bash -l
```

```bash
cd /work/11669/aleccheng/vista/CRMArena && source .venv/bin/activate && export HF_HOME=/work/11669/aleccheng/vista/cache-vista/huggingface HF_DATASETS_CACHE=/work/11669/aleccheng/vista/cache-vista/huggingface/datasets OPENAI_API_KEY=dummy OPENAI_API_BASE=http://127.0.0.1:8001/v1 OPENAI_BASE_URL=http://127.0.0.1:8001/v1 && python -u run_tasks.py --model openai/Qwen3.5-35B-A3B --task_category all --agent_eval_mode aided --log_dir results/b2b_interactive/react_qwen35_localjudge --agent_strategy react --interactive --llm_provider openai --judge_model openai/Qwen3.5-35B-A3B --judge_provider openai --user_model openai/Qwen3.5-35B-A3B --user_provider openai --max_turns 20 --max_user_turns 10 --reuse_results --privacy_aware_prompt false --org_type b2b
```

## Use Summarizer
```bash
cd /work/11669/aleccheng/vista/CRMArena && source .venv/bin/activate && python scripts/summarize_crmarena_results.py results/original/react_qwen35_all_smoke/results_openai/Qwen3.5-35B-A3B_react_all.json
```
## Serve LLAMA
cd /work/11669/aleccheng/vista/qwen_agent_ft && sbatch -A ECS24025 -t 8:00:00 scripts/vista_serve_llama31_8b_vllm.sbatch scripts/configs/serve_llama31_8b_vista_config.yaml

## Then Test
LLAMA_HOST=$(cat /work/11669/aleccheng/vista/qwen_agent_ft/llama31_8b_crmarena_judge_user_vllm_host.txt) && curl http://$LLAMA_HOST:8002/v1/models

## Serve Job
cd /work/11669/aleccheng/vista/CRMArena && source .venv/bin/activate && LLAMA_HOST=$(cat /work/11669/aleccheng/vista/qwen_agent_ft/llama31_8b_crmarena_judge_user_vllm_host.txt)
&& AGENT_BASE_URL=http://127.0.0.1:8001/v1 JUDGE_BASE_URL=http://$LLAMA_HOST:8002/v1 USER_BASE_URL=http://$LLAMA_HOST:8002/v1 TASKS_CSV=knowledge_qa,monthly_trend_analysis
ORG_TYPES_CSV=b2b MAX_JOBS=1 ./run_tasks_crmarena_pro.sh

Sequential script

```bash
cd /work/11669/aleccheng/vista/CRMArena && mkdir -p logs/attached && nohup srun -p gh -A ECS24025 --jobid=854802 --overlap -N 1 -n 1 -c 2 -t 8:50:00 bash -lc 'cd /work/11669/aleccheng/vista/CRMArena && source .venv/bin/activate && AGENT_BASE_URL=http://127.0.0.1:8001/v1 TASKS_CSV=knowledge_qa,monthly_trend_analysis ORG_TYPES_CSV=b2b MAX_VERIFIER_RETRIES=3 ./run_tasks_crmarena_pro_ab_sequential.sh' > logs/attached/crmarena_pro_ab_qwen35_$(date +%Y%m%d_%H%M).log 2>&1 &
```

### If later you get Llama access, you can override only these:

JUDGE_BASE_URL=http://$LLAMA_HOST:8002/v1 USER_BASE_URL=http://$LLAMA_HOST:8002/v1 JUDGE_MODEL=meta-llama/Llama-3.1-8B-Instruct USER_MODEL=meta-llama/Llama-3.1-8B-Instruct

module purge && module load gcc/13.2.0 cuda/12.6 python3 && cd /work/11669/aleccheng/vista/qwen_agent_ft && source .venv-vista/bin/activate && hf auth logout && hf auth login --force

### Light smoke test: 2 examples per category, baseline only, 20 agent turns, 10 user turns, Llama judge/user:

```bash
cd /work/11669/aleccheng/vista/CRMArena && source .venv/bin/activate && LLAMA_HOST=$(cat /work/11669/aleccheng/vista/qwen_agent_ft/llama31_8b_crmarena_judge_user_vllm_host.txt) && AGENT_BASE_URL=http://127.0.0.1:8001/v1 USE_LLAMA_JUDGE=true LLAMA_HOST=$LLAMA_HOST RUN_TAG=focus_smoke_base MAX_TASKS_PER_CATEGORY=2 MAX_TURNS=20 MAX_USER_TURNS=10 AGENT_MAX_TOKENS=1024 USE_SYNTACTIC_VERIFIER=false ./run_tasks_crmarena_pro.sh
```

### If you want the A/B smoke, baseline then verifier:

```bash
cd /work/11669/aleccheng/vista/CRMArena && Q35_JOB=$(cat /work/11669/aleccheng/vista/qwen_agent_ft/q35_vista_vllm_job_id.txt) && LLAMA_HOST=$(cat /work/11669/aleccheng/vista/qwen_agent_ft/llama31_8b_crmarena_judge_user_vllm_host.txt) && mkdir -p logs/run_wrappers && nohup srun -p gh -A ECS24025 --jobid="$Q35_JOB" --overlap -N 1 -n 1 -c 1 -t 01:00:00 bash -lc "cd /work/11669/aleccheng/vista/CRMArena && source .venv/bin/activate && RUN_TAG=focus_smoke_retry MAX_TASKS_PER_CATEGORY=2 MAX_TURNS=20 USE_LLAMA_JUDGE=true LLAMA_HOST=$LLAMA_HOST AGENT_BASE_URL=http://127.0.0.1:8001/v1 ./run_tasks_crmarena_pro_ab_sequential.sh" > logs/run_wrappers/focus_smoke_retry.log 2>&1 &
```

### Full?

```bash
cd /work/11669/aleccheng/vista/CRMArena && Q35_JOB=$(cat /work/11669/aleccheng/vista/qwen_agent_ft/q35_vista_vllm_job_id.txt) && LLAMA_HOST=$(cat /work/11669/aleccheng/vista/qwen_agent_ft/llama31_8b_crmarena_judge_user_vllm_host.txt) && mkdir -p logs/run_wrappers && nohup srun -p gh -A ECS24025 --jobid="$Q35_JOB" --overlap -N 1 -n 1 -c 1 -t 08:00:00 bash -lc "cd /work/11669/aleccheng/vista/CRMArena && source .venv/bin/activate && RUN_TAG=full_baseline MAX_TURNS=20 USE_LLAMA_JUDGE=true LLAMA_HOST=$LLAMA_HOST AGENT_BASE_URL=http://127.0.0.1:8001/v1 ./run_tasks_crmarena_pro_ab_sequential.sh" > logs/run_wrappers/full_baseline.log 2>&1 &
```


### Full focused baseline later:

```bash
cd /work/11669/aleccheng/vista/CRMArena && source .venv/bin/activate && LLAMA_HOST=$(cat /work/11669/aleccheng/vista/qwen_agent_ft/llama31_8b_crmarena_judge_user_vllm_host.txt) && AGENT_BASE_URL=http://127.0.0.1:8001/v1 USE_LLAMA_JUDGE=true LLAMA_HOST=$LLAMA_HOST RUN_TAG=focus_full_base MAX_TASKS_PER_CATEGORY=0 MAX_TURNS=20 MAX_USER_TURNS=10 AGENT_MAX_TOKENS=1024 USE_SYNTACTIC_VERIFIER=false ./run_tasks_crmarena_pro.sh
```

```bash
cd /work/11669/aleccheng/vista/CRMArena && Q35_JOB=$(cat /work/11669/aleccheng/vista/qwen_agent_ft/q35_vista_vllm_job_id.txt) && LLAMA_HOST=$(cat /work/11669/aleccheng/vista/qwen_agent_ft/llama31_8b_crmarena_judge_user_vllm_host.txt) && mkdir -p logs/run_wrappers && nohup srun -p gh -A ECS24025 --jobid="$Q35_JOB" --overlap -N 1 -n 1 -c 1 -t 01:00:00 bash -lc "cd /work/11669/aleccheng/vista/CRMArena && source .venv/bin/activate && RUN_TAG=focus_smoke_retry MAX_TASKS_PER_CATEGORY=2 MAX_TURNS=20 USE_LLAMA_JUDGE=true LLAMA_HOST=$LLAMA_HOST AGENT_BASE_URL=http://127.0.0.1:8001/v1 ./run_tasks_crmarena_pro_ab_sequential.sh" > logs/run_wrappers/focus_smoke_retry.log 2>&1 &
```

## Resume
```bash
cd /work/11669/aleccheng/vista/CRMArena && Q35_JOB=$(cat /work/11669/aleccheng/vista/qwen_agent_ft/q35_vista_vllm_job_id.txt) && LLAMA_HOST=$(cat /work/11669/aleccheng/vista/qwen_agent_ft/llama31_8b_crmarena_judge_user_vllm_host.txt) && mkdir -p logs/run_wrappers && nohup srun -p gh -A ECS24025 --jobid="$Q35_JOB" --overlap -N 1 -n 1 -c 1 -t 02:30:00 bash -lc "cd /work/11669/aleccheng/vista/CRMArena && source .venv/bin/activate && RUN_TAG=full_baseline MAX_TASKS_PER_CATEGORY=0 MAX_TURNS=20 MAX_USER_TURNS=10 AGENT_MAX_TOKENS=950 USE_SYNTACTIC_VERIFIER=false USE_LLAMA_JUDGE=true LLAMA_HOST=$LLAMA_HOST AGENT_BASE_URL=http://127.0.0.1:8001/v1 ./run_tasks_crmarena_pro.sh" > logs/run_wrappers/full_baseline_resume.log 2>&1 &
```


```bash
cd /work/11669/aleccheng/vista/CRMArena && Q35_JOB=$(cat /work/11669/aleccheng/vista/qwen_agent_ft/q35_vista_vllm_job_id.txt) && LLAMA_HOST=$(cat /work/11669/aleccheng/vista/qwen_agent_ft/llama31_8b_crmarena_judge_user_vllm_host.txt) && mkdir -p logs/run_wrappers && nohup srun -p gh -A ECS24025 --jobid="$Q35_JOB" --overlap -N 1 -n 1 -c 1 -t 08:00:00 bash -lc "cd /work/11669/aleccheng/vista/CRMArena && source .venv/bin/activate && RUN_TAG=base_default_full MAX_TURNS=20 MAX_USER_TURNS=10 USE_SYNTACTIC_VERIFIER=false USE_LLAMA_JUDGE=true LLAMA_HOST=$LLAMA_HOST AGENT_BASE_URL=http://127.0.0.1:8001/v1 ./run_tasks_crmarena_pro.sh" > logs/run_wrappers/base_default_full.log 2>&1 &
```

## Action Verifier Test
```bash
cd /work/11669/aleccheng/vista/CRMArena && source .venv/bin/activate && python scripts/analyze_verifier_on_results.py results/b2b_multi-turn/react_openai_Qwen3.5-35B-A3B_full_baseline_noverifier/results_openai --examples 3 --csv verifier_audit.csv --jsonl verifier_audit.jsonl
```

```bash ablation on verifiers
cd /work/11669/aleccheng/vista/CRMArena && mkdir -p logs/run_wrappers && nohup srun -p gh -A ECS24025 --jobid=858267 --overlap -N 1 -n 1 -c 1 -t 03:00:00 bash -lc 'cd /work/11669/aleccheng/vista/CRMArena && source .venv/bin/activate && BASE_RUN_TAG=ablation_smoke_q35_858267_llama_857224 MAX_TASKS_PER_CATEGORY=3 MAX_TURNS=20 MAX_USER_TURNS=10 ./run_tasks_crmarena_pro_ablation_smoke.sh' > logs/run_wrappers/ablation_smoke_q35_858267_llama_857224.log 2>&1 &
```

```bash
cd /work/11669/aleccheng/vista/CRMArena && mkdir -p logs/run_wrappers && nohup srun -p gh -A ECS24025 --jobid=858267 --overlap -N 1 -n 1 -c 1 -t 03:00:00 bash -lc 'cd /work/11669/aleccheng/vista/CRMArena && source .venv/bin/activate && BASE_RUN_TAG=ablation_smoke_q35_858267_llama_857224 MAX_TASKS_PER_CATEGORY=3 MAX_TURNS=20 MAX_USER_TURNS=10 ./run_tasks_crmarena_pro_ablation_smoke.sh' > logs/run_wrappers/ablation_smoke_q35_858267_llama_857224.log 2>&1 &
```

```bash
cd /work/11669/aleccheng/vista/CRMArena && mkdir -p logs/run_wrappers && nohup srun -p gh -A ECS24025 --jobid=858267 --overlap -N 1 -n 1 -c 1 -t 09:00:00 bash -lc 'cd /work/11669/aleccheng/vista/CRMArena && source .venv/bin/activate && AGENT_JOB_ID=858267 LLAMA_JOB_ID=858420 LLAMA_HOST=c638-031.vista.tacc.utexas.edu BASE_RUN_TAG=ablation30_q35_858267_llama_858420 BASELINE_RUN_TAG=base_default_full BASELINE_RESULT_SUFFIX=_noverifier MAX_TASKS_PER_CATEGORY=30 MAX_TURNS=20 MAX_USER_TURNS=10 ./run_tasks_crmarena_pro_ablation_smoke.sh' > logs/run_wrappers/ablation30_q35_858267_llama_858420.log 2>&1 &
```

## OR Run this in the compute node

 Run this on c609-062:

```bash
cd /work/11669/aleccheng/vista/CRMArena && mkdir -p logs/run_wrappers && source .venv/bin/activate && nohup env AGENT_MODEL=openai/Qwen3.5-35B-A3B AGENT_BASE_URL=http://127.0.0.1:8001/v1 AGENT_API_KEY=dummy USE_LLAMA_JUDGE=true LLAMA_HOST=c638-031.vista.tacc.utexas.edu LLAMA_PORT=8002 LLAMA_MODEL=meta-llama/Llama-3.1-8B-Instruct TASKS_CSV=quote_approval,lead_qualification,case_routing,private_customer_information,internal_operation_data,confidential_company_knowledge ORG_TYPES_CSV=b2b INTERACTIVE=true MAX_TASKS_PER_CATEGORY=30 MAX_TURNS=20 MAX_USER_TURNS=10 AGENT_MAX_TOKENS=950 USE_SYNTACTIC_VERIFIER=true MAX_VERIFIER_RETRIES=3 USE_WORKING_MEMORY=false ROUTING_MODE=none SCAFFOLD_MODE=none RUN_TAG=ablation30_q35_858267_llama_858420_syntactic_verifier_only MAX_JOBS=1 ./run_tasks_crmarena_pro.sh > logs/run_wrappers/syntactic_verifier_30_q35_858267_llama_858420.log 2>&1 < /dev/null & echo $! > logs/run_wrappers/syntactic_verifier_30_q35_858267_llama_858420.pid
``` 

```bash
cd /work/11669/aleccheng/vista/CRMArena && mkdir -p logs/run_wrappers && source .venv/bin/activate && nohup env AGENT_MODEL=openai/Qwen3.5-35B-A3B AGENT_BASE_URL=http://127.0.0.1:8001/v1 AGENT_API_KEY=dummy USE_LLAMA_JUDGE=true LLAMA_HOST=c638-031.vista.tacc.utexas.edu LLAMA_PORT=8002 LLAMA_MODEL=meta-llama/Llama-3.1-8B-Instruct TASKS_CSV=quote_approval,lead_qualification,case_routing,private_customer_information,internal_operation_data,confidential_company_knowledge ORG_TYPES_CSV=b2b INTERACTIVE=true MAX_TASKS_PER_CATEGORY=30 MAX_TURNS=20 MAX_USER_TURNS=10 AGENT_MAX_TOKENS=950 USE_SYNTACTIC_VERIFIER=true MAX_VERIFIER_RETRIES=3 USE_WORKING_MEMORY=false ROUTING_MODE=none SCAFFOLD_MODE=none RUN_TAG=ablation30_q35_858267_llama_858420_syntactic_verifier_only MAX_JOBS=1 ./run_tasks_crmarena_pro.sh > /work/11669/aleccheng/vista/CRMArena/logs/run_wrappers/syntactic_verifier_30_q35_858267_llama_858420.log 2>&1 < /dev/null & echo $! > /work/11669/aleccheng/vista/CRMArena/logs/run_wrappers/syntactic_verifier_30_q35_858267_llama_858420.pid
```

ssh c609-062.vista.tacc.utexas.edu 'ps -u aleccheng -o pid,ppid,stat,etime,cmd | egrep "run_tasks_crmarena_pro|run_tasks.py|syntactic_verifier|ablation30" | grep -v egrep'


From c613-021:

```bash
cd /work/11669/aleccheng/vista/CRMArena && mkdir -p /work/11669/aleccheng/vista/CRMArena/logs/run_wrappers && source .venv/bin/activate && setsid env LLAMA_HOST=c610-092.vista.tacc.utexas.edu LLAMA_PORT=8002 BASE_TAG_PREFIX=q35_859621_llama_859619 AGENT_BASE_URL=http://127.0.0.1:8001/v1 ./run_tasks_crmarena_pro_remaining_ablation_and_full_base.sh > /work/11669/aleccheng/vista/CRMArena/logs/run_wrappers/remaining_ablation_and_full_base_$(hostname)_$(date +%Y%m%d_%H%M).log 2>&1 < /dev/null &
  ```

```bash
cd /work/11669/aleccheng/vista/CRMArena && source .venv/bin/activate && mkdir -p logs/run_wrappers && nohup env AGENT_MODEL=openai/Qwen3.5-35B-A3B AGENT_BASE_URL=http://127.0.0.1:8001/v1 AGENT_API_KEY=dummy USE_LLAMA_JUDGE=true LLAMA_HOST=c610-092.vista.tacc.utexas.edu LLAMA_PORT=8002 LLAMA_MODEL=meta-llama/Llama-3.1-8B-Instruct TASKS_CSV=quote_approval,lead_qualification,case_routing,private_customer_information,internal_operation_data,confidential_company_knowledge ORG_TYPES_CSV=b2b INTERACTIVE=true MAX_TASKS_PER_CATEGORY=30 MAX_TURNS=20 MAX_USER_TURNS=10 AGENT_MAX_TOKENS=950 USE_SYNTACTIC_VERIFIER=true MAX_VERIFIER_RETRIES=3 USE_WORKING_MEMORY=false ROUTING_MODE=none SCAFFOLD_MODE=none RUN_TAG=syntax_verifier_v2 MAX_JOBS=1 ./run_tasks_crmarena_pro.sh > logs/run_wrappers/syntax_verifier_v2.log 2>&1 < /dev/null & echo $!
```


### Resume baseline run
```bash
cd /work/11669/aleccheng/vista/CRMArena && mkdir -p logs/run_wrappers && nohup setsid
srun -p gh -A ECS24025 --jobid=859621 --overlap -N 1 -n 1 -c 1 -t 03:00:00 bash -lc 'cd /work/11669/aleccheng/vista/CRMArena && source .venv/bin/activate && env AGENT_MODEL=openai/Qwen3.5-35B-A3B AGENT_BASE_URL=http://127.0.0.1:8001/v1  AGENT_API_KEY=dummy USE_LLAMA_JUDGE=true LLAMA_HOST=c610-092.vista.tacc.utexas.edu LLAMA_PORT=8002 LLAMA_MODEL=meta-llama/Llama-3.1-8B-Instruct TASKS_CSV=quote_approval,lead_qualification,case_routing,private_customer_information,internal_operation_data,confidential_company_knowledge ORG_TYPES_CSV=b2b INTERACTIVE=true MAX_TASKS_PER_CATEGORY=0 MAX_TURNS=20 MAX_USER_TURNS=10 AGENT_MAX_TOKENS=950 USE_SYNTACTIC_VERIFIER=false USE_WORKING_MEMORY=false ROUTING_MODE=none SCAFFOLD_MODE=none RUN_TAG=base_full_unmodified_q35_859621_llama_859619 MAX_JOBS=1 ./run_tasks_crmarena_pro.sh' > logs/run_wrappers/finish_base_full_unmodified_q35_859621_llama_859619.log 2>&1 < /dev/null & echo $!
```

```bash

cd /work/11669/aleccheng/vista/CRMArena && source .venv/bin/activate && PYTHONPATH=. python scripts/summarize_crmarena_results.py results/b2b_multi-turn/react_openai_Qwen3.5-35B-A3B_base_full_unmodified_q35_859621_llama_859619_noverifier_nowm --csv results/b2b_multi-turn/summaries/base_full_unmodified_q35_859621_llama_859619_deduped_summary.csv --markdown results/b2b_multi-turn/summaries/base_full_unmodified_q35_859621_llama_859619_deduped_summary.md
  ```