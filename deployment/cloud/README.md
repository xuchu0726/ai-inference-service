# Cloud GPU Deployment Scripts

## 1. Purpose

This directory contains cloud GPU deployment scripts for the AI Inference Service project.

The goal is to migrate the current FastAPI + VLLMBackend + vLLM serving pipeline from local/CX3 validation to a stable cloud GPU environment.

Cloud GPU is used for:

1. vLLM serving baseline
2. FastAPI + VLLMBackend end-to-end validation
3. Seed-OSS-36B tensor parallel smoke test
4. benchmark and performance analysis
5. later Prometheus / Grafana / stress testing

---

## 2. Why cloud GPU is needed

Local Mac environment is useful for:

1. API development
2. backend abstraction
3. small-model TransformersBackend validation
4. benchmark script development
5. documentation and deployment preparation

CX3 is useful for:

1. GPU availability validation
2. CUDA / PyTorch validation
3. vLLM environment validation
4. small-model vLLM E2E smoke test

Cloud GPU is needed because:

1. GPU resources can be held continuously during the rental period
2. vLLM server can run as a long-lived service
3. multi-GPU tensor parallel deployment is easier to control
4. benchmark, monitoring and demo recording require stable runtime
5. Seed-OSS-36B deployment requires more predictable GPU resources than CX3 queue jobs

---

## 3. Scripts

### 3.1 run_vllm_qwen_1_5b.sh

Starts Qwen2.5-1.5B with vLLM.

Purpose:

1. validate cloud GPU environment
2. validate CUDA / torch / vLLM
3. validate model download
4. validate OpenAI-compatible vLLM API
5. provide a baseline before switching to Seed-OSS-36B

Default model:

    Qwen/Qwen2.5-1.5B-Instruct

Default vLLM port:

    8001

Recommended command:

    bash deployment/cloud/run_vllm_qwen_1_5b.sh

---

### 3.2 run_fastapi_vllm.sh

Starts the project FastAPI service with VLLMBackend.

Default backend:

    INFERENCE_BACKEND=vllm

Default FastAPI port:

    8000

Default downstream vLLM URL:

    http://127.0.0.1:8001/v1

Service chain:

    Client
    -> FastAPI /generate
    -> VLLMBackend
    -> vLLM /v1/chat/completions
    -> GPU model
    -> response

Recommended command:

    bash deployment/cloud/run_fastapi_vllm.sh

---

### 3.3 smoke_test_generate.py

Sends one request to FastAPI /generate.

Purpose:

1. verify FastAPI is reachable
2. verify VLLMBackend is selected
3. verify vLLM downstream server is reachable
4. verify GPU model inference works
5. save response JSON to results/

Output file:

    results/cloud_smoke_test_response.json

Recommended command:

    python deployment/cloud/smoke_test_generate.py

---

### 3.4 run_vllm_seed_oss_36b_tp2.sh

Template for Seed-OSS-36B multi-GPU tensor parallel deployment with vLLM.

Default settings:

    TENSOR_PARALLEL_SIZE=2
    MAX_MODEL_LEN=4096
    DTYPE=bfloat16
    GPU_MEMORY_UTILIZATION=0.90

This script should be used first for short-context smoke test.

Do not start with long context. Increase MAX_MODEL_LEN only after short-context model loading and generation succeed.

The model ID is currently kept as a configurable template variable:

    MODEL_NAME

Before cloud execution, verify the actual Seed-OSS-36B model ID, access permission and download method.

Example command:

    MODEL_NAME=<verified-seed-oss-36b-model-id> \
    TENSOR_PARALLEL_SIZE=2 \
    MAX_MODEL_LEN=4096 \
    bash deployment/cloud/run_vllm_seed_oss_36b_tp2.sh

---

## 4. Recommended cloud execution order

### Step 1: install dependencies

Use either a Python virtual environment or Docker.

Minimum Python package requirements:

    pip install -r requirements.txt
    pip install -r requirements-vllm.txt

If requirements-vllm.txt only pins vLLM, vLLM will install its own compatible dependencies.

---

### Step 2: start vLLM Qwen baseline

Terminal 1:

    bash deployment/cloud/run_vllm_qwen_1_5b.sh

Wait until vLLM is ready.

Check:

    curl http://127.0.0.1:8001/v1/models

Expected result:

    HTTP 200
    model list returned

---

### Step 3: start FastAPI with VLLMBackend

Terminal 2:

    bash deployment/cloud/run_fastapi_vllm.sh

Check:

    curl http://127.0.0.1:8000/health

Expected result:

    {"status":"ok"}

---

### Step 4: run smoke test

Terminal 3:

    python deployment/cloud/smoke_test_generate.py

Expected result:

1. HTTP status 200
2. response text returned
3. backend is vllm
4. input_tokens / output_tokens returned
5. tokens_per_second returned
6. result saved under results/

---

### Step 5: run benchmark

After smoke test succeeds, run benchmark scripts.

Planned files:

    scripts/benchmark_vllm_backend.py
    scripts/analyze_vllm_benchmark.py
    results/vllm_benchmark.csv
    results/vllm_benchmark_summary.csv
    docs/vllm_benchmark_report.md

Target metrics:

1. TTFT
2. E2E latency
3. P50 latency
4. P95 latency
5. tokens/s
6. error_rate
7. concurrency
8. input_tokens
9. output_tokens

---

### Step 6: try Seed-OSS-36B tensor parallel

Only after Qwen baseline and FastAPI E2E succeed.

Example:

    MODEL_NAME=<verified-seed-oss-36b-model-id> \
    TENSOR_PARALLEL_SIZE=2 \
    MAX_MODEL_LEN=4096 \
    bash deployment/cloud/run_vllm_seed_oss_36b_tp2.sh

If model loading fails, record:

1. GPU type
2. GPU count
3. total GPU memory
4. tensor_parallel_size
5. max_model_len
6. dtype
7. error log
8. whether the failure is OOM, model access, dependency, architecture, or network related

---

## 5. Engineering rule

Do not use cloud GPU for trial-and-error editing.

Before starting expensive GPU instances, prepare:

1. startup scripts
2. smoke test client
3. benchmark scripts
4. logging path
5. result path
6. documentation template

Cloud GPU should be used for concentrated experiments, not for writing scripts from scratch.

---

## 6. Current project direction

The cloud deployment route supports the final AI Infra direction:

    FastAPI
    -> VLLMBackend
    -> vLLM serving
    -> cloud GPU
    -> Seed-OSS-36B tensor parallel
    -> benchmark
    -> monitoring
    -> failure analysis

This is the main path for turning the 项目 into a real LLM inference engineering project.

---

## 7. Relationship to the 4-week 项目 plan

### Week 1

Cloud scripts support:

1. GPU environment preparation
2. vLLM serving validation
3. FastAPI API deployment
4. Seed-OSS-36B deployment preparation
5. environment and failure documentation

### Week 2

Cloud scripts support:

1. performance baseline
2. benchmark data collection
3. latency / P95 / tokens/s measurement
4. vLLM parameter tuning
5. KV Cache and batching analysis

### Week 3

Cloud scripts support:

1. multi-GPU tensor parallel experiments
2. Seed-OSS-36B smoke test
3. high-availability service design
4. multimodal extension preparation

### Week 4

Cloud scripts support:

1. stress testing
2. monitoring
3. final deployment SOP
4. demo recording
5. final technical report

---

## 8. Notes before running on cloud

Before using cloud GPU, confirm:

1. GPU type and memory
2. CUDA driver version
3. Python version
4. torch version
5. vLLM version
6. model access permission
7. disk space for model weights
8. network access to model registry
9. whether ports 8000 and 8001 are available
10. whether multiple terminals or tmux are available

Recommended cloud workflow:

    prepare scripts locally
    push to GitHub
    pull repository on cloud GPU
    install dependencies
    start vLLM
    start FastAPI
    run smoke test
    run benchmark
    save logs and results
    commit reproducible scripts and reports

---

## 9. Seed-OSS-36B-Instruct target-model deployment

The target model for this 项目 project is:

    ByteDance-Seed/Seed-OSS-36B-Instruct

This is different from the Qwen baseline models used for low-risk serving validation.

Model roles:

| Model | Role |
|---|---|
| Qwen/Qwen2.5-1.5B-Instruct | Environment and serving smoke test |
| Qwen/Qwen2.5-7B-Instruct / Qwen/Qwen2.5-14B-Instruct | Medium-size vLLM benchmark baseline |
| ByteDance-Seed/Seed-OSS-36B-Instruct | Target model for Seed-OSS deployment and later long-context validation |

Seed-OSS-36B-Instruct requires a separate vLLM startup path because it uses Seed-specific serving options.

The target script is:

    deployment/cloud/run_vllm_seed_oss_36b_tp.sh

The low-resource TP=2 smoke-test wrapper is:

    deployment/cloud/run_vllm_seed_oss_36b_tp2.sh

The TP=2 script is experimental and should only be used for short-context feasibility checks. It is not the recommended full deployment configuration.

Seed-OSS vLLM startup uses:

    --enable-auto-tool-choice
    --tool-call-parser seed_oss
    --trust-remote-code
    --tensor-parallel-size
    --max-model-len
    --max-num-batched-tokens
    --gpu-memory-utilization
    --dtype bfloat16

For first short-context smoke test:

    TENSOR_PARALLEL_SIZE=2 \
    MAX_MODEL_LEN=4096 \
    MAX_NUM_BATCHED_TOKENS=8192 \
    bash deployment/cloud/run_vllm_seed_oss_36b_tp.sh

For larger multi-GPU deployment, increase tensor parallel size and context length according to available GPU memory.

---

## 10. Seed-OSS thinking budget

For generic models, the project records thinking_budget as an API-level field.

For Seed-OSS-36B-Instruct, thinking_budget should be passed to vLLM through:

    chat_template_kwargs.thinking_budget

The VLLMBackend now supports Seed-OSS-specific payload construction. When the model name contains Seed-OSS, or when VLLM_ENABLE_SEED_THINKING_BUDGET=true, the request payload includes:

    "chat_template_kwargs": {
        "thinking_budget": <value>
    }

This keeps Qwen baseline compatibility while enabling Seed-OSS native thinking-budget control.
