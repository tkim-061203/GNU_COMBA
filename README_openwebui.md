# COMBA-PROMPT on Open WebUI

This guide covers **hosting the LangGraph COMBA-PROMPT pipeline as an OpenAI-compatible
API** so it can be used interactively from [Open WebUI](https://docs.openwebui.com/).

The server ([`src/langgraph_core/api_server.py`](src/langgraph_core/api_server.py)) wraps the
multi-agent pipeline behind a `/v1/chat/completions` endpoint with **real per-node SSE
streaming**, so Open WebUI shows progressive updates (Converter → Generator → Syntax
Check → …) as the pipeline runs.

> This is the **interactive** front-end for the same pipeline documented in
> [README_langgraph.md](README_langgraph.md). For batch evaluation (`make langgraph`,
> RTLLM, VerilogEval) see [README.md](README.md). It is unrelated to the standalone
> `vLLM_OpenWebUI` custom-function project.

---

## Architecture

```text
 ┌────────────────────────┐      ┌────────────────────────┐
 │ vLLM "generator" :8000 │      │ vLLM "debugger"  :8001 │   (dual-GPU LLM backends)
 └───────────┬────────────┘      └───────────┬────────────┘
             │  base model                   │  LoRA debugger
             └───────────────┬───────────────┘
                             │  COMBALlm (llm_interface.py)
                  ┌──────────┴───────────┐
                  │  api_server.py :8100 │  FastAPI · OpenAI-compatible · SSE streaming
                  └──────────┬───────────┘
                             │  http://localhost:8100/v1
                  ┌──────────┴───────────┐
                  │      Open WebUI      │  Base URL + model = comba-verilog-pipeline
                  └──────────────────────┘
```

---

## Prerequisites

- The dual-GPU vLLM backends running (generator on `:8000`, debugger on `:8001`).
  See [README.md](README.md) → *Local Model Serving* (`./launch_dual_gpu.sh`).
- `iverilog` available on `PATH` (used by the syntax-check / TB-sim nodes).
- The conda environment used for the server (e.g. `test_VE`) with `fastapi`,
  `uvicorn`, `openai`, and the project's LangGraph deps installed.
- Open WebUI installed (`pip install open-webui` or via Docker).

---

## 1. Start the LLM backends

```bash
# Generator on GPU0:8000, Debugger on GPU1:8001
./launch_dual_gpu.sh
./launch_dual_gpu.sh --status   # verify both are up
```

## 2. Start the COMBA API server

```bash
conda activate test_VE
cd src/langgraph_core
uvicorn api_server:app --host 0.0.0.0 --port 8100
```

Verify it is healthy:

```bash
curl -s http://localhost:8100/health
curl -s http://localhost:8100/health/llm   # checks both vLLM backends
```

> **Stub mode (no GPUs needed)** — boot with a fake LLM to smoke-test the API:
> ```bash
> COMBA_USE_STUB=1 uvicorn api_server:app --host 0.0.0.0 --port 8100
> ```

## 3. Connect Open WebUI

In **Settings → Admin Panel → Connections → OpenAI API**, add a connection:

| Field    | Value                          |
|----------|--------------------------------|
| Base URL | `http://localhost:8100/v1`     |
| API Key  | anything (not validated)       |
| Model    | `comba-verilog-pipeline`       |

Start a new chat, select `comba-verilog-pipeline`, and prompt with a hardware spec,
e.g. *"Design a 10-bit adder named add_10bit with inputs [9:0] a, [9:0] b, cin and
outputs [9:0] sum, cout."* You will see the pipeline stream its progress and finish
with the verified Verilog plus a metrics table.

---

## API Endpoints

| Endpoint                 | Method | Purpose                                                  |
|--------------------------|--------|----------------------------------------------------------|
| `/v1/models`             | GET    | Lists the single model `comba-verilog-pipeline`.         |
| `/v1/chat/completions`   | POST   | OpenAI-compatible chat. Supports `stream: true` (SSE).   |
| `/health`                | GET    | Basic liveness + pipeline version.                       |
| `/health/llm`            | GET    | Per-backend LLM health (base + debugger).                |

---

## Configuration (environment variables)

Set these before launching `uvicorn` (or in `.env`).

### Pipeline behavior

| Variable                      | Default (server) | Effect |
|-------------------------------|------------------|--------|
| `COMBA_SKIP_TB_IF_NO_GOLDEN`  | `1`              | Skip functional TB-simulation when there is **no golden testbench** (the interactive case). The request returns as soon as Syntax Check passes. Set `0` to force the full generate-a-testbench + simulate flow. |
| `COMBA_SELF_CONSISTENCY`      | `0`              | `1` enables Best-of-N sampling (streams per-candidate progress). |
| `COMBA_MAX_SAMPLES`           | `10`             | Max candidates when self-consistency is on. |
| `COMBA_EARLY_EXIT`            | `1`              | Stop as soon as a candidate passes. |
| `COMBA_SC_START_ZERO`         | `0`              | Start the first candidate at `T=0` (greedy) then ramp. |
| `COMBA_USE_STUB`              | unset            | `1` → use a fake LLM (testing only). |

### LLM routing (read by `llm_interface.COMBALlm.from_env`)

| Variable             | Default                      |
|----------------------|------------------------------|
| `LLM_BASE_URL`       | `http://localhost:8000/v1`   |
| `LLM_DEBUGGER_URL`   | `http://localhost:8001/v1`   |
| `LLM_MODEL_BASE`     | `generator`                  |
| `LLM_MODEL_DEBUGGER` | `debugger`                   |
| `LLM_API_KEY`        | `not-needed`                 |

---

## Behavior notes

### Per-node SSE streaming
With `stream: true`, each pipeline node is forwarded to the client **as it completes**
(via a worker thread → `asyncio.Queue` bridge), so Open WebUI updates progressively
instead of waiting for the whole pipeline. Nodes that produce no state update (e.g.
guard nodes) are skipped safely.

### Open WebUI background-task bypass
Open WebUI automatically fires helper requests — **chat title**, **tags**,
**follow-up suggestions**, autocomplete — wrapped in a `### Task:` template, to the same
model endpoint. These are **not** Verilog design requests: the server detects them and
forwards them straight to the base model, bypassing the COMBA pipeline. This avoids
spurious `XML validation` failures and wasted GPU time.

> You can also disable those features entirely in Open WebUI:
> **Admin Settings → Interface** → turn off *Title / Tags / Follow-Up Generation*.

### Interactive TB-simulation skip
In interactive mode there is no golden testbench, so once a design passes Syntax Check
the server returns the verified Verilog immediately (`COMBA_SKIP_TB_IF_NO_GOLDEN=1`).
Batch evaluation always ships golden testbenches and is therefore unaffected even when
the flag is set.

---

## Quick tests (curl)

```bash
# Non-streaming design request
curl -s http://localhost:8100/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"comba-verilog-pipeline","stream":false,
       "messages":[{"role":"user","content":"Design a 2-input AND gate named and2 with inputs a, b and output y."}]}'

# Streaming design request (per-node SSE)
curl -sN http://localhost:8100/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"comba-verilog-pipeline","stream":true,
       "messages":[{"role":"user","content":"Design a 10-bit adder named add_10bit ..."}]}'
```

---

## Troubleshooting

| Symptom | Cause / Fix |
|---|---|
| `address already in use` on launch | A server is already bound to `:8100`. Use another port or stop the old one. |
| Blank response that never finishes | An old build that buffered the stream — restart the server to pick up the current `api_server.py`. |
| Lots of `XML invalid ... line 1, column 0` in logs | Open WebUI title/tag/follow-up requests. Handled by the bypass; restart to pick it up, or disable those features in Open WebUI. |
| Request stalls at *"No testbench found. Calling LLM/Debugger…"* | Full TB-sim flow is on. Keep `COMBA_SKIP_TB_IF_NO_GOLDEN=1` (default) for interactive use. |
| `/health/llm` shows a backend `error` | The corresponding vLLM server (`:8000`/`:8001`) is down. Restart with `./launch_dual_gpu.sh`. |

---
Maintainer: Vu-Minh-Thanh Nguyen (nvmthanh@hcmus.edu.vn), Ngoc-Thien-Kim Nguyen (nntkim.work@gmail.com)
