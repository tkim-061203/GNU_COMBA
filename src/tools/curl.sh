#!/bin/bash

HF_TOKEN=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
# curl "https://bz6n4l2qjijovmw2.us-east-1.aws.endpoints.huggingface.cloud/v1/models" \
# -X GET \
# -H "Authorization: Bearer $HF_TOKEN"

curl "https://bz6n4l2qjijovmw2.us-east-1.aws.endpoints.huggingface.cloud/v1/chat/completions" \
-X POST \
-H "Authorization: Bearer $HF_TOKEN" \
-H "Content-Type: application/json" \
-d '{
    "model": "nvmthanhhcmus/MIHA-DeepSeek-Coder-Pyranet-GGUF",
    "messages": [
        {
            "role": "user",
            "content": "What is deep learning?"
        }
    ],
    "max_tokens": 100
}'