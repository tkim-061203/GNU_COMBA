#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd "$SCRIPT_DIR/langgraph_core" || { echo "No langgraph_core folder"; exit 1; }

python api_server.py
