# Quick Start

Before starting, make sure you have completed [installation and provider configuration](install.md).

## 1. Recover a Known Equation from the CLI

The fastest way to see SRHarness in action is `sr-harness synthetic`. It generates synthetic data from a formula you provide, then challenges the Agent to rediscover that formula from the data alone.

The command below generates 200 samples with columns `x1`, `x2`, and `y`, where the true relationship is:

$$
y = 1 + x_1^2 + 2x_1x_2
$$

!!! tip
    Make sure you have configured the API key matching `--llm-provider`. The example below uses OpenRouter (`OPENROUTER_API_KEY`). If you use another provider such as DeepSeek or OpenAI, update `--llm-provider` and `--llm-model` accordingly.

Run the Agent with a small search budget:

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

The four budget flags control the shape of the search:

| Option | Meaning |
|---|---|
| `-R` | **Restarts**: Number of restart loops seeded with the best formulas found so far |
| `-C` | **Conversations**: Number of independent parallel branches per restart |
| `-L` | **Refinement Depth**: Maximum number of iterative turns per branch |
| `-K` | **Local Samples**: Number of model responses sampled at each turn |

All run logs and results are saved under `--save-path` (`./logs/quick-start`):

| File | Contents |
|---|---|
| `run.json` | Run ID, CLI arguments, and Agent configuration |
| `nodes.jsonl` | Every `(R, C, L, K)` conversation node and its parent links in the search tree |
| `result.json` | All evaluated formulas, the Pareto Front, and the final best candidate |
| `response.jsonl` | Raw LLM responses, token counts, and estimated cost |
| `tool_calls.jsonl` | Detailed records of every tool invocation and its return value |

## 2. Use the Interactive WebUI Workbench

For real-world datasets—where you often need to clean raw tables, compute derivatives, customize evaluation metrics, or steer the Agent mid-run—use the interactive WebUI workbench.

Start the server on port `8000` and store persistent workspaces and run logs in `./workspaces` and `./logs/webui`:

```bash
sr-harness run \
  --host 127.0.0.1 \
  --port 8000 \
  --workspace-dir ./workspaces \
  --save-path ./logs/webui
```

Open `http://127.0.0.1:8000/` in your browser and follow the three workflow tabs at the top:

1. **Data Preparation**: Upload raw files (or pick a built-in sample dataset) and ask the Data Preparation Agent to clean, transform, or validate your variables.
2. **Task Setup**: Choose the target and input features, describe their scientific meaning, and select or customize an Evaluator.
3. **Symbolic Regression**: Launch the search, watch the live reasoning timeline and search tree, and pause anytime to inject guidance or refine your variables and evaluation metric.

![SRHarness symbolic-regression workbench](https://yuzhthu.github.io/SRHarness/assets/webui-symbolic-regression.png)

For a full walkthrough, see [SRHarness WebUI](web-ui.md).

### Mount Read-Only Local Datasets

If your datasets are large or you want to ensure the Agent never modifies the original files, mount them with `--mount`:

```bash
sr-harness run \
  --workspace-dir ./workspaces \
  --mount ./datasets ./papers/model.pdf
```

Mounted files and folders appear as read-only links inside every conversation workspace, saving disk space and protecting your source data. When mounting multiple paths, make sure their top-level filenames or directory names do not collide.

## 3. Try the Hosted WebUI

If you want to try SRHarness without installing anything locally, open our [hosted WebUI workbench](http://sim1.fiblab.tech:30000/) directly in your browser.
