# SRHarness CLI Reference

All SRHarness CLI commands follow the pattern `sr-harness <command> [options]`:

| Command | Purpose |
|---|---|
| `serve` | Launch the interactive WebUI workbench |
| `synthetic` | Generate synthetic data from a formula and run a non-interactive search |
| `benchmark` | Evaluate SRHarness and other registered baselines on LLM-SRBench |
| `tool` | List available tools, inspect parameter schemas, or invoke a single tool |

## `astral serve`

Run the internal Harness API independently of Next.js:

```bash
export HARNESS_SERVICE_TOKEN='replace-with-at-least-24-random-characters'
astral serve --host 127.0.0.1 --port 8000 --root ./harness-data
```

| Option | Default | Meaning |
|---|---|---|
| `--host` | `127.0.0.1` | Bind address |
| `--port` | `8000` | Internal HTTP port |
| `--root` | `./harness-data` | Scientific sessions, workspaces and checkpoints |
| `--global-tasks` | `8` | Concurrent Agent tasks, including paused tasks |
| `--per-user-tasks` | `2` | Task limit per correlation tag `user_ref` |

This API does not serve browser pages or authenticate end users. All requests except `/health`
require the service Bearer token. Next.js owns accounts, conversation permissions and model
configurations. Browser access is through the Next.js server in `web/`.

See [deployment](../deploy/decoupled/README.md) and the generated `contracts/harness.openapi.json`.
The former `run`, `--isolate-users`, `--workspace-dir` and `--save-path` WebUI options are retired.
Scientific `synthetic`, `benchmark` and `tool` commands remain available through `astral`.

## `sr-harness synthetic`

`sr-harness synthetic` samples synthetic observations from a known equation and runs a non-interactive symbolic-regression search from the command line.

### Dataset options

| Option | Default | Description |
|---|---:|---|
| `-f`, `--equation` | `y = sin(x1 - x2)` | Ground-truth equation used to generate the target variable |
| `--features` | inferred | Space-separated observable feature names. Defaults to all variables on the right-hand side of the equation; specify explicitly to test nuisance features or omitted variables |
| `--n-samples` | `100` | Number of generated samples |
| `--seed` | `-1` | Random seed (`-1` uses the current system time) |
| `--x-low`, `--x-high` | `0.0`, `1.0` | Uniform sampling bounds for input features |
| `--noise-std-ratio` | `0.0` | Gaussian noise ratio added to the target (`noise_std = NOISE_STD_RATIO * std(target)`) |
| `--problem-description` | generated | Background problem description passed to the Agent |

### Model and tool options

| Option | Default | Description |
|---|---:|---|
| `--llm-provider` | `openrouter` | Base model provider |
| `--llm-model` | `deepseek/deepseek-v4-flash-0731` | Base model identifier |
| `--strong-llm-provider` | base provider | Provider for the strong model when automatic routing is enabled |
| `--strong-llm-model` | none | Optional stronger model used by automatic routing |
| `--llm-max-tokens` | automatic | Maximum output token limit per response (omit to use the provider default) |
| `--tool-parser` | `openai` | Tool-call format: `openai` (native function calling), `text`, `json`, or `xml` |
| `--tools` | default toolset | List of tools exposed to the Agent |
| `--ban-tools` | empty | Tools to exclude (ablate) from `--tools` |
| `--max-workers` | `0` | Worker count for parallel tool execution (`0` runs tools serially) |
| `--verbose` | off | Print detailed runtime logs |
| `--debug` | off | Enable verbose logs and halt immediately on unexpected exceptions |

### Search and evaluation

See [SRHarness Agent Workflow](agent.md#r-c-l-k-search) for how the four `R-C-L-K` dimensions work together.

| Option | Default | Description |
|---|---:|---|
| `-R`, `--max-restart-loop` | `1` | Number of restart loops |
| `-C`, `--global-width` | `1` | Parallel conversation branches per restart |
| `-L`, `--max-refinement-depth` | `30` | Maximum refinement steps per conversation branch |
| `-K`, `--local-sample-size` | `1` | Model responses sampled at each step |
| `--restart-top-k` | `1` | Number of top historical candidates injected into each new restart prompt |
| `--validation-fraction` | `0.2` | Fraction of samples reserved for validation |
| `--split-by` | `random` | Split strategy: `random` or `ood` (extrapolation split ordered by a variable) |
| `--split-ood-variable` | none | Variable used to sort samples when `--split-by ood` is selected |
| `--split-random-state` | `42` | Random seed for data splitting |
| `--force-initial-diagnostics` | on | Run statistical and relationship diagnostics before the first turn of each branch |
| `--auto-routing` | on | Automatically route between base and strong models based on search progress |

Boolean flags also accept `--no-...` (for example, `--no-auto-routing`).

## `sr-harness tool`

`sr-harness tool` lets you inspect registered tools, view their JSON schemas, or run a single tool directly from the command line without starting a full Agent loop—ideal for debugging custom tools or building scripted pipelines.

```bash
sr-harness tool list [--json]
sr-harness tool schema [TOOL]
sr-harness tool call TOOL \
  [--context context.npz] \
  [--target NAME] \
  [--params JSON] \
  [--params-file FILE]
```

- **`list`**: Prints all registered tools and their descriptions (`--json` outputs a plain JSON array of tool names).
- **`schema [TOOL]`**: Prints the parameter JSON schema for a specific tool (or all tools if omitted).
- **`call TOOL`**: Builds an `AgentContext` from the `.npz` file given by `--context` (defaults to `context.npz`, with `--target` optionally overriding the target variable) and executes the tool with JSON parameters.

You can pass parameters via `--params-file`, `--params`, or both (keys in `--params` override those in the file). Formatted tool output is printed to stdout, and failed tool runs exit with code `1`.

Example:

```bash
sr-harness tool schema evaluate_formula
sr-harness tool call evaluate_formula \
  --context context.npz \
  --params '{"f": "x1 ** 2", "y": "y"}'
```

## `sr-harness benchmark`

`sr-harness benchmark` runs systematic evaluations of SRHarness or other registered symbolic-regression baselines on the LLM-SRBench benchmark suite. It loads each problem, executes the chosen algorithm, computes numerical metrics ($R^2$, MSE, NMSE, MAPE, Kendall correlation) on in-domain and out-of-domain test splits, and checks symbolic equivalence against the ground-truth formula.

Use `--algorithm` to pick the method to evaluate. By default all supported datasets are run; pass `--datasets` and `--problem-names` to narrow the scope. Because each algorithm can register its own CLI flags, check `--help` for the full list of options available in your environment:

```bash
sr-harness benchmark --help
```

Example smoke test on a single problem:

```bash
sr-harness benchmark \
  --algorithm sr_harness \
  --datasets lsrtransform \
  --problem-names II.6.15b_1_0 \
  --save-path ./logs/benchmark-smoke
```

Per-problem logs are saved under `--save-path`, and dataset-level summaries are written to `--save-path/summary/`. Useful resume and ablation flags:

- `--skip-successful` (enabled by default): skips problems that already have a successful result so interrupted runs can resume cleanly;
- `--skip-existing`: skips any problem that already has an output record regardless of status;
- `--anonymize`: replaces variable names and scientific descriptions with generic placeholders while keeping the numerical arrays unchanged.
