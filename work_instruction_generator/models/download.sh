#!/usr/bin/env bash

# Copyright Advanced Micro Devices, Inc.
#
# SPDX-License-Identifier: MIT

set -e

MARKER="/root/.cache/huggingface/hub/models--Qwen--Qwen3.5-9B/refs/main"

if [ -f "$MARKER" ]; then
    echo "Qwen/Qwen3.5-9B already cached — skipping download."
    exit 0
fi

echo "Downloading Qwen/Qwen3.5-9B (~19GB)..."
pip install -q huggingface_hub
python3 -c "
from huggingface_hub import snapshot_download
snapshot_download('Qwen/Qwen3.5-9B')
print('Download complete.')
"
