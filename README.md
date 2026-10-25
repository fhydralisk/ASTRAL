# SRHarness: A Harness for Agentic Symbolic Regression

[English](README.md) | [简体中文](README.zh.md)

[![GitHub](https://img.shields.io/github/stars/yuzhTHU/SRHarness?style=flat&logo=github&label=GitHub)](https://github.com/yuzhTHU/SRHarness)
[![PyPI](https://img.shields.io/pypi/v/sr-harness?logo=pypi&logoColor=white)](https://pypi.org/project/sr-harness/)
[![Docker](https://img.shields.io/docker/v/yumeoww/sr-harness?sort=semver&logo=docker&logoColor=white&label=Docker)](https://hub.docker.com/r/yumeoww/sr-harness)
[![Documentation](https://img.shields.io/badge/docs-GitHub%20Pages-4e968b?logo=materialformkdocs&logoColor=white)](https://yuzhthu.github.io/SRHarness/)
[![Live WebUI](https://img.shields.io/badge/WebUI-live-4e968b?logo=googlechrome&logoColor=white)](http://sim1.fiblab.tech:30000/)
[![Hugging Face WebUI](https://img.shields.io/badge/WebUI-Hugging%20Face-ffd21e?logo=huggingface&logoColor=black)](https://yumeow-srharness.hf.space/)
[![arXiv](https://img.shields.io/badge/arXiv-2609.35501-b31b1b?logo=arxiv&logoColor=white)](https://arxiv.org/abs/2609.35501)
[![Documentation build](https://github.com/yuzhTHU/SRHarness/actions/workflows/docs.yml/badge.svg?branch=dev)](https://github.com/yuzhTHU/SRHarness/actions/workflows/docs.yml)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.12-3776AB?logo=python&logoColor=white)](https://pypi.org/project/sr-harness/)
[![License](https://img.shields.io/github/license/yuzhTHU/SRHarness)](LICENSE)

SRHarness is a research runtime and interactive workbench for **agentic symbolic regression**. Instead of relying on blind expression search or unverified model guesses, SRHarness equips language-model agents with scientific tools to prepare data, analyze variable relationships, fit parameters, diagnose residuals, and iteratively refine interpretable formulas. It also provides a browser-based workbench with persistent conversations, visual data exploration, and customizable formula evaluators (`Evaluator`).

## Key Capabilities

- **Composable scientific tools:** Statistical diagnostics, curve fitting, external symbolic-regression backends (PySR, SINDy), sandboxed Python execution, and formula evaluation share a unified `BaseTool` interface.
- **Persistent search state:** Every evaluated candidate, metric, residual profile, and search node is tracked across turns to maintain a global Top-k leaderboard and accuracy–complexity Pareto front.
- **Structured `R-C-L-K` search tree:** Coordinates outer restarts (`R`), parallel conversation branches (`C`), iterative refinement steps (`L`), and per-step local response sampling (`K`).
- **End-to-end interactive workbench:** A three-stage WebUI guides workflows through data preparation, task & Evaluator configuration, and human-in-the-loop symbolic regression.
- **Expressive symbolic engine:** `sr_harness_engine` supports scalar expressions, named and category-grouped parameters, directed graphs, ternary hypergraphs, and time delays.

## Benchmark Results

Our [paper](https://arxiv.org/abs/2609.35501) evaluates SRHarness on **LLM-SRBench** using matched language-model backbones. **LSR-Transform** tests symbolic recovery on transformed scientific equations, while **LSR-Transform-Anon** strips domain descriptions and variable names to test discovery from numerical patterns alone. The table below reports Symbolic Accuracy (SA):

| Method / Backbone | LSR-Transform | LSR-Transform-Anon |
|---|---:|---:|
| SRHarness + DeepSeek-v4-flash-0731 | **93.69%** | **72.97%** |
| SR-Scientist + DeepSeek-v4-flash-0731 | 62.16% | 39.64% |
| Codex + DeepSeek-v4-flash-0731 | — | 20.72% |

Using the same `DeepSeek-v4-flash-0731` backbone, SRHarness improves symbolic recovery by over 31 percentage points on both settings compared with SR-Scientist, and outperforms Codex by more than 52 percentage points on the anonymized benchmark. These gains show that coupling language models with structured scientific tools, persistent candidate tracking, and `R-C-L-K` trajectory management is essential for reliable equation discovery. See the paper for the full evaluation protocol, out-of-domain generalization results, cost analyses, and ablation studies.

## Installation

SRHarness requires Python 3.12 or newer:

```bash
pip install sr-harness
```

See the [installation guide](https://yuzhthu.github.io/SRHarness/install/) for LLM provider API key setup, optional extras (`tools`, `nn`, `dev`), Docker usage, and source installation.

### Hugging Face Spaces

You can try the hosted WebUI directly at <https://yumeow-srharness.hf.space/>. Version releases on `master` update this Space automatically alongside PyPI and Docker Hub.

To deploy your own Docker Space, use the [Space README template](deploy/huggingface/README.space.md) and follow the [Hugging Face deployment guide](deploy/huggingface/README.md) for credential configuration, persistent storage, and security settings.

## Quick Start

### 1. Recover a synthetic equation from the CLI: `sr-harness synthetic`

Set `OPENROUTER_API_KEY`, then run `sr-harness synthetic` to sample data from a known formula and test whether `SRAgent` can rediscover it:

```bash
sr-harness synthetic \
  --equation 'y = 1 + x1 ** 2 + 2 * x1 * x2' \
  --n-samples 200 \
  --x-low -2 \
  --x-high 2 \
  --seed 42 \
  --llm-provider openrouter \
  --llm-model deepseek/deepseek-v4-flash-0731 \
  --save-path ./logs/quick-start \
  -R 1 -C 1 -L 10 -K 1
```

To use another provider (such as DeepSeek, OpenAI, Gemini, or SiliconFlow), export its API key and update `--llm-provider` and `--llm-model`.

### 2. Launch the interactive workbench: `sr-harness run`

Start the local WebUI server for interactive data preparation, task and Evaluator setup, live search-tree inspection, and mid-run guidance:

```bash
sr-harness run \
  --host 127.0.0.1 \
  --port 8000 \
  --workspace-dir ./workspaces \
  --save-path ./logs/webui
```

Open <http://127.0.0.1:8000/> in your browser. Conversation workspaces and the chat registry are stored under `./workspaces`, while session snapshots and search records are saved under `./logs/webui`. You can also try the hosted instances at <http://sim1.fiblab.tech:30000/> and <https://yumeow-srharness.hf.space/>.

## Documentation

- [Overview](https://yuzhthu.github.io/SRHarness/)
- [Quick Start](https://yuzhthu.github.io/SRHarness/quick-start/)
- [Installation and Provider Configuration](https://yuzhthu.github.io/SRHarness/install/)
- [CLI Reference (`run`, `synthetic`, `tool`, `benchmark`)](https://yuzhthu.github.io/SRHarness/sr-harness/)
- [SRHarness Agent Workflow](https://yuzhthu.github.io/SRHarness/agent/)
- [Core Abstractions (`BaseTool` and `BaseParser`)](https://yuzhthu.github.io/SRHarness/core-abstractions/)
- [Structured Data and `context.data`](https://yuzhthu.github.io/SRHarness/context-data/)
- [Formula Evaluation and Custom Evaluators](https://yuzhthu.github.io/SRHarness/evaluator/)
- [SRHarness WebUI Guide](https://yuzhthu.github.io/SRHarness/web-ui/)
- [SRHarness Engine](https://yuzhthu.github.io/SRHarness/engine/)
- [API Reference](https://yuzhthu.github.io/SRHarness/reference/)

## Citation

```bibtex
@article{yu2026srharness,
  title   = {SRHarness: A Harness for Agentic Symbolic Regression},
  author  = {Yu, Zihan and Zhou, Shixuan and Huang, Hao and Ding, Jingtao and Li, Yong},
  journal = {arXiv preprint arXiv:2609.35501},
  year    = {2026}
}
```

## License

SRHarness is released under the [MIT License](LICENSE).
