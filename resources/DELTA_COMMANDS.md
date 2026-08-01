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