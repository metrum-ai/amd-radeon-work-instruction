<!--
Copyright Advanced Micro Devices, Inc.

SPDX-License-Identifier: MIT
-->
# Release Notes

## v1.0

### Features

* **Privacy-Preserving On-Prem AI Infrastructure**: All AI runs locally on 4× **AMD Radeon AI PRO R9700S** GPUs — `Qwen/Qwen3.5-9B`, `google/gemma-4-E2B-it` ×2, and `Flux-2-Klein-4B-GGUF` ×2 — so manuals, SOPs, and generated instructions never leave the plant network.

* **Automated Multi-Agent Harmonization Engine**: Specialized agents ingest mismatched multi-vendor OEM manuals (German ZYRO, Japanese Nexora, US Veltrix), normalize vendor terminology to plant standard, and re-render source figures into one consistent technical-diagram style via `Flux`.

* **State-Aware Dynamic Instruction Delivery**: Steps are authored against station telemetry (nozzle temperature, lens status, HV de-energized state — live for 3 simulated stations) and hard safety interlocks (LOTO, PPE, purge, fixture, lens), blocking or passing steps accordingly — on demand for any station.

* **Tribal Knowledge Capture & Operational Continuity**: A step can be refined with a free-text instruction; the fix is captured as tribal knowledge via the review chat and the step (and its illustration) is regenerated in place.

---

### Components

#### Python Libraries

| Component | Version | License |
|-----------|---------|---------|
| FastAPI | 0.124.2  / 0.139.0 | [MIT](https://github.com/fastapi/fastapi/blob/master/LICENSE) |
| Uvicorn | 0.38.0 / 0.49.0 | [BSD-3-Clause](https://github.com/encode/uvicorn/blob/master/LICENSE.md) |
| httpx | 0.28.1 | [BSD-3-Clause](https://github.com/encode/httpx/blob/master/LICENSE.md) |
| Pydantic | 2.11.0 | [MIT](https://github.com/pydantic/pydantic/blob/main/LICENSE) |
| pydantic-settings | 2.11.0 | [MIT](https://github.com/pydantic/pydantic-settings/blob/main/LICENSE) |
| PyYAML | 6.0.2  / 6.0.3  | [MIT](https://github.com/yaml/pyyaml/blob/master/LICENSE) |
| prometheus-client | 0.21.1 | [Apache-2.0](https://github.com/prometheus/client_python/blob/master/LICENSE) |
| python-multipart | 0.0.19 | [Apache-2.0](https://github.com/Kludex/python-multipart/blob/master/LICENSE.txt) |
| Pillow | 10.4.0 | [HPND](https://github.com/python-pillow/Pillow/blob/10.4.0/LICENSE) |
| Pillow | 12.3.0 | [MIT-CMU](https://github.com/python-pillow/Pillow/blob/main/LICENSE) |
| numpy | 2.2.3 | [BSD-3-Clause](https://github.com/numpy/numpy/blob/main/LICENSE.txt) |
| opencv-python-headless | 4.10.0.84 | [MIT](https://github.com/opencv/opencv-python/blob/4.x/LICENSE.txt) (wrapper) AND [Apache-2.0](https://github.com/opencv/opencv/blob/4.x/LICENSE) (bundled OpenCV) |
| WeasyPrint | 63.1 | [BSD-3-Clause](https://github.com/Kozea/WeasyPrint/blob/main/LICENSE) |
| Jinja2 | 3.1.5 | [BSD-3-Clause](https://github.com/pallets/jinja/blob/main/LICENSE.txt) |
| asyncpg | 0.31.0 | [Apache-2.0](https://github.com/MagicStack/asyncpg/blob/master/LICENSE) |
| mcp (Model Context Protocol SDK) | 1.28.1 | [MIT](https://github.com/modelcontextprotocol/python-sdk/blob/main/LICENSE) |
| openai (Python SDK) | 2.44.0 | [Apache-2.0](https://github.com/openai/openai-python/blob/main/LICENSE) |
| pymilvus | 2.5.18 | [Apache-2.0](https://github.com/milvus-io/pymilvus/blob/master/LICENSE) |
| mqtt-spb-wrapper | 2.1.2 | [EPL-2.0](https://github.com/javier-fg/mqtt-spb-wrapper/blob/main/LICENSE) |
| sentence-transformers | 5.6.0 | [Apache-2.0](https://github.com/UKPLab/sentence-transformers/blob/master/LICENSE) |
| langdetect | 1.0.9 | [Apache-2.0](https://github.com/Mimino666/langdetect/blob/master/LICENSE) |
| pdfplumber | 0.11.10 | [MIT](https://github.com/jsvine/pdfplumber/blob/stable/LICENSE.txt) |
| pypdf | 6.14.2 | [BSD-3-Clause](https://github.com/py-pdf/pypdf/blob/main/LICENSE) |

#### System Libraries

| Component | Version | License |
|-----------|---------|---------|
| Mesa / libgl1 | system apt (`libgl1-mesa-glx`) | [MIT](https://www.mesa3d.org/license.html) |
| GLib (`libglib2.0-0`) | system apt | [LGPL-2.1-or-later](https://gitlab.gnome.org/GNOME/glib/-/blob/main/COPYING) |
| Pango (`libpango-1.0-0`, `libpangocairo-1.0-0`) | system apt | [LGPL-2.0-or-later](https://gitlab.gnome.org/GNOME/pango/-/blob/main/COPYING) |
| Cairo (via `libpangocairo-1.0-0`) | system apt | [LGPL-2.1-or-later](https://gitlab.freedesktop.org/cairo/cairo/-/blob/master/COPYING-LGPL-2.1) OR [MPL-1.1](https://gitlab.freedesktop.org/cairo/cairo/-/blob/master/COPYING-MPL-1.1) |
| GDK-Pixbuf (`libgdk-pixbuf2.0-0`) | system apt | [LGPL-2.1-or-later](https://gitlab.gnome.org/GNOME/gdk-pixbuf/-/blob/main/COPYING) |
| libffi | system apt | [MIT](https://github.com/libffi/libffi/blob/master/LICENSE) |
| shared-mime-info | system apt | [GPL-2.0-or-later](https://gitlab.freedesktop.org/xdg/shared-mime-info/-/raw/master/COPYING) |

#### Frontend

| Component | Version | License |
|-----------|---------|---------|
| React | 19.2.7 | [MIT](https://github.com/facebook/react/blob/main/LICENSE) |
| react-dom | 19.2.7 | [MIT](https://github.com/facebook/react/blob/main/LICENSE) |
| ECharts | 6.1.0 | [Apache-2.0](https://github.com/apache/echarts/blob/master/LICENSE) |
| echarts-for-react | 3.0.6 | [MIT](https://github.com/hustcc/echarts-for-react/blob/master/LICENSE) |
| jsPDF | 4.2.1 | [MIT](https://github.com/parallax/jsPDF/blob/master/LICENSE) |
| lucide-react | 0.511.0 | [ISC](https://github.com/lucide-icons/lucide/blob/main/LICENSE) |
| TypeScript | 5.8.3 | [Apache-2.0](https://github.com/microsoft/TypeScript/blob/main/LICENSE.txt) |
| Vite | 6.4.3 | [MIT](https://github.com/vitejs/vite/blob/main/LICENSE) |
| @vitejs/plugin-react | 4.7.0 | [MIT](https://github.com/vitejs/vite-plugin-react/blob/main/LICENSE) |

#### Base Docker Images

| Image | License |
|-------|---------|
| `python:3.12.10-slim-bookworm` | [PSF-2.0](https://docs.python.org/3/license.html) |
| `python:3.12-slim` | [PSF-2.0](https://docs.python.org/3/license.html) |
| `node:20-alpine` | [MIT](https://github.com/nodejs/node/blob/main/LICENSE) |
| `nginxinc/nginx-unprivileged:alpine` | [BSD-2-Clause](https://github.com/nginx/nginx/blob/master/LICENSE) |
| `nginx:1.27-alpine` | [BSD-2-Clause](https://github.com/nginx/nginx/blob/master/LICENSE) |
| `postgres:16.4-alpine3.20` | [PostgreSQL](https://www.postgresql.org/about/licence/) |
| `nats:2.10.22-alpine3.20` | [Apache-2.0](https://github.com/nats-io/nats-server/blob/main/LICENSE) |
| `quay.io/coreos/etcd:v3.5.5` | [Apache-2.0](https://github.com/etcd-io/etcd/blob/main/LICENSE) |
| `rustfs/rustfs:1.0.0-beta.3` | [Apache-2.0](https://github.com/rustfs/rustfs/blob/main/LICENSE) |
| `milvusdb/milvus:v2.4.6` | [Apache-2.0](https://github.com/milvus-io/milvus/blob/master/LICENSE) |
| `eclipse-mosquitto:2.0` | [EPL-2.0](https://github.com/eclipse-mosquitto/mosquitto/blob/master/epl-v20) OR [EDL-1.0](https://github.com/eclipse-mosquitto/mosquitto/blob/master/edl-v10) |
| `vllm/vllm-openai-rocm:v0.24.0` | [Apache-2.0](https://github.com/vllm-project/vllm/blob/main/LICENSE) |
| `ghcr.io/lemonade-sdk/lemonade-server:v10.8.0` | [Apache-2.0](https://github.com/lemonade-sdk/lemonade/blob/main/LICENSE) |
| `rocm/device-metrics-exporter:v1.4.2` | [Apache-2.0](https://github.com/ROCm/device-metrics-exporter/blob/main/LICENSE) |
| `prom/node-exporter:v1.8.2` | [Apache-2.0](https://github.com/prometheus/node_exporter/blob/master/LICENSE) |
| `prom/prometheus:v2.51.2` | [Apache-2.0](https://github.com/prometheus/prometheus/blob/main/LICENSE) |
| `ghcr.io/openclaw/openclaw:2026.6.9-slim` | [MIT](https://github.com/openclaw/openclaw/blob/main/LICENSE) |

#### Infrastructure Services

| Component | Version | License |
|-----------|---------|---------|
| PostgreSQL | 16.4 | [PostgreSQL](https://www.postgresql.org/about/licence/) |
| NATS Server | 2.10.22 | [Apache-2.0](https://github.com/nats-io/nats-server/blob/main/LICENSE) |
| etcd | v3.5.5 | [Apache-2.0](https://github.com/etcd-io/etcd/blob/main/LICENSE) |
| RustFS | 1.0.0-beta.3 | [Apache-2.0](https://github.com/rustfs/rustfs/blob/main/LICENSE) |
| Milvus | v2.4.6 | [Apache-2.0](https://github.com/milvus-io/milvus/blob/master/LICENSE) |
| Eclipse Mosquitto | 2.0 | [EPL-2.0](https://github.com/eclipse-mosquitto/mosquitto/blob/master/epl-v20) OR [EDL-1.0](https://github.com/eclipse-mosquitto/mosquitto/blob/master/edl-v10) |
| vLLM (ROCm) | v0.24.0 | [Apache-2.0](https://github.com/vllm-project/vllm/blob/main/LICENSE) |
| Lemonade Server | v10.8.0 | [Apache-2.0](https://github.com/lemonade-sdk/lemonade/blob/main/LICENSE) |
| Prometheus | v2.51.2 | [Apache-2.0](https://github.com/prometheus/prometheus/blob/main/LICENSE) |
| node-exporter | v1.8.2 | [Apache-2.0](https://github.com/prometheus/node_exporter/blob/master/LICENSE) |
| AMD Device Metrics Exporter | v1.4.2 | [Apache-2.0](https://github.com/ROCm/device-metrics-exporter/blob/main/LICENSE) |
| OpenClaw | 2026.6.9 | [MIT](https://github.com/openclaw/openclaw/blob/main/LICENSE) |

#### Models

| Component | License |
|-----------|---------|
| `Qwen/Qwen3.5-9B` (VLM / translation, GPU 0) | [Apache-2.0](https://huggingface.co/Qwen/Qwen3.5-9B) |
| `google/gemma-4-E2B-it` (instruction authoring, GPU 1) | [Apache-2.0](https://huggingface.co/google/gemma-4-E2B-it) |
| `unsloth/FLUX.2-klein-4B-GGUF` (illustration, GPU 2/3, via Lemonade) | [Apache-2.0](https://huggingface.co/unsloth/FLUX.2-klein-4B-GGUF) , based on [black-forest-labs/FLUX.2-klein-4B](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B) |
| `BAAI/bge-small-en-v1.5` (SOP/manual embeddings, RAG) | [MIT](https://huggingface.co/BAAI/bge-small-en-v1.5) |

---

### Known Issues

#### Application

- **First model load is slow** — Qwen3.5-9B, Gemma-4-E2B-it, and Flux/Lemonade all report unhealthy for several minutes on first boot while weights download and load onto GPU (vLLM start period ~20 minutes, Lemonade ~30 minutes).
- **Document ingestion is slow** — `oem-ingest` can take up to 15–20 minutes to ingest all OEM manual/SOP documents into Milvus on every stack bring-up. Monitor with `docker compose logs -f oem-ingest`.

---

### Documentation

| Document | Description |
| -------- | ----------- |
| **[Design](docs/design.md)** | Solution architecture, component glossary, and GPU/model layout |
