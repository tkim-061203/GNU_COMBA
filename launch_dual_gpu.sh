#!/bin/bash
# ============================================================
# launch_dual_gpu.sh — 2× RTX 5880 Ada Deployment
# ============================================================
#
#   GPU 0 (port 8000): Base Qwen           → Process ⓪ + Agent 1
#   GPU 1 (port 8001): Merged LoRA model   → Process ① (Correcter)
#
# Usage:
#   ./launch_dual_gpu.sh                # start
#   ./launch_dual_gpu.sh --stop         # stop
#   ./launch_dual_gpu.sh --status       # check
#   ./launch_dual_gpu.sh --restart      # restart
#   ./launch_dual_gpu.sh --logs         # show logs

set -euo pipefail

# ── Config ──
GENERATED_MODEL="${GENERATED_MODEL:-/home/nntkim/Downloads/model}"
MERGED_MODEL="${MERGED_MODEL:-/home/nntkim/Downloads/model_debugger}"
PORT_GEN=8000
PORT_DBG=8001
MAX_MODEL_LEN=16384
GPU_MEM=0.92
CACHE_DIR="../../hf_model_cache"
DTYPE="bfloat16"
LOG_DIR="./logs"

# ── Parse Args ──
ACTION="start"
while [[ $# -gt 0 ]]; do
    case $1 in
        --base-model)    GENERATED_MODEL="$2"; shift 2 ;;
        --merged-model)  MERGED_MODEL="$2"; shift 2 ;;
        --stop)          ACTION="stop"; shift ;;
        --status)        ACTION="status"; shift ;;
        --restart)       ACTION="restart"; shift ;;
        --logs)          ACTION="logs"; shift ;;
        -h|--help)
            echo "Usage: $0 [--base-model PATH] [--merged-model PATH] [--stop] [--status] [--restart] [--logs]"
            exit 0 ;;
        *) echo "Unknown: $1"; exit 1 ;;
    esac
done

# ── Functions ──

check_gpu() {
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║    2× RTX 5880 Ada — COMBA-PROMPT Dual Model             ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    echo ""

    if ! command -v nvidia-smi &> /dev/null; then
        echo "❌ nvidia-smi not found"; exit 1
    fi

    GPU_COUNT=$(nvidia-smi --query-gpu=name --format=csv,noheader | wc -l)
    if [[ $GPU_COUNT -lt 2 ]]; then
        echo "❌ Only $GPU_COUNT GPU(s) detected. Need 2 GPUs."
        exit 1
    fi

    echo "🖥️  GPU Configuration:"
    nvidia-smi --query-gpu=index,name,memory.total,memory.free --format=csv,noheader | while read line; do
        echo "   $line"
    done
    echo ""
}

stop_servers() {
    echo "🛑 Stopping vLLM servers..."
    for PORT in $PORT_GEN $PORT_DBG; do
        PID=$(lsof -ti:$PORT 2>/dev/null || true)
        if [[ -n "$PID" ]]; then
            kill $PID 2>/dev/null && echo "   Killed process $PID on port $PORT" || true
        fi
    done
    pkill -f "vllm.entrypoints.openai.api_server" 2>/dev/null || true
    sleep 2
    echo "✅ All servers stopped"
}

check_status() {
    echo "📊 Server Status:"
    for PORT in $PORT_GEN $PORT_DBG; do
        LABEL="Generator"; [[ $PORT == $PORT_DBG ]] && LABEL="Debugger "
        if curl -s "http://localhost:$PORT/health" > /dev/null 2>&1; then
            echo "   ✅ $LABEL (:$PORT) — RUNNING"
        else
            echo "   ❌ $LABEL (:$PORT) — DOWN"
        fi
    done
    echo ""
    nvidia-smi --query-gpu=index,memory.used,memory.free,utilization.gpu --format=csv,noheader 2>/dev/null || true
}

tail_logs() {
    echo "📋 Tailing logs (Ctrl+C to stop)..."
    mkdir -p $LOG_DIR
    touch $LOG_DIR/vllm_gpu0_generator.log $LOG_DIR/vllm_gpu1_debugger.log
    tail -f $LOG_DIR/vllm_gpu0_generator.log $LOG_DIR/vllm_gpu1_debugger.log
}

start_dual() {
    if [[ ! -d "$MERGED_MODEL" ]]; then
        echo "❌ Merged model not found: $MERGED_MODEL"
        echo "   Run: llamafactory-cli export your_config.yaml"
        exit 1
    fi

    echo "📋 Configuration:"
    echo "   GPU 0: $GENERATED_MODEL"
    echo "   GPU 1: $MERGED_MODEL"
    echo ""

    mkdir -p $LOG_DIR

    # ── GPU 0: Base Qwen ──
    echo "🔵 Starting Generator on GPU 0 (:$PORT_GEN)..."
    CUDA_VISIBLE_DEVICES=0 nohup python -m vllm.entrypoints.openai.api_server \
        --model $GENERATED_MODEL \
        --download-dir $CACHE_DIR \
        --served-model-name generator \
        --dtype $DTYPE \
        --max-model-len $MAX_MODEL_LEN \
        --gpu-memory-utilization $GPU_MEM \
        --port $PORT_GEN \
        --host 0.0.0.0 \
        --trust-remote-code \
        > $LOG_DIR/vllm_gpu0_generator.log 2>&1 &
    echo "   PID: $! → log: $LOG_DIR/vllm_gpu0_generator.log"

    # ── GPU 1: Merged LoRA model ──
    echo "🔴 Starting Debugger on GPU 1 (:$PORT_DBG)..."
    CUDA_VISIBLE_DEVICES=1 nohup python -m vllm.entrypoints.openai.api_server \
        --model $MERGED_MODEL \
        --served-model-name debugger \
        --dtype $DTYPE \
        --max-model-len $MAX_MODEL_LEN \
        --gpu-memory-utilization $GPU_MEM \
        --port $PORT_DBG \
        --host 0.0.0.0 \
        --trust-remote-code \
        > $LOG_DIR/vllm_gpu1_debugger.log 2>&1 &
    echo "   PID: $! → log: $LOG_DIR/vllm_gpu1_debugger.log"

    # ── Wait ──
    echo ""
    echo ""
    echo "⏳ Waiting for servers (~30-60s)..."
    echo "📝 Streaming logs while waiting (will stop once ready):"
    echo "--------------------------------------------------------"
    
    # Start tailing logs in the background
    tail -n 0 -f $LOG_DIR/vllm_gpu0_generator.log $LOG_DIR/vllm_gpu1_debugger.log &
    TAIL_PID=$!
    
    # Cleanup tail process on exit
    trap "kill $TAIL_PID 2>/dev/null || true" EXIT

    for PORT in $PORT_GEN $PORT_DBG; do
        LABEL="Generator"; [[ $PORT == $PORT_DBG ]] && LABEL="Debugger"
        for i in $(seq 1 120); do
            if curl -s "http://localhost:$PORT/health" > /dev/null 2>&1; then
                echo -e "\n   ✅ $LABEL (:$PORT) ready (${i}s)"
                break
            fi
            [[ $i -eq 120 ]] && echo -e "\n   ⚠️  $LABEL (:$PORT) timeout — check logs"
            sleep 1
        done
    done

    # Kill background tail process
    kill $TAIL_PID 2>/dev/null || true
    trap - EXIT # Clear trap

    echo "--------------------------------------------------------"
    echo ""
    echo "✅ Both servers running!"
    echo "   Generator: http://localhost:$PORT_GEN/v1  model=\"generator\""
    echo "   Debugger:  http://localhost:$PORT_DBG/v1  model=\"debugger\""
    echo ""
    nvidia-smi --query-gpu=index,memory.used,memory.free --format=csv,noheader 2>/dev/null || true
}

# ── Main ──
case $ACTION in
    start)   check_gpu; start_dual ;;
    stop)    stop_servers ;;
    status)  check_status ;;
    restart) stop_servers; sleep 3; check_gpu; start_dual ;;
    logs)    tail_logs ;;
esac