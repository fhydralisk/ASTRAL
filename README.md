> Architecture update: the React/Next.js app is in `web/`; run the independent Harness with `astral serve`. See [deployment and development](deploy/decoupled/README.md). The legacy `astral run` WebUI has been removed. Historical data is not migrated.

# ASTRAL

**A human–AI interactive astronomy discovery platform, built on [SRHarness](https://github.com/yuzhTHU/SRHarness).**

[English](README.md) | [简体中文](README.zh.md)

[![GitHub](https://img.shields.io/github/stars/yuzhTHU/ASTRAL?style=flat&logo=github&label=GitHub)](https://github.com/yuzhTHU/ASTRAL)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.12-173b73?logo=python&logoColor=white)](pyproject.toml)
[![License](https://img.shields.io/github/license/yuzhTHU/ASTRAL)](LICENSE)

ASTRAL brings interactive scientific data preparation, agent-assisted symbolic regression, formula evaluation, and human guidance into one research workbench. It starts from SRHarness and is being developed toward astronomy discovery workflows.

Astronomy datasets, domain knowledge, and dedicated astronomy skills are planned extensions. The current platform provides the inherited scientific workflow with ASTRAL branding and a deep-blue theme in both light and dark modes.

## Current capabilities

- Persistent conversations and workspaces for iterative scientific investigation.
- Interactive data preparation and task configuration.
- Composable analysis, fitting, and evaluation tools.
- Custom Evaluators, interpretable candidate formulas, and search diagnostics.
- Human guidance throughout the search, with Chinese and English interfaces.

## Install from source

Requires Python 3.12 or newer. ASTRAL is currently installed from source; PyPI and Docker Hub publishing are not configured.

```bash
git clone git@github.com:yuzhTHU/ASTRAL.git
cd ASTRAL
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

The distribution and CLI are named `astral`. Python imports retain the upstream `sr_harness` and `sr_harness_engine` module names to support ongoing upstream integration.

## Launch the workbench

The Next.js/React frontend and backend live in `web/` and control an independent Harness over internal HTTP. Follow the [deployment and development guide](deploy/decoupled/README.md) to start the root Compose stack with Next.js, Harness and PostgreSQL.

For local development, configure `HARNESS_SERVICE_TOKEN` and start the scientific runtime:

```bash
astral serve --host 127.0.0.1 --port 8000 --root ./harness-data
```

In a second terminal, enter `web/`, configure `.env.local`, then run `npm ci`, `npm run db:migrate` and `npm run dev`. Open `http://localhost:3000`. Secure Harness workspaces and sandbox execution require Linux.

The workbench uses account login. Registration defaults to open; administrators can switch to invitation-only or administrator-created accounts. Next.js owns model configurations, encrypts keys in its database, and supplies them to Harness on demand. Legacy WebUI data is not migrated.

For a synthetic symbolic-regression example, configure `OPENROUTER_API_KEY`, then run:

```bash
astral synthetic \
  --equation 'y = 1 + x1 ** 2 + 2 * x1 * x2' \
  --n-samples 200 \
  --seed 42 \
  --llm-provider openrouter \
  --llm-model deepseek/deepseek-v4-flash-0731 \
  --save-path ./logs/quick-start
```

## Upstream integration

ASTRAL is an independent repository that preserves SRHarness history. Use `origin` for ASTRAL and `upstream` for SRHarness:

```bash
git remote add upstream git@github.com:yuzhTHU/SRHarness.git
git fetch upstream
git switch -c sync/srharness main
git merge upstream/master
```

Resolve conflicts and validate the result before merging the sync branch into `main`. Preserve upstream ancestry with a regular merge commit.

## Documentation and attribution

The inherited engine and workflow are described in the [SRHarness documentation](https://yuzhthu.github.io/SRHarness/) and the local [docs](docs/) directory. Those documents may still use the upstream project name and `sr-harness` command; use `astral` for this project.

ASTRAL builds on [SRHarness](https://github.com/yuzhTHU/SRHarness), described in [SRHarness: A Harness for Agentic Symbolic Regression](https://arxiv.org/abs/2609.35501). The upstream project’s research results should be attributed to SRHarness.

Released under the [MIT License](LICENSE).
