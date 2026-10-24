# SRHarness CLI Reference

All SRHarness CLI commands follow the pattern `sr-harness <command> [options]`:

| Command | Purpose |
|---|---|
| `run` | Launch the interactive WebUI workbench |
| `synthetic` | Generate synthetic data from a formula and run a non-interactive search |
| `benchmark` | Evaluate SRHarness and other registered baselines on LLM-SRBench |
| `tool` | List available tools, inspect parameter schemas, or invoke a single tool |

## `sr-harness run`

Launches the interactive WebUI workbench in your browser for data preparation, task setup, and symbolic regression.

| Option | Default | Description |
|---|---:|---|
| `--name` | `run` | Task name prefix used to build `{EXP_NAME}=YYYYMMDD_{NAME}_HHMMSS_{HOSTNAME}` |
| `--exp-name` | generated | Full experiment name used to build `{SAVE_PATH}={SAVE_DIR}/{EXP_NAME}` (makes `--name` optional) |
| `--save-dir` | none | Base directory used to build `{SAVE_PATH}={SAVE_DIR}/{EXP_NAME}` |
| `--save-path` | derived | Directory for persistent run logs (makes `--name`, `--exp-name`, and `--save-dir` optional) |
| `--host` | `127.0.0.1` | Host address to bind the web server |
| `--port` | `8000` | Port number to bind the web server |
| `--workspace-dir` | `{SAVE_PATH}` | Root directory for the conversation registry and per-conversation workspaces |
| `--isolate-users` | off | Filter conversation lists per user via a persistent browser cookie |
| `--mount` | empty | Files or directories to mount read-only into every workspace (`--mount a b c ...`) |
| `--read-only` | off | Browse existing conversations in read-only mode (disables all state-changing APIs and background writes) |

### Save paths and workspaces

SRHarness stores the conversation registry, per-conversation Agent workspaces, and private session state under `--workspace-dir` (which defaults to `--save-path`; if neither is provided, a temporary directory is used and conversations are not persisted after exit):

```text
{WORKSPACE_DIR}/
├── conversations.json          # Registry of persisted conversations and display names
├── conversation-visits.jsonl   # Visitor and persistence event log
├── workspaces/
│   └── {CONVERSATION_ID}/      # Conversation workspace (accessible to Agent tools)
└── sessions/
    └── {CONVERSATION_ID}/      # Private session state (hidden from Agent tools)
        ├── .env                # Conversation-scoped API keys and proxy settings
        └── interactive-session.json
```

Key details on how storage and session lifecycle work:

- **Workspace vs. private session state**: Agent tools can read and write files inside `workspaces/`. By contrast, `sessions/` stores each conversation's API keys, proxy settings, and session snapshot out of reach of workspace tools. Conversation exports automatically exclude `.env` files, and renaming a conversation only updates `conversations.json` without moving directories on disk.
- **Lazy persistence (no empty folders)**: Opening the WebUI or clicking **New chat** starts a lightweight in-memory session without touching `conversations.json` or creating empty folders under `workspaces/`, `sessions/`, or `runs/`. A conversation is written to disk only after you upload or modify workspace files, rename the chat, or run an Agent.
- **Visitor tracking and idle recovery**: Each new temporary session logs a `visit_started` event in `conversation-visits.jsonl`, followed by a `conversation_persisted` event once promoted to disk (making it easy to count unique visitors by `visitor_id` and see how many browsed without running tasks). After one hour of inactivity, the server frees the in-memory session and OS temp folder—but if the user returns days later with the same browser cookie, the server transparently rebuilds the session under the same ID without requiring a page refresh.
- **Crash recovery**: When `--save-path` (or `--save-dir`) is specified, run logs are written to `{SAVE_PATH}/runs/{CONVERSATION_ID}` and session snapshots under `sessions/` are updated periodically. Restarting the server with the same `workspace-dir` and `save-path` restores your timelines, datasets, settings, custom Evaluators, and search progress.
- **Read-only mode**: To serve an existing store for inspection or sharing, pass `--save-path`, `--workspace-dir`, and `--read-only` (requires `conversations.json` to exist and cannot be combined with `--mount`). `--read-only` works either globally or alongside `--isolate-users`. For container deployments, also bind-mount the data volume read-only (`:ro`) for OS-level enforcement:

```bash
sr-harness run --save-path /data --workspace-dir /data --read-only --host 0.0.0.0 --port 8000
```

Local-only server:

```bash
sr-harness run --host 127.0.0.1 --port 8000
```

Network-accessible server (ensure your firewall allows the port):

```bash
sr-harness run --host 0.0.0.0 --port 8000
```

!!! warning
    SRHarness does not include built-in user authentication or network security boundaries. Always place it behind a reverse proxy with TLS and access control before exposing it to an untrusted network.

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
