## Serve Qwen 3.5 With vLLM On DeltaAI

The old command used `scripts/configs/serve_q35_config.yaml`, but that file is
not present in the current `qwen_agent_ft` checkout. Use one of the Delta configs
that exists:

- Base model on port `8001`: `scripts/configs/serve_q35_delta_base.yaml`
- LoRA model on port `8002`: `scripts/configs/serve_q35_delta_config.yaml`

Both Delta configs serve the base model directly from Hugging Face:

```text
Qwen/Qwen3.5-35B-A3B
```

They do not require a local copy under `qwen_agent_ft/models`.

### Serve Base Qwen

First create the DeltaAI serving virtualenv. The serving configs expect this
path:

```bash
/work/hdd/bgtb/acheng11/qwen_agent_ft/.venv-deltaai
```

Run this once before submitting the vLLM job:

```bash
cd /work/hdd/bgtb/acheng11/qwen_agent_ft

INSTALL_VLLM=1 scripts/deltaai_setup_venv.sh
```

Then submit the base-model serving job:

```bash
cd /work/hdd/bgtb/acheng11/qwen_agent_ft
mkdir -p logs

sbatch -A bgtb-dtai-gh -t 10:00:00 \
  scripts/deltaai_serve_qwen35_vllm.sbatch \
  scripts/configs/serve_q35_delta_base.yaml
```

Run the LoRA config instead:

```bash
cd /work/hdd/bgtb/acheng11/qwen_agent_ft
mkdir -p logs

sbatch -A bgtb-dtai-gh -t 10:00:00 \
  scripts/deltaai_serve_qwen35_vllm.sbatch \
  scripts/configs/serve_q35_delta_config.yaml
```

### Check The Server

The sbatch script writes the serving host and job id under
`/work/hdd/bgtb/acheng11/qwen_agent_ft/logs`.

```bash
cd /work/hdd/bgtb/acheng11/qwen_agent_ft

cat logs/qwen35_base_vllm_job_id.txt
cat logs/qwen35_base_vllm_host.txt

QWEN_HOST="$(cat logs/qwen35_base_vllm_host.txt)"
curl "http://${QWEN_HOST}:8001/v1/models"
```

For the LoRA config, use:

```bash
cat logs/qwen35_lora_vllm_job_id.txt
cat logs/qwen35_lora_vllm_host.txt

QWEN_HOST="$(cat logs/qwen35_lora_vllm_host.txt)"
curl "http://${QWEN_HOST}:8002/v1/models"
```

### Run Benchmarks From The vLLM Compute Node

Assumption for every command below: first SSH into the exact compute node that is
serving vLLM. Then `127.0.0.1:8001` is the vLLM server you want to use, and no
`--overlap` Slurm step is needed.

Recommended pattern after SSH'ing into the compute node:

```bash
cd /work/hdd/bgtb/acheng11/CRMArena
module purge >/dev/null 2>&1 || true
module load gcc-native
module load cudatoolkit/25.5_12.9
module load python/miniforge3_pytorch/2.10.0
source .venv-crm-modern/bin/activate

curl http://127.0.0.1:8001/v1/models
```

To keep a run alive after disconnecting, either start it inside `tmux`, or use
the `nohup bash -lc ... &` blocks below from the compute node.

The folder/resume key is `RUN_TAG`. To resume into the same result folders, reuse
exactly the same `RUN_TAG` as the interrupted run. `run_tasks.py` is invoked with
`--reuse_results` by the wrapper scripts, so completed task ids are skipped.

For your current interrupted full external run, the resume tag is:

```bash
RUN_TAG=external_full_overlap_2797701_20260731_1005
```

That produces the same batch folders as before:

```text
...external_full_overlap_2797701_20260731_1005_regular_external...
...external_full_overlap_2797701_20260731_1005_confidentiality...
```

### Direct Lead Qualification Smoke Test

```bash
cd /work/hdd/bgtb/acheng11/CRMArena
mkdir -p logs/run_wrappers

RUN_NAME="lead_dsl_smoke_node_$(date +%Y%m%d_%H%M)"
nohup bash -lc '
  cd /work/hdd/bgtb/acheng11/CRMArena
  module purge >/dev/null 2>&1 || true
  module load gcc-native
  module load cudatoolkit/25.5_12.9
  module load python/miniforge3_pytorch/2.10.0
  source .venv-crm-modern/bin/activate
  QWEN_BASE_URL=http://127.0.0.1:8001/v1 \
  QWEN_MODEL=openai/Qwen3.5-35B-A3B \
  CRMARENA_VENV=/work/hdd/bgtb/acheng11/CRMArena/.venv-crm-modern \
  PYTHON_BIN="$(command -v python)" \
  RUN_TAG='"$RUN_NAME"' \
  ./run_tasks_crmarena_pro_lead_dsl_smoke.sh
' > "logs/run_wrappers/${RUN_NAME}.log" 2>&1 < /dev/null &

echo "Started wrapper PID: $!"
echo "Log: /work/hdd/bgtb/acheng11/CRMArena/logs/run_wrappers/${RUN_NAME}.log"
```

### Targeted External Gate Regression Benchmark

Runs 25 examples each for the affected tasks after knowledge-article gate changes:

- `original/knowledge_qa`
- `b2b/confidential_company_knowledge`

Run this from the same compute node as the vLLM server at `127.0.0.1:8001`.

```bash
cd /work/hdd/bgtb/acheng11/CRMArena
mkdir -p logs/run_wrappers

RUN_NAME="external_gate_regression_25_node_$(date +%Y%m%d_%H%M)"
nohup bash -lc '
  cd /work/hdd/bgtb/acheng11/CRMArena
  module purge >/dev/null 2>&1 || true
  module load gcc-native
  module load cudatoolkit/25.5_12.9
  module load python/miniforge3_pytorch/2.10.0
  source .venv-crm-modern/bin/activate
  QWEN_BASE_URL=http://127.0.0.1:8001/v1 \
  QWEN_MODEL=openai/Qwen3.5-35B-A3B \
  MAX_TASKS_PER_CATEGORY=25 \
  REGULAR_EXTERNAL_TASKS_CSV=knowledge_qa \
  CONFIDENTIALITY_TASKS_CSV=confidential_company_knowledge \
  CRMARENA_VENV=/work/hdd/bgtb/acheng11/CRMArena/.venv-crm-modern \
  PYTHON_BIN="$(command -v python)" \
  RUN_TAG='"$RUN_NAME"' \
  ./run_tasks_crmarena_pro_external_full.sh
' > "logs/run_wrappers/${RUN_NAME}.log" 2>&1 < /dev/null &

echo "Started wrapper PID: $!"
echo "Log: /work/hdd/bgtb/acheng11/CRMArena/logs/run_wrappers/${RUN_NAME}.log"
```

### Direct Full Lead Qualification Benchmark

```bash
cd /work/hdd/bgtb/acheng11/CRMArena
mkdir -p logs/run_wrappers

RUN_NAME="lead_dsl_full_node_$(date +%Y%m%d_%H%M)"
nohup bash -lc '
  cd /work/hdd/bgtb/acheng11/CRMArena
  module purge >/dev/null 2>&1 || true
  module load gcc-native
  module load cudatoolkit/25.5_12.9
  module load python/miniforge3_pytorch/2.10.0
  source .venv-crm-modern/bin/activate
  QWEN_BASE_URL=http://127.0.0.1:8001/v1 \
  QWEN_MODEL=openai/Qwen3.5-35B-A3B \
  CRMARENA_VENV=/work/hdd/bgtb/acheng11/CRMArena/.venv-crm-modern \
  PYTHON_BIN="$(command -v python)" \
  MAX_TASKS_PER_CATEGORY=0 \
  RUN_TAG='"$RUN_NAME"' \
  ./run_tasks_crmarena_pro_lead_dsl_smoke.sh
' > "logs/run_wrappers/${RUN_NAME}.log" 2>&1 < /dev/null &

echo "Started wrapper PID: $!"
echo "Log: /work/hdd/bgtb/acheng11/CRMArena/logs/run_wrappers/${RUN_NAME}.log"
```

### Direct Quote Approval Smoke Test

```bash
cd /work/hdd/bgtb/acheng11/CRMArena
mkdir -p logs/run_wrappers

RUN_NAME="quote_dsl_smoke_node_$(date +%Y%m%d_%H%M)"
nohup bash -lc '
  cd /work/hdd/bgtb/acheng11/CRMArena
  module purge >/dev/null 2>&1 || true
  module load gcc-native
  module load cudatoolkit/25.5_12.9
  module load python/miniforge3_pytorch/2.10.0
  source .venv-crm-modern/bin/activate
  QWEN_BASE_URL=http://127.0.0.1:8001/v1 \
  QWEN_MODEL=openai/Qwen3.5-35B-A3B \
  CRMARENA_VENV=/work/hdd/bgtb/acheng11/CRMArena/.venv-crm-modern \
  PYTHON_BIN="$(command -v python)" \
  RUN_TAG='"$RUN_NAME"' \
  ./run_tasks_crmarena_pro_quote_dsl_smoke.sh
' > "logs/run_wrappers/${RUN_NAME}.log" 2>&1 < /dev/null &

echo "Started wrapper PID: $!"
echo "Log: /work/hdd/bgtb/acheng11/CRMArena/logs/run_wrappers/${RUN_NAME}.log"
```

### Direct Full Quote Approval Benchmark

```bash
cd /work/hdd/bgtb/acheng11/CRMArena
mkdir -p logs/run_wrappers

RUN_NAME="quote_dsl_full_node_$(date +%Y%m%d_%H%M)"
nohup bash -lc '
  cd /work/hdd/bgtb/acheng11/CRMArena
  module purge >/dev/null 2>&1 || true
  module load gcc-native
  module load cudatoolkit/25.5_12.9
  module load python/miniforge3_pytorch/2.10.0
  source .venv-crm-modern/bin/activate
  QWEN_BASE_URL=http://127.0.0.1:8001/v1 \
  QWEN_MODEL=openai/Qwen3.5-35B-A3B \
  CRMARENA_VENV=/work/hdd/bgtb/acheng11/CRMArena/.venv-crm-modern \
  PYTHON_BIN="$(command -v python)" \
  MAX_TASKS_PER_CATEGORY=0 \
  RUN_TAG='"$RUN_NAME"' \
  ./run_tasks_crmarena_pro_quote_dsl_smoke.sh
' > "logs/run_wrappers/${RUN_NAME}.log" 2>&1 < /dev/null &

echo "Started wrapper PID: $!"
echo "Log: /work/hdd/bgtb/acheng11/CRMArena/logs/run_wrappers/${RUN_NAME}.log"
```

### Direct Case Routing Smoke Test

```bash
cd /work/hdd/bgtb/acheng11/CRMArena
mkdir -p logs/run_wrappers

RUN_NAME="case_dsl_smoke_node_$(date +%Y%m%d_%H%M)"
nohup bash -lc '
  cd /work/hdd/bgtb/acheng11/CRMArena
  module purge >/dev/null 2>&1 || true
  module load gcc-native
  module load cudatoolkit/25.5_12.9
  module load python/miniforge3_pytorch/2.10.0
  source .venv-crm-modern/bin/activate
  QWEN_BASE_URL=http://127.0.0.1:8001/v1 \
  QWEN_MODEL=openai/Qwen3.5-35B-A3B \
  CRMARENA_VENV=/work/hdd/bgtb/acheng11/CRMArena/.venv-crm-modern \
  PYTHON_BIN="$(command -v python)" \
  RUN_TAG='"$RUN_NAME"' \
  ./run_tasks_crmarena_pro_case_dsl_smoke.sh
' > "logs/run_wrappers/${RUN_NAME}.log" 2>&1 < /dev/null &

echo "Started wrapper PID: $!"
echo "Log: /work/hdd/bgtb/acheng11/CRMArena/logs/run_wrappers/${RUN_NAME}.log"
```

### Direct Full Case Routing Benchmark

```bash
cd /work/hdd/bgtb/acheng11/CRMArena
mkdir -p logs/run_wrappers

RUN_NAME="case_dsl_full_node_$(date +%Y%m%d_%H%M)"
nohup bash -lc '
  cd /work/hdd/bgtb/acheng11/CRMArena
  module purge >/dev/null 2>&1 || true
  module load gcc-native
  module load cudatoolkit/25.5_12.9
  module load python/miniforge3_pytorch/2.10.0
  source .venv-crm-modern/bin/activate
  QWEN_BASE_URL=http://127.0.0.1:8001/v1 \
  QWEN_MODEL=openai/Qwen3.5-35B-A3B \
  CRMARENA_VENV=/work/hdd/bgtb/acheng11/CRMArena/.venv-crm-modern \
  PYTHON_BIN="$(command -v python)" \
  MAX_TASKS_PER_CATEGORY=0 \
  RUN_TAG='"$RUN_NAME"' \
  ./run_tasks_crmarena_pro_case_dsl_smoke.sh
' > "logs/run_wrappers/${RUN_NAME}.log" 2>&1 < /dev/null &

echo "Started wrapper PID: $!"
echo "Log: /work/hdd/bgtb/acheng11/CRMArena/logs/run_wrappers/${RUN_NAME}.log"
```

### Direct External Knowledge QA Smoke Test

```bash
cd /work/hdd/bgtb/acheng11/CRMArena
mkdir -p logs/run_wrappers

RUN_NAME="external_knowledge_qa_smoke_node_$(date +%Y%m%d_%H%M)"
nohup bash -lc '
  cd /work/hdd/bgtb/acheng11/CRMArena
  module purge >/dev/null 2>&1 || true
  module load gcc-native
  module load cudatoolkit/25.5_12.9
  module load python/miniforge3_pytorch/2.10.0
  source .venv-crm-modern/bin/activate
  QWEN_BASE_URL=http://127.0.0.1:8001/v1 \
  QWEN_MODEL=openai/Qwen3.5-35B-A3B \
  EXTERNAL_TASK=knowledge_qa \
  USE_KNOWLEDGE_QA_DSL=true \
  USE_NED_DSL=false \
  USE_EXTERNAL_ROUTER_DSL=true \
  CRMARENA_VENV=/work/hdd/bgtb/acheng11/CRMArena/.venv-crm-modern \
  PYTHON_BIN="$(command -v python)" \
  RUN_TAG='"$RUN_NAME"' \
  ./run_tasks_crmarena_pro_external_dsl_smoke.sh
' > "logs/run_wrappers/${RUN_NAME}.log" 2>&1 < /dev/null &

echo "Started wrapper PID: $!"
echo "Log: /work/hdd/bgtb/acheng11/CRMArena/logs/run_wrappers/${RUN_NAME}.log"
```

### Direct External Named Entity Disambiguation Smoke Test

```bash
cd /work/hdd/bgtb/acheng11/CRMArena
mkdir -p logs/run_wrappers

RUN_NAME="external_ned_smoke_node_$(date +%Y%m%d_%H%M)"
nohup bash -lc '
  cd /work/hdd/bgtb/acheng11/CRMArena
  module purge >/dev/null 2>&1 || true
  module load gcc-native
  module load cudatoolkit/25.5_12.9
  module load python/miniforge3_pytorch/2.10.0
  source .venv-crm-modern/bin/activate
  QWEN_BASE_URL=http://127.0.0.1:8001/v1 \
  QWEN_MODEL=openai/Qwen3.5-35B-A3B \
  EXTERNAL_TASK=named_entity_disambiguation \
  USE_KNOWLEDGE_QA_DSL=false \
  USE_NED_DSL=true \
  USE_EXTERNAL_ROUTER_DSL=true \
  CRMARENA_VENV=/work/hdd/bgtb/acheng11/CRMArena/.venv-crm-modern \
  PYTHON_BIN="$(command -v python)" \
  RUN_TAG='"$RUN_NAME"' \
  ./run_tasks_crmarena_pro_external_dsl_smoke.sh
' > "logs/run_wrappers/${RUN_NAME}.log" 2>&1 < /dev/null &

echo "Started wrapper PID: $!"
echo "Log: /work/hdd/bgtb/acheng11/CRMArena/logs/run_wrappers/${RUN_NAME}.log"
```

### Direct Confidentiality Router Smoke Test

Samples five tasks from each confidentiality category.

```bash
cd /work/hdd/bgtb/acheng11/CRMArena
mkdir -p logs/run_wrappers

RUN_NAME="confidentiality_router_smoke_node_$(date +%Y%m%d_%H%M)"
nohup bash -lc '
  cd /work/hdd/bgtb/acheng11/CRMArena
  module purge >/dev/null 2>&1 || true
  module load gcc-native
  module load cudatoolkit/25.5_12.9
  module load python/miniforge3_pytorch/2.10.0
  source .venv-crm-modern/bin/activate
  QWEN_BASE_URL=http://127.0.0.1:8001/v1 \
  QWEN_MODEL=openai/Qwen3.5-35B-A3B \
  CRMARENA_VENV=/work/hdd/bgtb/acheng11/CRMArena/.venv-crm-modern \
  PYTHON_BIN="$(command -v python)" \
  RUN_TAG='"$RUN_NAME"' \
  ./run_tasks_crmarena_pro_confidentiality_router_smoke.sh
' > "logs/run_wrappers/${RUN_NAME}.log" 2>&1 < /dev/null &

echo "Started wrapper PID: $!"
echo "Log: /work/hdd/bgtb/acheng11/CRMArena/logs/run_wrappers/${RUN_NAME}.log"
```

### Direct Full External-Facing Benchmark

Runs all examples for regular external tasks and confidentiality tasks:

- `original/knowledge_qa`
- `original/named_entity_disambiguation`
- `b2b/private_customer_information`
- `b2b/internal_operation_data`
- `b2b/confidential_company_knowledge`

```bash
cd /work/hdd/bgtb/acheng11/CRMArena
mkdir -p logs/run_wrappers

RUN_NAME="external_full_node_$(date +%Y%m%d_%H%M)"
nohup bash -lc '
  cd /work/hdd/bgtb/acheng11/CRMArena
  module purge >/dev/null 2>&1 || true
  module load gcc-native
  module load cudatoolkit/25.5_12.9
  module load python/miniforge3_pytorch/2.10.0
  source .venv-crm-modern/bin/activate
  QWEN_BASE_URL=http://127.0.0.1:8001/v1 \
  QWEN_MODEL=openai/Qwen3.5-35B-A3B \
  MAX_TASKS_PER_CATEGORY=0 \
  CRMARENA_VENV=/work/hdd/bgtb/acheng11/CRMArena/.venv-crm-modern \
  PYTHON_BIN="$(command -v python)" \
  RUN_TAG='"$RUN_NAME"' \
  ./run_tasks_crmarena_pro_external_full.sh
' > "logs/run_wrappers/${RUN_NAME}.log" 2>&1 < /dev/null &

echo "Started wrapper PID: $!"
echo "Log: /work/hdd/bgtb/acheng11/CRMArena/logs/run_wrappers/${RUN_NAME}.log"
```

### Resume Current Full External Run

Use this exact `RUN_TAG` to write to the same result folders from the interrupted
run that had completed Knowledge QA tasks `0-77`:

```bash
cd /work/hdd/bgtb/acheng11/CRMArena
mkdir -p logs/run_wrappers

RUN_NAME="external_full_resume_2797701_20260731_1005_$(date +%Y%m%d_%H%M)"
nohup bash -lc '
  cd /work/hdd/bgtb/acheng11/CRMArena
  module purge >/dev/null 2>&1 || true
  module load gcc-native
  module load cudatoolkit/25.5_12.9
  module load python/miniforge3_pytorch/2.10.0
  source .venv-crm-modern/bin/activate
  QWEN_BASE_URL=http://127.0.0.1:8001/v1 \
  QWEN_MODEL=openai/Qwen3.5-35B-A3B \
  MAX_TASKS_PER_CATEGORY=0 \
  CRMARENA_VENV=/work/hdd/bgtb/acheng11/CRMArena/.venv-crm-modern \
  PYTHON_BIN="$(command -v python)" \
  RUN_TAG=external_full_overlap_2797701_20260731_1005 \
  ./run_tasks_crmarena_pro_external_full.sh
' > "logs/run_wrappers/${RUN_NAME}.log" 2>&1 < /dev/null &

echo "Started wrapper PID: $!"
echo "Log: /work/hdd/bgtb/acheng11/CRMArena/logs/run_wrappers/${RUN_NAME}.log"
```

Watch progress for any command:

```bash
tail -f /work/hdd/bgtb/acheng11/CRMArena/logs/run_wrappers/${RUN_NAME}.log
```

### If vLLM Is Missing

The sbatch script expects vLLM in:

```bash
/work/hdd/bgtb/acheng11/qwen_agent_ft/.venv-deltaai
```

If the job fails with `No such file or directory` for `.venv-deltaai/bin/activate`,
or with `vllm not found`, run the setup script from `qwen_agent_ft`:

```bash
cd /work/hdd/bgtb/acheng11/qwen_agent_ft
INSTALL_VLLM=1 scripts/deltaai_setup_venv.sh
```

### Full external DSL Benchmark, cappeed at 25 per run

```bash
cd /work/hdd/bgtb/acheng11/CRMArena
mkdir -p logs/run_wrappers

RUN_NAME="full_25$(date +%Y%m%d_%H%M)"
nohup bash -lc '
  cd /work/hdd/bgtb/acheng11/CRMArena
  module purge >/dev/null 2>&1 || true
  module load gcc-native
  module load cudatoolkit/25.5_12.9
  module load python/miniforge3_pytorch/2.10.0
  source .venv-crm-modern/bin/activate
  QWEN_BASE_URL=http://127.0.0.1:8001/v1 \
  QWEN_MODEL=openai/Qwen3.5-35B-A3B \
  MAX_TASKS_PER_CATEGORY=25 \
  CRMARENA_VENV=/work/hdd/bgtb/acheng11/CRMArena/.venv-crm-modern \
  PYTHON_BIN="$(command -v python)" \
  RUN_TAG='"$RUN_NAME"' \
  ./run_tasks_crmarena_pro_external_full.sh
' > "logs/run_wrappers/${RUN_NAME}.log" 2>&1 < /dev/null &

echo "Started wrapper PID: $!"
echo "Log: /work/hdd/bgtb/acheng11/CRMArena/logs/run_wrappers/${RUN_NAME}.log"
```

## General Runtime DSL Runs

These commands exercise the shared `general_dsl` agent path. Run them from the same compute node as the vLLM server at `127.0.0.1:8001`; they are node-local `nohup` wrappers, not Slurm overlap jobs.

### General Runtime External + Confidentiality Smoke Test

Runs 5 examples each for all external-facing and confidentiality tasks:

- `original/knowledge_qa`
- `original/named_entity_disambiguation`
- `b2b/private_customer_information`
- `b2b/internal_operation_data`
- `b2b/confidential_company_knowledge`

```bash
cd /work/hdd/bgtb/acheng11/CRMArena
mkdir -p logs/run_wrappers

RUN_NAME="general_runtime_external_conf_5_node_$(date +%Y%m%d_%H%M)"
nohup bash -lc '
  cd /work/hdd/bgtb/acheng11/CRMArena
  module purge >/dev/null 2>&1 || true
  module load gcc-native
  module load cudatoolkit/25.5_12.9
  module load python/miniforge3_pytorch/2.10.0
  source .venv-crm-modern/bin/activate
  QWEN_BASE_URL=http://127.0.0.1:8001/v1 \
  QWEN_MODEL=openai/Qwen3.5-35B-A3B \
  AGENT_STRATEGY=general_dsl \
  USE_EXTERNAL_ROUTER_DSL=true \
  REGULAR_EXTERNAL_TASKS_CSV=knowledge_qa,named_entity_disambiguation \
  CONFIDENTIALITY_TASKS_CSV=private_customer_information,internal_operation_data,confidential_company_knowledge \
  MAX_TASKS_PER_CATEGORY=8 \
  INTERACTIVE=true \
  MAX_TURNS=20 \
  MAX_USER_TURNS=10 \
  AGENT_MAX_TOKENS=2500 \
  KNOWLEDGE_QA_DSL_EXTRACTOR_MAX_TOKENS=1800 \
  KNOWLEDGE_QA_DSL_DISABLE_THINKING=true \
  NED_DSL_EXTRACTOR_MAX_TOKENS=1600 \
  NED_DSL_DISABLE_THINKING=true \
  EXTERNAL_ROUTER_MAX_TOKENS=900 \
  EXTERNAL_ROUTER_DISABLE_THINKING=true \
  MAX_VERIFIER_RETRIES=3 \
  ROUTING_MODE=none \
  SCAFFOLD_MODE=none \
  CRMARENA_VENV=/work/hdd/bgtb/acheng11/CRMArena/.venv-crm-modern \
  PYTHON_BIN="$(command -v python)" \
  RUN_TAG='"$RUN_NAME"' \
  ./run_tasks_crmarena_pro_external_full.sh
' > "logs/run_wrappers/${RUN_NAME}.log" 2>&1 < /dev/null &

WRAPPER_PID=$!
echo "Started wrapper PID: ${WRAPPER_PID}"
echo "Log: /work/hdd/bgtb/acheng11/CRMArena/logs/run_wrappers/${RUN_NAME}.log"
echo "Check running: ps -fp ${WRAPPER_PID}; pgrep -af 'run_tasks_crmarena_pro|run_tasks.py|${RUN_NAME}'"
echo "Stop wrapper/process group: kill -- -${WRAPPER_PID} || kill ${WRAPPER_PID}"
```


kill a job with
kill -- -WRAPPER_PID

## OpenRouter User/Judge Smoke Tests

These commands keep the agent on the local Qwen vLLM server, but run the simulated user and evaluator through OpenRouter. Set `OPENROUTER_API_KEY` before running.

The default OpenRouter user/judge model is `openai/gpt-4o-2024-11-20`, matching the GPT-4o version listed in the CRMArena-Pro paper's model specification. For a cheap plumbing test, explicitly override `OPENROUTER_DEFAULT_MODEL`, `JUDGE_MODEL`, and `USER_MODEL` to a free model.

### One-Task OpenRouter GPT-4o User/Judge Smoke Test

```bash
cd /work/hdd/bgtb/acheng11/CRMArena
mkdir -p logs/run_wrappers
export OPENROUTER_API_KEY="sk-or-v1-..."

RUN_NAME="openrouter_gpt4o_user_judge_smoke_$(date +%Y%m%d_%H%M)"
nohup bash -lc '
  cd /work/hdd/bgtb/acheng11/CRMArena
  module purge >/dev/null 2>&1 || true
  module load gcc-native
  module load cudatoolkit/25.5_12.9
  module load python/miniforge3_pytorch/2.10.0
  source .venv-crm-modern/bin/activate
  QWEN_BASE_URL=http://127.0.0.1:8001/v1 \
  QWEN_MODEL=openai/Qwen3.5-35B-A3B \
  AGENT_PROVIDER=openai \
  AGENT_STRATEGY=general_dsl \
  JUDGE_PROVIDER=openrouter \
  USER_PROVIDER=openrouter \
  JUDGE_MODEL="${JUDGE_MODEL:-openai/gpt-4o-2024-11-20}" \
  USER_MODEL="${USER_MODEL:-openai/gpt-4o-2024-11-20}" \
  OPENROUTER_API_KEY='"$OPENROUTER_API_KEY"' \
  TASKS_CSV=knowledge_qa \
  ORG_TYPES_CSV=original \
  MAX_TASKS_PER_CATEGORY=1 \
  INTERACTIVE=true \
  CRMARENA_VENV=/work/hdd/bgtb/acheng11/CRMArena/.venv-crm-modern \
  PYTHON_BIN="$(command -v python)" \
  RUN_TAG='"$RUN_NAME"' \
  ./run_tasks_crmarena_pro.sh
' > "logs/run_wrappers/${RUN_NAME}.log" 2>&1 < /dev/null &

WRAPPER_PID=$!
echo "Started wrapper PID: ${WRAPPER_PID}"
echo "Log: /work/hdd/bgtb/acheng11/CRMArena/logs/run_wrappers/${RUN_NAME}.log"
echo "Stop wrapper/process group: kill -- -${WRAPPER_PID} || kill ${WRAPPER_PID}"
```

### Full External Suite With OpenRouter GPT-4o User/Judge

```bash
cd /work/hdd/bgtb/acheng11/CRMArena
mkdir -p logs/run_wrappers
export OPENROUTER_API_KEY="sk-or-v1-..."

RUN_NAME="general_runtime_external_openrouter_gpt4o_user_judge_$(date +%Y%m%d_%H%M)"
nohup bash -lc '
  cd /work/hdd/bgtb/acheng11/CRMArena
  module purge >/dev/null 2>&1 || true
  module load gcc-native
  module load cudatoolkit/25.5_12.9
  module load python/miniforge3_pytorch/2.10.0
  source .venv-crm-modern/bin/activate
  QWEN_BASE_URL=http://127.0.0.1:8001/v1 \
  QWEN_MODEL=openai/Qwen3.5-35B-A3B \
  AGENT_PROVIDER=openai \
  AGENT_STRATEGY=general_dsl \
  JUDGE_PROVIDER=openrouter \
  USER_PROVIDER=openrouter \
  JUDGE_MODEL="${JUDGE_MODEL:-openai/gpt-4o-2024-11-20}" \
  USER_MODEL="${USER_MODEL:-openai/gpt-4o-2024-11-20}" \
  OPENROUTER_API_KEY='"$OPENROUTER_API_KEY"' \
  REGULAR_EXTERNAL_TASKS_CSV=knowledge_qa,named_entity_disambiguation \
  CONFIDENTIALITY_TASKS_CSV=private_customer_information,internal_operation_data,confidential_company_knowledge \
  MAX_TASKS_PER_CATEGORY=0 \
  INTERACTIVE=true \
  MAX_TURNS=20 \
  MAX_USER_TURNS=10 \
  AGENT_MAX_TOKENS=2500 \
  CRMARENA_VENV=/work/hdd/bgtb/acheng11/CRMArena/.venv-crm-modern \
  PYTHON_BIN="$(command -v python)" \
  RUN_TAG='"$RUN_NAME"' \
  ./run_tasks_crmarena_pro_external_full.sh
' > "logs/run_wrappers/${RUN_NAME}.log" 2>&1 < /dev/null &

WRAPPER_PID=$!
echo "Started wrapper PID: ${WRAPPER_PID}"
echo "Log: /work/hdd/bgtb/acheng11/CRMArena/logs/run_wrappers/${RUN_NAME}.log"
echo "Stop wrapper/process group: kill -- -${WRAPPER_PID} || kill ${WRAPPER_PID}"
```

### Cheap Free-Model Plumbing Override

Use this only for checking that OpenRouter plumbing works. Do not use it for comparable benchmark reporting.

```bash
OPENROUTER_DEFAULT_MODEL=nvidia/nemotron-3-ultra-550b-a55b:free \
JUDGE_PROVIDER=openrouter \
JUDGE_MODEL=nvidia/nemotron-3-ultra-550b-a55b:free \
USER_PROVIDER=openrouter \
USER_MODEL=nvidia/nemotron-3-ultra-550b-a55b:free
```

The Python harness normalizes these to OpenRouter/LiteLLM format.

## CLI Agent Baseline Runs

These commands benchmark a CLI-hosted agent through the CRMArena harness. They are intended for raw model-agent baselines, so they use:

- `AGENT_STRATEGY=react`
- no symbolic DSL routing
- no syntactic verifier
- no working memory / clipboards
- standard interactive loop limits: `MAX_TURNS=20`, `MAX_USER_TURNS=10`
- stateless CLI calls through the adapter:
  - Codex: `codex exec --ephemeral`
  - Claude: `claude --print --no-session-persistence`

Credentials and CLI model defaults are loaded from:

```bash
/work/hdd/bgtb/acheng11/.model-configs.txt
```

### Codex CLI + OpenRouter GPT-4o User/Judge, 2 Tasks Each

Runs one task from each external/confidentiality category:

- `original/knowledge_qa`
- `original/named_entity_disambiguation`
- `b2b/private_customer_information`
- `b2b/internal_operation_data`
- `b2b/confidential_company_knowledge`

```bash
cd /work/hdd/bgtb/acheng11/CRMArena
mkdir -p logs/run_wrappers

RUN_NAME="codex_cli_openrouter_gpt4o_external_conf_2each_$(date +%Y%m%d_%H%M)"
PID_FILE="logs/run_wrappers/${RUN_NAME}.pid"
PGID_FILE="logs/run_wrappers/${RUN_NAME}.pgid"
setsid nohup bash -lc '
  cd /work/hdd/bgtb/acheng11/CRMArena
  echo "$$" > "'"$PID_FILE"'"
  ps -o pgid= -p "$$" | tr -d " " > "'"$PGID_FILE"'"
  module purge >/dev/null 2>&1 || true
  module load gcc-native
  module load cudatoolkit/25.5_12.9
  module load python/miniforge3_pytorch/2.10.0
  source .venv-crm-modern/bin/activate
  set -a
  source /work/hdd/bgtb/acheng11/.model-configs.txt
  set +a
  MODEL_CONFIG_FILE=/dev/null \
  QWEN_MODEL=default \
  QWEN_BASE_URL= \
  AGENT_PROVIDER=codex_cli \
  CODEX_CLI_MODEL="${CODEX_CLI_MODEL:-default}" \
  AGENT_REASONING_MODE=default \
  AGENT_STRATEGY=react \
  JUDGE_PROVIDER=openrouter \
  USER_PROVIDER=openrouter \
  JUDGE_MODEL="${JUDGE_MODEL:-openai/gpt-4o-2024-11-20}" \
  USER_MODEL="${USER_MODEL:-openai/gpt-4o-2024-11-20}" \
  REGULAR_EXTERNAL_TASKS_CSV=knowledge_qa,named_entity_disambiguation \
  CONFIDENTIALITY_TASKS_CSV=private_customer_information,internal_operation_data,confidential_company_knowledge \
  MAX_TASKS_PER_CATEGORY=2 \
  INTERACTIVE=true \
  PRIVACY_AWARE_PROMPT=true \
  MAX_TURNS=20 \
  MAX_USER_TURNS=10 \
  AGENT_MAX_TOKENS=2500 \
  USE_SYNTACTIC_VERIFIER=false \
  USE_WORKING_MEMORY=false \
  USE_QUOTE_CLIPBOARD=false \
  USE_LEAD_CLIPBOARD=false \
  ROUTING_MODE=none \
  SCAFFOLD_MODE=none \
  SKIP_HEALTH_CHECKS=true \
  CRMARENA_VENV=/work/hdd/bgtb/acheng11/CRMArena/.venv-crm-modern \
  PYTHON_BIN="$(command -v python)" \
  RUN_TAG='"$RUN_NAME"' \
  ./run_tasks_crmarena_pro_external_full.sh
' > "logs/run_wrappers/${RUN_NAME}.log" 2>&1 < /dev/null &

for _ in $(seq 1 50); do
  [[ -s "$PID_FILE" && -s "$PGID_FILE" ]] && break
  sleep 0.1
done
WRAPPER_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
WRAPPER_PGID="$(cat "$PGID_FILE" 2>/dev/null || true)"
echo "Started wrapper PID: ${WRAPPER_PID}"
echo "Started wrapper PGID: ${WRAPPER_PGID}"
echo "Node: $(hostname)"
echo "Log: /work/hdd/bgtb/acheng11/CRMArena/logs/run_wrappers/${RUN_NAME}.log"
if [[ -n "$WRAPPER_PGID" ]]; then
  echo "Stop on this same node: kill -TERM -${WRAPPER_PGID}; sleep 5; kill -KILL -${WRAPPER_PGID}"
else
  echo "Could not read wrapper PGID. Find it with: ps -u \"$(id -u)\" -o pid,ppid,pgid,cmd | grep ${RUN_NAME}"
fi
```

To resume the same PVI result folder after deleting quota-limit rows, keep the
same `RESULT_RUN_TAG` and use a fresh `LOG_NAME`. This version explicitly
activates the CRM Arena Python environment so imports like `dotenv` resolve:

```bash
cd /work/hdd/bgtb/acheng11/CRMArena

module purge >/dev/null 2>&1 || true
module load gcc-native
module load cudatoolkit/25.5_12.9
module load python/miniforge3_pytorch/2.10.0
source .venv-crm-modern/bin/activate

set -a
source /work/hdd/bgtb/acheng11/.model-configs.txt
set +a

RESULT_RUN_TAG="claude_cli_opus_react_pvi_full_20260809_1550"
LOG_NAME="${RESULT_RUN_TAG}_resume_$(date +%Y%m%d_%H%M)"

MODEL_CONFIG_FILE=/dev/null \
AGENT_MODEL=claude_cli \
AGENT_PROVIDER=claude_cli \
CLAUDE_CONFIG_DIR=/work/hdd/bgtb/acheng11/.claude-bench \
CLAUDE_CLI_MODEL="${CLAUDE_CLI_MODEL:-claude-opus-5}" \
AGENT_REASONING_MODE=default \
AGENT_STRATEGY=react \
TASKS_CSV=policy_violation_identification \
ORG_TYPES_CSV=b2b \
JUDGE_PROVIDER=openrouter \
USER_PROVIDER=openrouter \
JUDGE_MODEL="${JUDGE_MODEL:-openai/gpt-4o-2024-11-20}" \
USER_MODEL="${USER_MODEL:-openai/gpt-4o-2024-11-20}" \
MAX_TASKS_PER_CATEGORY=0 \
INTERACTIVE=true \
PRIVACY_AWARE_PROMPT=false \
ROUTING_MODE=none \
SCAFFOLD_MODE=none \
SKIP_HEALTH_CHECKS=true \
RUN_TAG="$RESULT_RUN_TAG" \
LOG_TAG="$LOG_NAME" \
PYTHON_BIN="$(command -v python)" \
./run_tasks_crmarena_pro.sh
```

### Codex CLI + OpenRouter GPT-4o User/Judge, Full External/Confidentiality Benchmark

Runs all examples for:

- `original/knowledge_qa`
- `original/named_entity_disambiguation`
- `b2b/private_customer_information`
- `b2b/internal_operation_data`
- `b2b/confidential_company_knowledge`

This is the prompt-only privacy-aware raw ReAct baseline. It uses `AGENT_STRATEGY=react`, no symbolic DSL, no verifier, no working memory, and `PRIVACY_AWARE_PROMPT=true`.

```bash
cd /work/hdd/bgtb/acheng11/CRMArena
mkdir -p logs/run_wrappers

RESULT_RUN_TAG="codex_cli_openrouter_gpt4o_external_conf_full_20260802_2328"
RUN_NAME="${RESULT_RUN_TAG}_resume_$(date +%Y%m%d_%H%M)"
LOG_NAME="$RUN_NAME"
PID_FILE="logs/run_wrappers/${RUN_NAME}.pid"
PGID_FILE="logs/run_wrappers/${RUN_NAME}.pgid"
setsid nohup bash -lc '
  cd /work/hdd/bgtb/acheng11/CRMArena
  echo "$$" > "'"$PID_FILE"'"
  ps -o pgid= -p "$$" | tr -d " " > "'"$PGID_FILE"'"
  module purge >/dev/null 2>&1 || true
  module load gcc-native
  module load cudatoolkit/25.5_12.9
  module load python/miniforge3_pytorch/2.10.0
  source .venv-crm-modern/bin/activate
  set -a
  source /work/hdd/bgtb/acheng11/.model-configs.txt
  set +a
  MODEL_CONFIG_FILE=/dev/null \
  QWEN_MODEL=default \
  QWEN_BASE_URL= \
  AGENT_PROVIDER=codex_cli \
  CODEX_CLI_MODEL="${CODEX_CLI_MODEL:-gpt-5.6-sol}" \
  AGENT_REASONING_MODE=default \
  AGENT_STRATEGY=react \
  JUDGE_PROVIDER=openrouter \
  USER_PROVIDER=openrouter \
  JUDGE_MODEL="${JUDGE_MODEL:-openai/gpt-4o-2024-11-20}" \
  USER_MODEL="${USER_MODEL:-openai/gpt-4o-2024-11-20}" \
  REGULAR_EXTERNAL_TASKS_CSV=knowledge_qa,named_entity_disambiguation \
  CONFIDENTIALITY_TASKS_CSV=private_customer_information,internal_operation_data,confidential_company_knowledge \
  MAX_TASKS_PER_CATEGORY=0 \
  INTERACTIVE=true \
  PRIVACY_AWARE_PROMPT=true \
  MAX_TURNS=20 \
  MAX_USER_TURNS=10 \
  AGENT_MAX_TOKENS=2500 \
  USE_SYNTACTIC_VERIFIER=false \
  USE_WORKING_MEMORY=false \
  USE_QUOTE_CLIPBOARD=false \
  USE_LEAD_CLIPBOARD=false \
  ROUTING_MODE=none \
  SCAFFOLD_MODE=none \
  SKIP_HEALTH_CHECKS=true \
  CRMARENA_VENV=/work/hdd/bgtb/acheng11/CRMArena/.venv-crm-modern \
  PYTHON_BIN="$(command -v python)" \
  RUN_TAG='"$RESULT_RUN_TAG"' \
  LOG_TAG='"$LOG_NAME"' \
  ./run_tasks_crmarena_pro_external_full.sh
' > "logs/run_wrappers/${RUN_NAME}.log" 2>&1 < /dev/null &

for _ in $(seq 1 50); do
  [[ -s "$PID_FILE" && -s "$PGID_FILE" ]] && break
  sleep 0.1
done
WRAPPER_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
WRAPPER_PGID="$(cat "$PGID_FILE" 2>/dev/null || true)"
echo "Started wrapper PID: ${WRAPPER_PID}"
echo "Started wrapper PGID: ${WRAPPER_PGID}"
echo "Node: $(hostname)"
echo "Log: /work/hdd/bgtb/acheng11/CRMArena/logs/run_wrappers/${RUN_NAME}.log"
if [[ -n "$WRAPPER_PGID" ]]; then
  echo "Stop on this same node: kill -TERM -${WRAPPER_PGID}; sleep 5; kill -KILL -${WRAPPER_PGID}"
else
  echo "Could not read wrapper PGID. Find it with: ps -u \"$(id -u)\" -o pid,ppid,pgid,cmd | grep ${RUN_NAME}"
fi
```

### Claude CLI Opus + OpenRouter GPT-4o User/Judge, Full External/Confidentiality Benchmark

Runs all examples for:

- `original/knowledge_qa`
- `original/named_entity_disambiguation`
- `b2b/private_customer_information`
- `b2b/internal_operation_data`
- `b2b/confidential_company_knowledge`

This is the prompt-only privacy-aware raw ReAct baseline for Claude CLI. It uses `AGENT_STRATEGY=react`, no symbolic DSL, no verifier, no working memory, and `PRIVACY_AWARE_PROMPT=true`.

```bash
cd /work/hdd/bgtb/acheng11/CRMArena
mkdir -p logs/run_wrappers

RESULT_RUN_TAG="claude_cli_opus_openrouter_gpt4o_external_conf_full_20260802_2346"
RUN_NAME="${RESULT_RUN_TAG}_resume_$(date +%Y%m%d_%H%M)"
LOG_NAME="$RUN_NAME"
PID_FILE="logs/run_wrappers/${RUN_NAME}.pid"
PGID_FILE="logs/run_wrappers/${RUN_NAME}.pgid"
setsid nohup bash -lc '
  cd /work/hdd/bgtb/acheng11/CRMArena
  echo "$$" > "'"$PID_FILE"'"
  ps -o pgid= -p "$$" | tr -d " " > "'"$PGID_FILE"'"
  module purge >/dev/null 2>&1 || true
  module load gcc-native
  module load cudatoolkit/25.5_12.9
  module load python/miniforge3_pytorch/2.10.0
  source .venv-crm-modern/bin/activate
  set -a
  source /work/hdd/bgtb/acheng11/.model-configs.txt
  set +a
  MODEL_CONFIG_FILE=/dev/null \
  QWEN_MODEL=default \
  QWEN_BASE_URL= \
  AGENT_PROVIDER=claude_cli \
  CLAUDE_CLI_MODEL="${CLAUDE_CLI_MODEL:-claude-opus-5}" \
  AGENT_REASONING_MODE=default \
  AGENT_STRATEGY=react \
  JUDGE_PROVIDER=openrouter \
  USER_PROVIDER=openrouter \
  JUDGE_MODEL="${JUDGE_MODEL:-openai/gpt-4o-2024-11-20}" \
  USER_MODEL="${USER_MODEL:-openai/gpt-4o-2024-11-20}" \
  REGULAR_EXTERNAL_TASKS_CSV=knowledge_qa,named_entity_disambiguation \
  CONFIDENTIALITY_TASKS_CSV=private_customer_information,internal_operation_data,confidential_company_knowledge \
  MAX_TASKS_PER_CATEGORY=0 \
  INTERACTIVE=true \
  PRIVACY_AWARE_PROMPT=true \
  MAX_TURNS=20 \
  MAX_USER_TURNS=10 \
  AGENT_MAX_TOKENS=2500 \
  USE_SYNTACTIC_VERIFIER=false \
  USE_WORKING_MEMORY=false \
  USE_QUOTE_CLIPBOARD=false \
  USE_LEAD_CLIPBOARD=false \
  ROUTING_MODE=none \
  SCAFFOLD_MODE=none \
  SKIP_HEALTH_CHECKS=true \
  CRMARENA_VENV=/work/hdd/bgtb/acheng11/CRMArena/.venv-crm-modern \
  PYTHON_BIN="$(command -v python)" \
  RUN_TAG='"$RESULT_RUN_TAG"' \
  LOG_TAG='"$LOG_NAME"' \
  ./run_tasks_crmarena_pro_external_full.sh
' > "logs/run_wrappers/${RUN_NAME}.log" 2>&1 < /dev/null &

for _ in $(seq 1 50); do
  [[ -s "$PID_FILE" && -s "$PGID_FILE" ]] && break
  sleep 0.1
done
WRAPPER_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
WRAPPER_PGID="$(cat "$PGID_FILE" 2>/dev/null || true)"
echo "Started wrapper PID: ${WRAPPER_PID}"
echo "Started wrapper PGID: ${WRAPPER_PGID}"
echo "Node: $(hostname)"
echo "Log: /work/hdd/bgtb/acheng11/CRMArena/logs/run_wrappers/${RUN_NAME}.log"
if [[ -n "$WRAPPER_PGID" ]]; then
  echo "Stop on this same node: kill -TERM -${WRAPPER_PGID}; sleep 5; kill -KILL -${WRAPPER_PGID}"
else
  echo "Could not read wrapper PGID. Find it with: ps -u \"$(id -u)\" -o pid,ppid,pgid,cmd | grep ${RUN_NAME}"
fi
```

### CLI Baseline Customization Notes

Model/account config:

```bash
# Preferred place to change CLI auth/model defaults:
nano /work/hdd/bgtb/acheng11/.model-configs.txt

# Typical entries:
CODEX_HOME=/work/hdd/bgtb/acheng11/.codex-bench
CLAUDE_CONFIG_DIR=/work/hdd/bgtb/acheng11/.claude-bench
CODEX_CLI_MODEL=default
CLAUDE_CLI_MODEL=sonnet
AGENT_REASONING_MODE=default
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_DEFAULT_MODEL=openai/gpt-4o-2024-11-20
```

Switch Codex CLI to Claude CLI:

```bash
AGENT_PROVIDER=claude_cli
QWEN_MODEL=default
```

Set OpenRouter user/judge explicitly to the paper-aligned GPT-4o model:

```bash
JUDGE_PROVIDER=openrouter \
JUDGE_MODEL=openai/gpt-4o-2024-11-20 \
USER_PROVIDER=openrouter \
USER_MODEL=openai/gpt-4o-2024-11-20
```

Run the symbolic/general runtime instead of raw ReAct:

```bash
AGENT_STRATEGY=general_dsl
```

For raw frontier-agent baselines, keep `AGENT_STRATEGY=react`. That is closest to the benchmark's normal agent setup: the model sees the CRMArena Salesforce prompt/schema and must emit `Thought` plus `<execute>` or `<respond>` actions. The CLI adapter itself is stateless across calls, but CRMArena still passes the benchmark-visible conversation history within a task.

External interactive runs now default to `PRIVACY_AWARE_PROMPT=true`, which enables the repo's privacy-aware external interactive system prompt for raw ReAct baselines. Set `PRIVACY_AWARE_PROMPT=false` for a non-privacy-prompt ablation.

Each result JSON item includes top-level `time_to_resolution_seconds`, `task_wall_time_seconds`, `model_calls`, `env_steps`, `usage`, `total_cost`, and aggregate token totals when the model client reports them. CLI providers currently expose estimated token counts and `cost=null`; OpenRouter/LiteLLM may provide real usage and cost depending on provider response metadata.

Reasoning/thinking comparability:

- `AGENT_REASONING_MODE=default` is the intended baseline: the adapter passes no reasoning/effort override and lets the provider/model use its normal default.
- Codex CLI runs through `codex exec --ephemeral`; with `CODEX_CLI_MODEL=default`, the adapter does not pass `--model` and lets the authenticated Codex account choose its default supported model.
- Claude CLI runs through `claude --print --no-session-persistence`; the adapter does not pass `--effort` when `AGENT_REASONING_MODE=default`.
- For Claude-only ablations, set `AGENT_REASONING_MODE=low`, `medium`, `high`, `xhigh`, or `max`; the adapter maps that to `claude --effort`.
- The CRMArena harness does not receive hidden reasoning separately. It only parses the visible final CLI output.
- `openai/gpt-4o-2024-11-20` is the default OpenRouter user/judge model for benchmark-like runs. `nvidia/nemotron-3-ultra-550b-a55b:free` is only for plumbing smoke tests. `openrouter/free` randomly routes across free providers and can fail when one upstream provider is unhealthy.
- OpenRouter free providers can return transient capacity errors such as `ResourceExhausted`. The harness retries OpenRouter calls by default with `OPENROUTER_RETRY_ATTEMPTS=4` and `OPENROUTER_RETRY_BASE_SLEEP_SECONDS=8`; override those for faster failure or longer waits.

Scale knobs:

```bash
# 1 each, smoke:
MAX_TASKS_PER_CATEGORY=1

# 25 each, small benchmark:
MAX_TASKS_PER_CATEGORY=25

# full task categories:
MAX_TASKS_PER_CATEGORY=0
```

Stopping jobs:

- Run the stop command from the same node where the wrapper started. Linux PIDs are node-local.
- If the wrapper was launched inside a Slurm allocation, SSH back to that compute node or cancel the Slurm job/step.
- The `setsid` wrapper makes `PGID` equal to a real process group, so `kill -TERM -${WRAPPER_PGID}` stops the wrapper plus child Python/Codex/Claude processes.

## Claude CLI General DSL Smoke Test

This runs Claude through the shared `general_dsl` symbolic runtime, not raw
ReAct. It uses Claude's configured/default CLI model and default reasoning
behavior:

- `CLAUDE_CLI_MODEL=default` means the adapter does not pass `--model`.
- `AGENT_REASONING_MODE=default` means the adapter does not pass `--effort`.

The task order is:

1. `b2b/private_customer_information`
2. `b2b/internal_operation_data`
3. `b2b/confidential_company_knowledge`
4. `original/knowledge_qa`
5. `original/named_entity_disambiguation`

Change `MAX_TASKS_PER_CATEGORY=8` to `0` for the full benchmark.

```bash
cd /work/hdd/bgtb/acheng11/CRMArena
mkdir -p logs/run_wrappers

MAX_TASKS_PER_CATEGORY=8
RESULT_RUN_TAG="claude_cli_general_dsl_external_conf_${MAX_TASKS_PER_CATEGORY}each_$(date +%Y%m%d_%H%M)"
RUN_NAME="$RESULT_RUN_TAG"
LOG_NAME="$RUN_NAME"
PID_FILE="logs/run_wrappers/${RUN_NAME}.pid"
PGID_FILE="logs/run_wrappers/${RUN_NAME}.pgid"

setsid nohup bash -lc '
  cd /work/hdd/bgtb/acheng11/CRMArena
  echo "$$" > "'"$PID_FILE"'"
  ps -o pgid= -p "$$" | tr -d " " > "'"$PGID_FILE"'"
  module purge >/dev/null 2>&1 || true
  module load gcc-native
  module load cudatoolkit/25.5_12.9
  module load python/miniforge3_pytorch/2.10.0
  source .venv-crm-modern/bin/activate
  set -a
  source /work/hdd/bgtb/acheng11/.model-configs.txt
  set +a

  run_general_dsl_task() {
    local org_type="$1"
    local task_name="$2"
    echo "============================================================"
    echo "Claude general_dsl: org=${org_type} task=${task_name}"
    echo "============================================================"
    MODEL_CONFIG_FILE=/dev/null \
    AGENT_MODEL=claude_cli \
    AGENT_PROVIDER=claude_cli \
    AGENT_BASE_URL= \
    AGENT_API_KEY=dummy \
    CLAUDE_CLI_MODEL="${CLAUDE_CLI_MODEL:-default}" \
    AGENT_REASONING_MODE=default \
    AGENT_STRATEGY=general_dsl \
    JUDGE_PROVIDER=openrouter \
    USER_PROVIDER=openrouter \
    JUDGE_MODEL="${JUDGE_MODEL:-openai/gpt-4o-2024-11-20}" \
    USER_MODEL="${USER_MODEL:-openai/gpt-4o-2024-11-20}" \
    TASKS_CSV="${task_name}" \
    ORG_TYPES_CSV="${org_type}" \
    MAX_TASKS_PER_CATEGORY='"$MAX_TASKS_PER_CATEGORY"' \
    INTERACTIVE=true \
    PRIVACY_AWARE_PROMPT=true \
    MAX_TURNS=20 \
    MAX_USER_TURNS=10 \
    AGENT_MAX_TOKENS=2500 \
    USE_EXTERNAL_ROUTER_DSL=true \
    USE_SYNTACTIC_VERIFIER=false \
    USE_WORKING_MEMORY=false \
    USE_QUOTE_CLIPBOARD=false \
    USE_LEAD_CLIPBOARD=false \
    ROUTING_MODE=none \
    SCAFFOLD_MODE=none \
    SKIP_HEALTH_CHECKS=true \
    CRMARENA_VENV=/work/hdd/bgtb/acheng11/CRMArena/.venv-crm-modern \
    PYTHON_BIN="$(command -v python)" \
    RUN_TAG='"$RESULT_RUN_TAG"' \
    LOG_TAG='"$LOG_NAME"' \
    ./run_tasks_crmarena_pro.sh
  }

  run_general_dsl_task b2b private_customer_information
  run_general_dsl_task b2b internal_operation_data
  run_general_dsl_task b2b confidential_company_knowledge
  run_general_dsl_task original knowledge_qa
  run_general_dsl_task original named_entity_disambiguation
' > "logs/run_wrappers/${RUN_NAME}.log" 2>&1 < /dev/null &

for _ in $(seq 1 50); do
  [[ -s "$PID_FILE" && -s "$PGID_FILE" ]] && break
  sleep 0.1
done
WRAPPER_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
WRAPPER_PGID="$(cat "$PGID_FILE" 2>/dev/null || true)"
echo "Started wrapper PID: ${WRAPPER_PID}"
echo "Started wrapper PGID: ${WRAPPER_PGID}"
echo "Node: $(hostname)"
echo "Log: /work/hdd/bgtb/acheng11/CRMArena/logs/run_wrappers/${RUN_NAME}.log"
if [[ -n "$WRAPPER_PGID" ]]; then
  echo "Stop on this same node: kill -TERM -${WRAPPER_PGID}; sleep 5; kill -KILL -${WRAPPER_PGID}"
else
  echo "Could not read wrapper PGID. Find it with: ps -u \"$(id -u)\" -o pid,ppid,pgid,cmd | grep ${RUN_NAME}"
fi
```

## Slurm Claude General DSL Benchmark

This submits a Slurm job that runs Claude CLI through the shared
`general_dsl` runtime in this order:

1. `b2b/internal_operation_data`
2. `b2b/private_customer_information`
3. `original/named_entity_disambiguation`
4. `original/knowledge_qa`
5. `b2b/confidential_company_knowledge`

Outputs are written under:

```bash
/work/hdd/bgtb/acheng11/CRMArena/results/claude-bench-results/<tag>
/work/hdd/bgtb/acheng11/CRMArena/logs/claude-bench-results/<tag>
```

Default 2-task smoke test:

```bash
cd /work/hdd/bgtb/acheng11/CRMArena
mkdir -p logs/claude-bench-results/slurm

sbatch -A bgtb-dtai-gh \
  scripts/deltaai_claude_general_dsl_benchmark.sbatch
```

2-task smoke test with an explicit tag:

```bash
cd /work/hdd/bgtb/acheng11/CRMArena
mkdir -p logs/claude-bench-results/slurm

sbatch -A bgtb-dtai-gh \
  scripts/deltaai_claude_general_dsl_benchmark.sbatch \
  smoke claude_general_dsl_smoke_v1
```

Full benchmark with an explicit tag:

```bash
cd /work/hdd/bgtb/acheng11/CRMArena
mkdir -p logs/claude-bench-results/slurm

sbatch -A bgtb-dtai-gh \
  scripts/deltaai_claude_general_dsl_benchmark.sbatch \
  full claude_general_dsl_full_v1
```

You can also override knobs inline:

```bash
MAX_TASKS_PER_CATEGORY=25 \
CLAUDE_CLI_MODEL=default \
AGENT_REASONING_MODE=default \
sbatch -A bgtb-dtai-gh \
  scripts/deltaai_claude_general_dsl_benchmark.sbatch \
  smoke claude_general_dsl_25each_v1
```

The script sources `/work/hdd/bgtb/acheng11/.model-configs.txt` for
`CLAUDE_CONFIG_DIR` and `OPENROUTER_API_KEY`. By default it uses
`openai/gpt-4o-2024-11-20` through OpenRouter for both the simulated user and
judge, matching the benchmark-style evaluator setup we have been using.



```
cd /work/hdd/bgtb/acheng11/CRMArena

RESUME_TAG="claude_general_dsl_full_v1_resume_kqa_cck_$(date +%Y%m%d_%H%M)"

sbatch --export=ALL,\
BENCH_MODE=full,\
MAX_TASKS_PER_CATEGORY=0,\
RUN_TAG="$RESUME_TAG",\
RESULT_ROOT=/work/hdd/bgtb/acheng11/CRMArena/results/claude-bench-results/claude_general_dsl_full_v1,\
LOG_ROOT=/work/hdd/bgtb/acheng11/CRMArena/logs/claude-bench-results/$RESUME_TAG \
scripts/deltaai_claude_general_dsl_benchmark.sbatch full "$RESUME_TAG"

```


cd /work/hdd/bgtb/acheng11/CRMArena

module purge >/dev/null 2>&1 || true
module load gcc-native
module load cudatoolkit/25.5_12.9
module load python/miniforge3_pytorch/2.10.0
source .venv-crm-modern/bin/activate

RUN_TAG="claude_internal_full_$(date +%Y%m%d_%H%M)"

TASKS_CSV=wrong_stage_rectification \
ROUTING_MODE=none \
SCAFFOLD_MODE=none \
ORG_TYPES_CSV=b2b \
AGENT_STRATEGY=general_dsl \
AGENT_MODEL=claude_cli \
AGENT_PROVIDER=claude_cli \
CLAUDE_CONFIG_DIR=/work/hdd/bgtb/acheng11/.claude-bench \
CLAUDE_CLI_MODEL=default \
JUDGE_PROVIDER=openrouter \
USER_PROVIDER=openrouter \
JUDGE_MODEL=openai/gpt-4o-2024-11-20 \
USER_MODEL=openai/gpt-4o-2024-11-20 \
MAX_TASKS_PER_CATEGORY=0 \
MAX_JOBS=1 \
RUN_TAG="$RUN_TAG" \
LOG_TAG="$RUN_TAG" \
CRMARENA_VENV=/work/hdd/bgtb/acheng11/CRMArena/.venv-crm-modern \
PYTHON_BIN="$(command -v python)" \
./run_tasks_crmarena_pro.sh




cd /work/hdd/bgtb/acheng11/CRMArena
mkdir -p logs/run_wrappers

RESULT_RUN_TAG="claude_internal_full_20260805_2240"
LOG_TAG="${RESULT_RUN_TAG}_resume_$(date +%Y%m%d_%H%M)"
WRAPPER_LOG="logs/run_wrappers/${LOG_TAG}.log"

nohup bash -lc '
cd /work/hdd/bgtb/acheng11/CRMArena
module purge >/dev/null 2>&1 || true
module load gcc-native
module load cudatoolkit/25.5_12.9
module load python/miniforge3_pytorch/2.10.0
source .venv-crm-modern/bin/activate

TASKS_CSV=wrong_stage_rectification \
ROUTING_MODE=none \
SCAFFOLD_MODE=none \
ORG_TYPES_CSV=b2b \
AGENT_STRATEGY=general_dsl \
AGENT_MODEL=claude_cli \
AGENT_PROVIDER=claude_cli \
CLAUDE_CONFIG_DIR=/work/hdd/bgtb/acheng11/.claude-bench \
CLAUDE_CLI_MODEL=default \
JUDGE_PROVIDER=openrouter \
USER_PROVIDER=openrouter \
JUDGE_MODEL=openai/gpt-4o-2024-11-20 \
USER_MODEL=openai/gpt-4o-2024-11-20 \
MAX_TASKS_PER_CATEGORY=0 \
MAX_JOBS=1 \
RUN_TAG="'"$RESULT_RUN_TAG"'" \
LOG_TAG="'"$LOG_TAG"'" \
CRMARENA_VENV=/work/hdd/bgtb/acheng11/CRMArena/.venv-crm-modern \
PYTHON_BIN="$(command -v python)" \
./run_tasks_crmarena_pro.sh
' > "$WRAPPER_LOG" 2>&1 < /dev/null &

echo "Wrapper PID: $!"
echo "Result folder: /work/hdd/bgtb/acheng11/CRMArena/results/b2b_multi-turn/general_dsl_claude_cli_${RESULT_RUN_TAG}_noverifier_nowm"
echo "New task log: /work/hdd/bgtb/acheng11/CRMArena/logs/b2b_multi-turn/general_dsl_claude_cli_${LOG_TAG}_noverifier_nowm/
run_wrong_stage_rectification_default.log"
echo "Wrapper log: /work/hdd/bgtb/acheng11/CRMArena/${WRAPPER_LOG}"
```

### Claude CLI Opus ReAct Baseline, Full Policy Violation Identification Benchmark

Run this from a login node. This is the corrected raw Claude ReAct baseline for
`policy_violation_identification`; it does not run `sales_cycle_understanding`,
does not use the symbolic runtime, and does not require a local vLLM server.

```bash
cd /work/hdd/bgtb/acheng11/CRMArena
mkdir -p logs/run_wrappers

RESULT_RUN_TAG="claude_cli_opus_react_pvi_full_$(date +%Y%m%d_%H%M)"
RUN_NAME="$RESULT_RUN_TAG"
LOG_NAME="$RUN_NAME"
PID_FILE="logs/run_wrappers/${RUN_NAME}.pid"
PGID_FILE="logs/run_wrappers/${RUN_NAME}.pgid"

setsid nohup bash -lc '
  cd /work/hdd/bgtb/acheng11/CRMArena
  echo "$$" > "'"$PID_FILE"'"
  ps -o pgid= -p "$$" | tr -d " " > "'"$PGID_FILE"'"
  module purge >/dev/null 2>&1 || true
  module load gcc-native
  module load cudatoolkit/25.5_12.9
  module load python/miniforge3_pytorch/2.10.0
  source .venv-crm-modern/bin/activate
  set -a
  source /work/hdd/bgtb/acheng11/.model-configs.txt
  set +a

  MODEL_CONFIG_FILE=/dev/null \
  AGENT_MODEL=claude_cli \
  AGENT_PROVIDER=claude_cli \
  CLAUDE_CONFIG_DIR=/work/hdd/bgtb/acheng11/.claude-bench \
  CLAUDE_CLI_MODEL="${CLAUDE_CLI_MODEL:-claude-opus-5}" \
  AGENT_REASONING_MODE=default \
  AGENT_STRATEGY=react \
  TASKS_CSV=policy_violation_identification \
  ORG_TYPES_CSV=b2b \
  JUDGE_PROVIDER=openrouter \
  USER_PROVIDER=openrouter \
  JUDGE_MODEL="${JUDGE_MODEL:-openai/gpt-4o-2024-11-20}" \
  USER_MODEL="${USER_MODEL:-openai/gpt-4o-2024-11-20}" \
  MAX_TASKS_PER_CATEGORY=0 \
  INTERACTIVE=true \
  PRIVACY_AWARE_PROMPT=false \
  MAX_TURNS=20 \
  MAX_USER_TURNS=10 \
  AGENT_MAX_TOKENS=2500 \
  USE_SYNTACTIC_VERIFIER=false \
  USE_WORKING_MEMORY=false \
  USE_QUOTE_CLIPBOARD=false \
  USE_LEAD_CLIPBOARD=false \
  ROUTING_MODE=none \
  SCAFFOLD_MODE=none \
  SKIP_HEALTH_CHECKS=true \
  CRMARENA_VENV=/work/hdd/bgtb/acheng11/CRMArena/.venv-crm-modern \
  PYTHON_BIN="$(command -v python)" \
  RUN_TAG='"$RESULT_RUN_TAG"' \
  LOG_TAG='"$LOG_NAME"' \
  ./run_tasks_crmarena_pro.sh
' > "logs/run_wrappers/${RUN_NAME}.log" 2>&1 < /dev/null &

for _ in $(seq 1 50); do
  [[ -s "$PID_FILE" && -s "$PGID_FILE" ]] && break
  sleep 0.1
done
WRAPPER_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
WRAPPER_PGID="$(cat "$PGID_FILE" 2>/dev/null || true)"
echo "Started wrapper PID: ${WRAPPER_PID}"
echo "Started wrapper PGID: ${WRAPPER_PGID}"
echo "Node: $(hostname)"
echo "Result folder: /work/hdd/bgtb/acheng11/CRMArena/results/b2b_multi-turn/react_claude_cli_${RESULT_RUN_TAG}_noverifier_nowm"
echo "Task log: /work/hdd/bgtb/acheng11/CRMArena/logs/b2b_multi-turn/react_claude_cli_${LOG_NAME}_noverifier_nowm/run_policy_violation_identification_default.log"
echo "Wrapper log: /work/hdd/bgtb/acheng11/CRMArena/logs/run_wrappers/${RUN_NAME}.log"
if [[ -n "$WRAPPER_PGID" ]]; then
  echo "Stop on this same node: kill -TERM -${WRAPPER_PGID}; sleep 5; kill -KILL -${WRAPPER_PGID}"
else
  echo "Could not read wrapper PGID. Find it with: ps -u \"$(id -u)\" -o pid,ppid,pgid,cmd | grep ${RUN_NAME}"
fi
```

### Rerun API/CLI Stub Rows Into an Existing Result Folder

Use this when a finished benchmark has a small number of provider/quota/API
stub rows. It removes and reruns only the requested task IDs, writes the new
rows back into the original result JSON, and writes fresh logs under a new
`LOG_TAG`.

Current useful presets:

- `kqa_react_api_stubs`: Claude ReAct KQA task `80`.
- `pvi_react_api_stubs`: Claude ReAct PVI tasks `1427,1428,1429`.
- `pvi_dsl_api_stubs`: Claude General DSL PVI tasks `1399,1403`.

```bash
cd /work/hdd/bgtb/acheng11/CRMArena
mkdir -p logs/run_wrappers
PRESET="pvi_dsl_api_stubs"

RUN_NAME="rerun_${PRESET}_$(date +%Y%m%d_%H%M)"
PID_FILE="logs/run_wrappers/${RUN_NAME}.pid"
PGID_FILE="logs/run_wrappers/${RUN_NAME}.pgid"

setsid nohup bash -lc '
  cd /work/hdd/bgtb/acheng11/CRMArena
  echo "$$" > "'"$PID_FILE"'"
  ps -o pgid= -p "$$" | tr -d " " > "'"$PGID_FILE"'"
  module purge >/dev/null 2>&1 || true
  module load gcc-native
  module load cudatoolkit/25.5_12.9
  module load python/miniforge3_pytorch/2.10.0
  source .venv-crm-modern/bin/activate
  PRESET="'"$PRESET"'" scripts/rerun_missing_wsr_react_direct.sh
' > "logs/run_wrappers/${RUN_NAME}.log" 2>&1 < /dev/null &

for _ in $(seq 1 50); do
  [[ -s "$PID_FILE" && -s "$PGID_FILE" ]] && break
  sleep 0.1
done
WRAPPER_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
WRAPPER_PGID="$(cat "$PGID_FILE" 2>/dev/null || true)"
echo "Started wrapper PID: ${WRAPPER_PID}"
echo "Started wrapper PGID: ${WRAPPER_PGID}"
echo "Wrapper log: /work/hdd/bgtb/acheng11/CRMArena/logs/run_wrappers/${RUN_NAME}.log"
if [[ -n "$WRAPPER_PGID" ]]; then
  echo "Stop on this same node: kill -TERM -${WRAPPER_PGID}; sleep 5; kill -KILL -${WRAPPER_PGID}"
else
  echo "Could not read wrapper PGID. Find it with: ps -u \"$(id -u)\" -o pid,ppid,pgid,cmd | grep ${RUN_NAME}"
fi
```

To rerun a different current exclusion, only change `PRESET`:

```bash
PRESET="kqa_react_api_stubs"
PRESET="pvi_dsl_api_stubs"
```

For a future custom exclusion, call the same script with explicit fields. Do
not copy this block as-is; replace every placeholder first:

```bash
# TASKS_CSV=<task_family> \
# TASK_IDS_CSV=<comma_separated_task_ids> \
# RUN_TAG=<existing_result_run_tag> \
# ORG_TYPES_CSV=<b2b_or_original> \
# AGENT_STRATEGY=<react_or_general_dsl> \
# AGENT_MODEL=<agent_model_name> \
# scripts/rerun_missing_wsr_react_direct.sh
```

### Generic EWM Smoke Test With Base Claude, Worst-to-Best Task Order

This tests the new generic `ewm` runtime, not the older task-specific
`general_dsl` path. It uses base Claude CLI as the agent and OpenRouter
`gpt-4o-2024-11-20` for the simulated user and judge, matching the baseline
setup we have been using.

Task order is based on the latest local base Claude ReAct baseline results,
from weakest to strongest among the selected read-oriented families:

1. `knowledge_qa` (`original`)
2. `policy_violation_identification` (`b2b`)
3. `confidential_company_knowledge` (`b2b`)
4. `wrong_stage_rectification` (`b2b`)
5. `named_entity_disambiguation` (`original`)
6. `internal_operation_data` (`b2b`)
7. `private_customer_information` (`b2b`)

Run from a login node or compute node where Claude CLI authentication is
available. This does not require vLLM.

```bash
cd /work/hdd/bgtb/acheng11/CRMArena
mkdir -p logs/run_wrappers

RUN_NAME="base_claude_ewm_smoke_5each_$(date +%Y%m%d_%H%M)"
PID_FILE="logs/run_wrappers/${RUN_NAME}.pid"
PGID_FILE="logs/run_wrappers/${RUN_NAME}.pgid"

setsid nohup bash -lc '
  cd /work/hdd/bgtb/acheng11/CRMArena
  echo "$$" > "'"$PID_FILE"'"
  ps -o pgid= -p "$$" | tr -d " " > "'"$PGID_FILE"'"
  module purge >/dev/null 2>&1 || true
  module load gcc-native
  module load cudatoolkit/25.5_12.9
  module load python/miniforge3_pytorch/2.10.0
  source .venv-crm-modern/bin/activate
  set -a
  source /work/hdd/bgtb/acheng11/.model-configs.txt
  set +a

  COMMON_ENV="MODEL_CONFIG_FILE=/dev/null AGENT_MODEL=claude_cli AGENT_PROVIDER=claude_cli CLAUDE_CONFIG_DIR=/work/hdd/bgtb/acheng11/.claude-bench CLAUDE_CLI_MODEL=${CLAUDE_CLI_MODEL:-default} AGENT_REASONING_MODE=default AGENT_STRATEGY=ewm JUDGE_PROVIDER=openrouter USER_PROVIDER=openrouter JUDGE_MODEL=${JUDGE_MODEL:-openai/gpt-4o-2024-11-20} USER_MODEL=${USER_MODEL:-openai/gpt-4o-2024-11-20} MAX_TASKS_PER_CATEGORY=5 INTERACTIVE=true PRIVACY_AWARE_PROMPT=true MAX_TURNS=20 MAX_USER_TURNS=10 AGENT_MAX_TOKENS=2500 USE_SYNTACTIC_VERIFIER=false USE_WORKING_MEMORY=false USE_QUOTE_CLIPBOARD=false USE_LEAD_CLIPBOARD=false ROUTING_MODE=none SCAFFOLD_MODE=none SKIP_HEALTH_CHECKS=true CRMARENA_VENV=/work/hdd/bgtb/acheng11/CRMArena/.venv-crm-modern PYTHON_BIN=$(command -v python) RUN_TAG='"$RUN_NAME"' LOG_TAG='"$RUN_NAME"'"

  eval "$COMMON_ENV EWM_ORG_TYPE=original ORG_TYPES_CSV=original TASKS_CSV=knowledge_qa ./run_tasks_crmarena_pro.sh"
  eval "$COMMON_ENV EWM_ORG_TYPE=b2b ORG_TYPES_CSV=b2b TASKS_CSV=policy_violation_identification ./run_tasks_crmarena_pro.sh"
  eval "$COMMON_ENV EWM_ORG_TYPE=b2b ORG_TYPES_CSV=b2b TASKS_CSV=confidential_company_knowledge ./run_tasks_crmarena_pro.sh"
  eval "$COMMON_ENV EWM_ORG_TYPE=b2b ORG_TYPES_CSV=b2b TASKS_CSV=wrong_stage_rectification ./run_tasks_crmarena_pro.sh"
  eval "$COMMON_ENV EWM_ORG_TYPE=original ORG_TYPES_CSV=original TASKS_CSV=named_entity_disambiguation ./run_tasks_crmarena_pro.sh"
  eval "$COMMON_ENV EWM_ORG_TYPE=b2b ORG_TYPES_CSV=b2b TASKS_CSV=internal_operation_data ./run_tasks_crmarena_pro.sh"
  eval "$COMMON_ENV EWM_ORG_TYPE=b2b ORG_TYPES_CSV=b2b TASKS_CSV=private_customer_information ./run_tasks_crmarena_pro.sh"
' > "logs/run_wrappers/${RUN_NAME}.log" 2>&1 < /dev/null &

for _ in $(seq 1 50); do
  [[ -s "$PID_FILE" && -s "$PGID_FILE" ]] && break
  sleep 0.1
done
WRAPPER_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
WRAPPER_PGID="$(cat "$PGID_FILE" 2>/dev/null || true)"
echo "Started wrapper PID: ${WRAPPER_PID}"
echo "Started wrapper PGID: ${WRAPPER_PGID}"
echo "Wrapper log: /work/hdd/bgtb/acheng11/CRMArena/logs/run_wrappers/${RUN_NAME}.log"
echo "Original-org results: /work/hdd/bgtb/acheng11/CRMArena/results/original_multi-turn/ewm_claude_cli_${RUN_NAME}_noverifier_nowm"
echo "B2B results: /work/hdd/bgtb/acheng11/CRMArena/results/b2b_multi-turn/ewm_claude_cli_${RUN_NAME}_noverifier_nowm"
if [[ -n "$WRAPPER_PGID" ]]; then
  echo "Stop on this same node: kill -TERM -${WRAPPER_PGID}; sleep 5; kill -KILL -${WRAPPER_PGID}"
else
  echo "Could not read wrapper PGID. Find it with: ps -u \"$(id -u)\" -o pid,ppid,pgid,cmd | grep ${RUN_NAME}"
fi
```

### Generic EWM Smoke Test With Codex 5.6, Worst-to-Best Task Order

This is the same new generic `ewm` runtime smoke test as above, but with Codex
CLI as the agent. It uses OpenRouter `gpt-4o-2024-11-20` for the simulated user
and judge. Change `CODEX_CLI_MODEL` if your Codex CLI account exposes a
different model slug.

```bash
cd /work/hdd/bgtb/acheng11/CRMArena
mkdir -p logs/run_wrappers

RUN_NAME="codex56_ewm_smoke_5each_$(date +%Y%m%d_%H%M)"
PID_FILE="logs/run_wrappers/${RUN_NAME}.pid"
PGID_FILE="logs/run_wrappers/${RUN_NAME}.pgid"

setsid nohup bash -lc '
  cd /work/hdd/bgtb/acheng11/CRMArena
  echo "$$" > "'"$PID_FILE"'"
  ps -o pgid= -p "$$" | tr -d " " > "'"$PGID_FILE"'"
  module purge >/dev/null 2>&1 || true
  module load gcc-native
  module load cudatoolkit/25.5_12.9
  module load python/miniforge3_pytorch/2.10.0
  source .venv-crm-modern/bin/activate
  set -a
  source /work/hdd/bgtb/acheng11/.model-configs.txt
  set +a

  COMMON_ENV="MODEL_CONFIG_FILE=/dev/null AGENT_MODEL=codex_cli AGENT_PROVIDER=codex_cli CODEX_HOME=/work/hdd/bgtb/acheng11/.codex-bench CODEX_CLI_MODEL=${CODEX_CLI_MODEL:-gpt-5.6-sol} AGENT_REASONING_MODE=default AGENT_STRATEGY=ewm JUDGE_PROVIDER=openrouter USER_PROVIDER=openrouter JUDGE_MODEL=${JUDGE_MODEL:-openai/gpt-4o-2024-11-20} USER_MODEL=${USER_MODEL:-openai/gpt-4o-2024-11-20} MAX_TASKS_PER_CATEGORY=5 INTERACTIVE=true PRIVACY_AWARE_PROMPT=true MAX_TURNS=20 MAX_USER_TURNS=10 AGENT_MAX_TOKENS=2500 USE_SYNTACTIC_VERIFIER=false USE_WORKING_MEMORY=false USE_QUOTE_CLIPBOARD=false USE_LEAD_CLIPBOARD=false ROUTING_MODE=none SCAFFOLD_MODE=none SKIP_HEALTH_CHECKS=true CRMARENA_VENV=/work/hdd/bgtb/acheng11/CRMArena/.venv-crm-modern PYTHON_BIN=$(command -v python) RUN_TAG='"$RUN_NAME"' LOG_TAG='"$RUN_NAME"'"

  eval "$COMMON_ENV EWM_ORG_TYPE=original ORG_TYPES_CSV=original TASKS_CSV=knowledge_qa ./run_tasks_crmarena_pro.sh"
  eval "$COMMON_ENV EWM_ORG_TYPE=b2b ORG_TYPES_CSV=b2b TASKS_CSV=policy_violation_identification ./run_tasks_crmarena_pro.sh"
  eval "$COMMON_ENV EWM_ORG_TYPE=b2b ORG_TYPES_CSV=b2b TASKS_CSV=confidential_company_knowledge ./run_tasks_crmarena_pro.sh"
  eval "$COMMON_ENV EWM_ORG_TYPE=b2b ORG_TYPES_CSV=b2b TASKS_CSV=wrong_stage_rectification ./run_tasks_crmarena_pro.sh"
  eval "$COMMON_ENV EWM_ORG_TYPE=original ORG_TYPES_CSV=original TASKS_CSV=named_entity_disambiguation ./run_tasks_crmarena_pro.sh"
  eval "$COMMON_ENV EWM_ORG_TYPE=b2b ORG_TYPES_CSV=b2b TASKS_CSV=internal_operation_data ./run_tasks_crmarena_pro.sh"
  eval "$COMMON_ENV EWM_ORG_TYPE=b2b ORG_TYPES_CSV=b2b TASKS_CSV=private_customer_information ./run_tasks_crmarena_pro.sh"
' > "logs/run_wrappers/${RUN_NAME}.log" 2>&1 < /dev/null &

for _ in $(seq 1 50); do
  [[ -s "$PID_FILE" && -s "$PGID_FILE" ]] && break
  sleep 0.1
done
WRAPPER_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
WRAPPER_PGID="$(cat "$PGID_FILE" 2>/dev/null || true)"
echo "Started wrapper PID: ${WRAPPER_PID}"
echo "Started wrapper PGID: ${WRAPPER_PGID}"
echo "Wrapper log: /work/hdd/bgtb/acheng11/CRMArena/logs/run_wrappers/${RUN_NAME}.log"
echo "Original-org results: /work/hdd/bgtb/acheng11/CRMArena/results/original_multi-turn/ewm_codex_cli_${RUN_NAME}_noverifier_nowm"
echo "B2B results: /work/hdd/bgtb/acheng11/CRMArena/results/b2b_multi-turn/ewm_codex_cli_${RUN_NAME}_noverifier_nowm"
if [[ -n "$WRAPPER_PGID" ]]; then
  echo "Stop on this same node: kill -TERM -${WRAPPER_PGID}; sleep 5; kill -KILL -${WRAPPER_PGID}"
else
  echo "Could not read wrapper PGID. Find it with: ps -u \"$(id -u)\" -o pid,ppid,pgid,cmd | grep ${RUN_NAME}"
fi
```

### Generic EWM Codex Smoke Test As Slurm Batch Job

This runs the Codex generic EWM smoke test as a Slurm job and charges
`bhit-dtai-gh` by default. It uses a short smoke configuration:
`MAX_TASKS_PER_CATEGORY=2`, `MAX_TURNS=4`, `MAX_USER_TURNS=4`, and
`EWM_MAX_STEPS=8`. The task order is KQA, PVI, CCK, WSR, NED, IOD, PCI.

```bash
cd /work/hdd/bgtb/acheng11/CRMArena

sbatch scripts/deltaai_codex_ewm_smoke.sbatch
```

Useful overrides:

```bash
# Use 5 examples per task family.
sbatch --export=ALL,MAX_TASKS_PER_CATEGORY=5 \
  scripts/deltaai_codex_ewm_smoke.sbatch

# Charge the older bgtb allocation instead.
sbatch --account=bgtb-dtai-gh \
  scripts/deltaai_codex_ewm_smoke.sbatch

# Use a different Codex CLI model if your bench config supports it.
sbatch --export=ALL,CODEX_CLI_MODEL=gpt-5.4-mini,MAX_TASKS_PER_CATEGORY=8 \
  scripts/deltaai_codex_ewm_smoke.sbatch
```

### Generic EWM Qwen35 vLLM Smoke Test On Serving Node

Use this when Qwen35 is already being served by vLLM and you are SSH'd into
the same compute node as the vLLM server. This tests the generic `ewm` runtime
with Qwen35 as the agent, simulated user, and judge through the OpenAI-compatible
vLLM endpoint.

By default this runs two examples per selected task family with short
interaction limits. Change `MAX_TASKS_PER_CATEGORY=2` to `5`, `10`, or `0`
when you are ready to scale.

```bash
cd /work/hdd/bgtb/acheng11/CRMArena
mkdir -p logs/run_wrappers

QWEN_BASE_URL="${QWEN_BASE_URL:-http://127.0.0.1:8001/v1}"
QWEN_MODEL="${QWEN_MODEL:-openai/Qwen3.5-35B-A3B}"
MAX_TASKS_PER_CATEGORY="${MAX_TASKS_PER_CATEGORY:-2}"
RUN_NAME="qwen35_vllm_ewm_smoke_${MAX_TASKS_PER_CATEGORY}each_$(date +%Y%m%d_%H%M)"
PID_FILE="logs/run_wrappers/${RUN_NAME}.pid"
PGID_FILE="logs/run_wrappers/${RUN_NAME}.pgid"

curl -fsS "${QWEN_BASE_URL%/}/models" >/dev/null || {
  echo "ERROR: Qwen35 vLLM endpoint is not reachable at ${QWEN_BASE_URL%/}/models"
  echo "Run this from the same compute node as the vLLM server, or set QWEN_BASE_URL."
  exit 1
}

setsid nohup bash -lc '
  cd /work/hdd/bgtb/acheng11/CRMArena
  echo "$$" > "'"$PID_FILE"'"
  ps -o pgid= -p "$$" | tr -d " " > "'"$PGID_FILE"'"

  module purge >/dev/null 2>&1 || true
  module load gcc-native
  module load cudatoolkit/25.5_12.9
  module load python/miniforge3_pytorch/2.10.0
  source .venv-crm-modern/bin/activate

  COMMON_ENV="MODEL_CONFIG_FILE=/dev/null AGENT_MODEL='"$QWEN_MODEL"' AGENT_PROVIDER=openai AGENT_BASE_URL='"$QWEN_BASE_URL"' AGENT_API_KEY=dummy AGENT_STRATEGY=ewm JUDGE_PROVIDER=openai JUDGE_MODEL='"$QWEN_MODEL"' JUDGE_BASE_URL='"$QWEN_BASE_URL"' JUDGE_API_KEY=dummy USER_PROVIDER=openai USER_MODEL='"$QWEN_MODEL"' USER_BASE_URL='"$QWEN_BASE_URL"' USER_API_KEY=dummy MAX_TASKS_PER_CATEGORY='"$MAX_TASKS_PER_CATEGORY"' INTERACTIVE=true PRIVACY_AWARE_PROMPT=true MAX_TURNS=4 MAX_USER_TURNS=4 EWM_MAX_STEPS=8 AGENT_MAX_TOKENS=1800 EWM_FRAME_MAX_TOKENS=1200 EWM_DECISION_MAX_TOKENS=1400 EWM_CLAIM_MAX_TOKENS=1200 EWM_COMPLETION_VERIFIER_MAX_TOKENS=900 USE_SYNTACTIC_VERIFIER=false USE_WORKING_MEMORY=false USE_QUOTE_CLIPBOARD=false USE_LEAD_CLIPBOARD=false ROUTING_MODE=none SCAFFOLD_MODE=none CRMARENA_VENV=/work/hdd/bgtb/acheng11/CRMArena/.venv-crm-modern PYTHON_BIN=$(command -v python) RUN_TAG='"$RUN_NAME"' LOG_TAG='"$RUN_NAME"'"

  eval "$COMMON_ENV EWM_ORG_TYPE=original ORG_TYPES_CSV=original TASKS_CSV=knowledge_qa ./run_tasks_crmarena_pro.sh"
  eval "$COMMON_ENV EWM_ORG_TYPE=b2b ORG_TYPES_CSV=b2b TASKS_CSV=policy_violation_identification ./run_tasks_crmarena_pro.sh"
  eval "$COMMON_ENV EWM_ORG_TYPE=b2b ORG_TYPES_CSV=b2b TASKS_CSV=confidential_company_knowledge ./run_tasks_crmarena_pro.sh"
  eval "$COMMON_ENV EWM_ORG_TYPE=b2b ORG_TYPES_CSV=b2b TASKS_CSV=wrong_stage_rectification ./run_tasks_crmarena_pro.sh"
  eval "$COMMON_ENV EWM_ORG_TYPE=original ORG_TYPES_CSV=original TASKS_CSV=named_entity_disambiguation ./run_tasks_crmarena_pro.sh"
  eval "$COMMON_ENV EWM_ORG_TYPE=b2b ORG_TYPES_CSV=b2b TASKS_CSV=internal_operation_data ./run_tasks_crmarena_pro.sh"
  eval "$COMMON_ENV EWM_ORG_TYPE=b2b ORG_TYPES_CSV=b2b TASKS_CSV=private_customer_information ./run_tasks_crmarena_pro.sh"
' > "logs/run_wrappers/${RUN_NAME}.log" 2>&1 < /dev/null &

for _ in $(seq 1 50); do
  [[ -s "$PID_FILE" && -s "$PGID_FILE" ]] && break
  sleep 0.1
done
WRAPPER_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
WRAPPER_PGID="$(cat "$PGID_FILE" 2>/dev/null || true)"
echo "Started wrapper PID: ${WRAPPER_PID}"
echo "Started wrapper PGID: ${WRAPPER_PGID}"
echo "Wrapper log: /work/hdd/bgtb/acheng11/CRMArena/logs/run_wrappers/${RUN_NAME}.log"
echo "Original-org results: /work/hdd/bgtb/acheng11/CRMArena/results/original_multi-turn/ewm_${QWEN_MODEL//[\/:,]/_}_${RUN_NAME}_noverifier_nowm"
echo "B2B results: /work/hdd/bgtb/acheng11/CRMArena/results/b2b_multi-turn/ewm_${QWEN_MODEL//[\/:,]/_}_${RUN_NAME}_noverifier_nowm"
if [[ -n "$WRAPPER_PGID" ]]; then
  echo "Stop on this same node: kill -TERM -${WRAPPER_PGID}; sleep 5; kill -KILL -${WRAPPER_PGID}"
else
  echo "Could not read wrapper PGID. Find it with: ps -u \"$(id -u)\" -o pid,ppid,pgid,cmd | grep ${RUN_NAME}"
fi
```

### Generic EWM Claude 10-Example Slurm Smoke Test

This runs the same selected EWM task order as the Codex Slurm smoke job, but
with Claude CLI as the agent. It does not require vLLM. It requests one GPU
because DeltaAI jobs in this project are expected to request one, although the
agent itself is served through Claude CLI.

Optional quick readiness check before submitting. If Claude session quota is
still exhausted, this should return the quota/reset message within 3 minutes:

```bash
CLAUDE_CONFIG_DIR=/work/hdd/bgtb/acheng11/.claude-bench \
timeout 180 claude --print --no-session-persistence --output-format text \
  "Return exactly: claude ok"
```

Submit 10 examples per selected task family:

```bash
cd /work/hdd/bgtb/acheng11/CRMArena
mkdir -p logs/ewm-smoke/slurm

sbatch --export=ALL,MAX_TASKS_PER_CATEGORY=5,RUN_TAG=claude_ewm_smoke_5each_4turn_$(date +%Y%m%d_%H%M) \
  scripts/deltaai_claude_ewm_smoke.sbatch
```

If a previous Claude EWM run failed with `Claude's response exceeded the 1200
output token maximum`, rerun with a fresh `RUN_TAG` as above. The script now
defaults to larger EWM component caps so Claude can emit the structured JSON
the runtime expects.

Useful overrides:

```bash
# Charge the older bgtb allocation instead of the script default bhit account.
sbatch --account=bgtb-dtai-gh --export=ALL,MAX_TASKS_PER_CATEGORY=10 \
  scripts/deltaai_claude_ewm_smoke.sbatch

# Use an explicit Claude model if your Claude CLI account exposes it.
sbatch --export=ALL,MAX_TASKS_PER_CATEGORY=10,CLAUDE_CLI_MODEL=claude-opus-5 \
  scripts/deltaai_claude_ewm_smoke.sbatch

# More turns for debugging multi-turn follow-up behavior.
sbatch --export=ALL,MAX_TASKS_PER_CATEGORY=10,MAX_TURNS=8,MAX_USER_TURNS=8,EWM_MAX_STEPS=10 \
  scripts/deltaai_claude_ewm_smoke.sbatch

# Override Claude/EWM output caps if needed.
sbatch --export=ALL,MAX_TASKS_PER_CATEGORY=10,EWM_DECISION_MAX_TOKENS=6000,EWM_COMPLETION_VERIFIER_MAX_TOKENS=3000 \
  scripts/deltaai_claude_ewm_smoke.sbatch
```

### Generic EWM Codex CLI Smoke Test On Login Node

Use this when you want to avoid Slurm/GPU usage and run the generic EWM runtime
through Codex CLI directly from the login node. This does not use vLLM. It uses
the separate benchmark Codex authentication directory, not your default/personal
Codex account. It uses OpenRouter `gpt-4o-2024-11-20` for the simulated user
and judge from `/work/hdd/bgtb/acheng11/.model-configs.txt`.

Change `MAX_TASKS_PER_CATEGORY=5` to `1`, `2`, `10`, or `0` as needed. Keep a
fresh `RUN_NAME` if you want separate logs.

```bash
cd /work/hdd/bgtb/acheng11/CRMArena
mkdir -p logs/run_wrappers

MAX_TASKS_PER_CATEGORY=5
BENCH_CODEX_HOME="/work/hdd/bgtb/acheng11/.codex-bench"
RUN_NAME="codex_login_ewm_${MAX_TASKS_PER_CATEGORY}each_$(date +%Y%m%d_%H%M)"
PID_FILE="logs/run_wrappers/${RUN_NAME}.pid"
PGID_FILE="logs/run_wrappers/${RUN_NAME}.pgid"

setsid nohup bash -lc '
  cd /work/hdd/bgtb/acheng11/CRMArena
  echo "$$" > "'"$PID_FILE"'"
  ps -o pgid= -p "$$" | tr -d " " > "'"$PGID_FILE"'"

  module purge >/dev/null 2>&1 || true
  module load gcc-native
  module load python/miniforge3_pytorch/2.10.0
  source .venv-crm-modern/bin/activate

  set -a
  source /work/hdd/bgtb/acheng11/.model-configs.txt
  set +a

  COMMON_ENV="MODEL_CONFIG_FILE=/dev/null AGENT_MODEL=codex_cli AGENT_PROVIDER=codex_cli CODEX_HOME='"$BENCH_CODEX_HOME"' CODEX_CLI_MODEL=${CODEX_CLI_MODEL:-gpt-5.6-sol} AGENT_REASONING_MODE=default AGENT_STRATEGY=ewm JUDGE_PROVIDER=openrouter USER_PROVIDER=openrouter JUDGE_MODEL=${JUDGE_MODEL:-openai/gpt-4o-2024-11-20} USER_MODEL=${USER_MODEL:-openai/gpt-4o-2024-11-20} MAX_TASKS_PER_CATEGORY='"$MAX_TASKS_PER_CATEGORY"' INTERACTIVE=true PRIVACY_AWARE_PROMPT=true MAX_TURNS=4 MAX_USER_TURNS=4 EWM_MAX_STEPS=10 AGENT_MAX_TOKENS=2500 USE_SYNTACTIC_VERIFIER=false USE_WORKING_MEMORY=false USE_QUOTE_CLIPBOARD=false USE_LEAD_CLIPBOARD=false ROUTING_MODE=none SCAFFOLD_MODE=none SKIP_HEALTH_CHECKS=true CRMARENA_VENV=/work/hdd/bgtb/acheng11/CRMArena/.venv-crm-modern PYTHON_BIN=$(command -v python) RUN_TAG='"$RUN_NAME"' LOG_TAG='"$RUN_NAME"'"

  eval "$COMMON_ENV EWM_ORG_TYPE=original ORG_TYPES_CSV=original TASKS_CSV=knowledge_qa ./run_tasks_crmarena_pro.sh"
  eval "$COMMON_ENV EWM_ORG_TYPE=b2b ORG_TYPES_CSV=b2b TASKS_CSV=policy_violation_identification ./run_tasks_crmarena_pro.sh"
  eval "$COMMON_ENV EWM_ORG_TYPE=b2b ORG_TYPES_CSV=b2b TASKS_CSV=confidential_company_knowledge ./run_tasks_crmarena_pro.sh"
  eval "$COMMON_ENV EWM_ORG_TYPE=b2b ORG_TYPES_CSV=b2b TASKS_CSV=wrong_stage_rectification ./run_tasks_crmarena_pro.sh"
  eval "$COMMON_ENV EWM_ORG_TYPE=original ORG_TYPES_CSV=original TASKS_CSV=named_entity_disambiguation ./run_tasks_crmarena_pro.sh"
  eval "$COMMON_ENV EWM_ORG_TYPE=b2b ORG_TYPES_CSV=b2b TASKS_CSV=internal_operation_data ./run_tasks_crmarena_pro.sh"
  eval "$COMMON_ENV EWM_ORG_TYPE=b2b ORG_TYPES_CSV=b2b TASKS_CSV=private_customer_information ./run_tasks_crmarena_pro.sh"
' > "logs/run_wrappers/${RUN_NAME}.log" 2>&1 < /dev/null &

for _ in $(seq 1 50); do
  [[ -s "$PID_FILE" && -s "$PGID_FILE" ]] && break
  sleep 0.1
done
WRAPPER_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
WRAPPER_PGID="$(cat "$PGID_FILE" 2>/dev/null || true)"
echo "Started wrapper PID: ${WRAPPER_PID}"
echo "Started wrapper PGID: ${WRAPPER_PGID}"
echo "Wrapper log: /work/hdd/bgtb/acheng11/CRMArena/logs/run_wrappers/${RUN_NAME}.log"
echo "Original-org results: /work/hdd/bgtb/acheng11/CRMArena/results/original_multi-turn/ewm_codex_cli_${RUN_NAME}_noverifier_nowm"
echo "B2B results: /work/hdd/bgtb/acheng11/CRMArena/results/b2b_multi-turn/ewm_codex_cli_${RUN_NAME}_noverifier_nowm"
if [[ -n "$WRAPPER_PGID" ]]; then
  echo "Stop on this same login node: kill -TERM -${WRAPPER_PGID}; sleep 5; kill -KILL -${WRAPPER_PGID}"
else
  echo "Could not read wrapper PGID. Find it with: ps -u \"$(id -u)\" -o pid,ppid,pgid,cmd | grep ${RUN_NAME}"
fi
```

Sanity check that this command is using the benchmark Codex account before
launching a paid run:

```bash
CODEX_HOME=/work/hdd/bgtb/acheng11/.codex-bench \
codex exec --skip-git-repo-check "Return exactly: bench codex ok"
```
