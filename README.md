# AstroDiscovery

**A human–AI interactive astronomy discovery platform, built on [SRHarness](https://github.com/yuzhTHU/SRHarness).**

[English](README.md) | [简体中文](README.zh.md)

[![GitHub](https://img.shields.io/github/stars/yuzhTHU/AstroDiscovery?style=flat&logo=github&label=GitHub)](https://github.com/yuzhTHU/AstroDiscovery)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.12-173b73?logo=python&logoColor=white)](pyproject.toml)
[![License](https://img.shields.io/github/license/yuzhTHU/AstroDiscovery)](LICENSE)

AstroDiscovery brings interactive scientific data preparation, agent-assisted symbolic regression, formula evaluation, and human guidance into one research workbench. It starts from SRHarness and is being developed toward astronomy discovery workflows.

Astronomy datasets, domain knowledge, and dedicated astronomy skills are planned extensions. The current platform provides the inherited scientific workflow with AstroDiscovery branding and a deep-blue theme in both light and dark modes.

## Current capabilities

- Persistent conversations and workspaces for iterative scientific investigation.
- Interactive data preparation and task configuration.
- Composable analysis, fitting, and evaluation tools.
- Custom Evaluators, interpretable candidate formulas, and search diagnostics.
- Human guidance throughout the search, with Chinese and English interfaces.

## Install from source

Requires Python 3.12 or newer. AstroDiscovery is currently installed from source; PyPI and Docker Hub publishing are not configured.

```bash
git clone git@github.com:yuzhTHU/AstroDiscovery.git
cd AstroDiscovery
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

The distribution and CLI are named `astro-discovery`. Python imports retain the upstream `sr_harness` and `sr_harness_engine` module names to support ongoing upstream integration.

## Launch the workbench

```bash
astro-discovery run \
  --host 0.0.0.0 \
  --port 11002 \
  --workspace-dir ./workspaces \
  --save-path ./logs/webui
```

Open `http://localhost:11002` on the server, or `http://SERVER_IP:11002` from another machine. Configure a model provider, model, and API key in the workbench before running an agent. See [.env.sample](.env.sample) for provider configuration examples.

The workspace and log arguments retain conversations and run artifacts across restarts. Omitting them uses a temporary workspace.

For a synthetic symbolic-regression example, configure `OPENROUTER_API_KEY`, then run:

```bash
astro-discovery synthetic \
  --equation 'y = 1 + x1 ** 2 + 2 * x1 * x2' \
  --n-samples 200 \
  --seed 42 \
  --llm-provider openrouter \
  --llm-model deepseek/deepseek-v4-flash-0731 \
  --save-path ./logs/quick-start
```

## Upstream integration

AstroDiscovery is an independent repository that preserves SRHarness history. Use `origin` for AstroDiscovery and `upstream` for SRHarness:

```bash
git remote add upstream git@github.com:yuzhTHU/SRHarness.git
git fetch upstream
git switch -c sync/srharness main
git merge upstream/master
```

Resolve conflicts and validate the result before merging the sync branch into `main`. Preserve upstream ancestry with a regular merge commit.

## Documentation and attribution

The inherited engine and workflow are described in the [SRHarness documentation](https://yuzhthu.github.io/SRHarness/) and the local [docs](docs/) directory. Those documents may still use the upstream project name and `sr-harness` command; use `astro-discovery` for this project.

AstroDiscovery builds on [SRHarness](https://github.com/yuzhTHU/SRHarness), described in [SRHarness: A Harness for Agentic Symbolic Regression](https://arxiv.org/abs/2609.35501). The upstream project’s research results should be attributed to SRHarness.

Released under the [MIT License](LICENSE).
