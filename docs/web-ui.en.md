# SRHarness WebUI

The SRHarness WebUI guides a symbolic-regression study through three clear stages: **Data Preparation → Task Setup → Symbolic Regression**.

The interface uses a three-column layout: the left sidebar manages conversations and workspace files, the center panel hosts the active stage, and the right panel displays interactive data previews or the live search tree and candidate formulas.

## Launch the Workbench

```bash
sr-harness run \
  --host 127.0.0.1 \
  --port 8000 \
  --workspace-dir ./workspaces \
  --save-path ./logs/webui
```

Open `http://127.0.0.1:8000/` in your browser.

## Interface Overview

![SRHarness data preparation](https://yuzhthu.github.io/SRHarness/assets/webui-data-preparation.png)

| Area | Purpose |
|---|---|
| **Top header** | Rename the active chat, switch language (`EN` / `中`), toggle light/dark mode, open docs, and check connection/run status |
| **Left sidebar** | Switch between **Chats** and **Workspace**, create or export chats, and upload, download, or lock workspace files |
| **Center panel** | Navigate across **Data Preparation**, **Task Setup**, and **Symbolic Regression** (plus **Current Context** inspection) |
| **Right panel** | Inspect data tables, graph topology, scatter/distribution/heatmap plots during preparation, or explore the live search tree and candidate formulas during a run |

Every conversation has its own isolated workspace folder, private session settings (including conversation-scoped API keys), and `InteractiveSession`. Switching conversations switches the active dataset, timeline, settings, and search state automatically. See [Save paths and workspaces](sr-harness.md#save-paths-and-workspaces) for how files are organized on disk.

## Stage 1: Data Preparation

### 1. Upload Files or Load a Built-in Sample Dataset

Drag and drop CSV, Excel (`.xls`/`.xlsx`), PDF, or `.npy` files into the upload bar, or click the upload button.

Note that **raw CSV or Excel files are preparation inputs and cannot start a symbolic-regression run directly**. Before moving to Task Setup, a valid `context.data/manifest.json` and its `.npy` arrays must be created and loaded.

To explore the workflow right away without uploading files, click **sample dataset** to generate one of four built-in benchmarks:

1. **Polynomial Regression**: Two continuous inputs with a quadratic target;
2. **Grouped Parameters**: Exponential decay where a categorical label selects group-specific constants;
3. **Oscillatory ODE**: A nonlinear 1D oscillator trajectory under multi-frequency periodic forcing;
4. **Kuramoto Network**: Coupled oscillator dynamics on a 10-node Barabási–Albert directed network.

Once `context.data/` is loaded, the right panel previews variable shapes, tables, graph structures, and interactive scatter, distribution, and heatmap plots.

### 2. Use the Data Preparation Agent

Ask the Data Preparation Agent in plain language to inspect uploaded files, clean noisy columns, compute derivatives, and write standardized arrays to `context.data/`. For example:

> Read trajectory.csv, estimate dx_dt using central differences, keep t, x, and dx_dt, and document their physical meaning and units in the manifest.

After updating `context.data/`, the Agent runs `validate_context_data` so `InteractiveSession` can reload the verified dataset into the shared `AgentContext`. See [Structured Data and `context.data`](context-data.md) for the full format specification.

**Composer shortcuts and stop controls**:

- Press `Enter` to send, or `Shift + Enter` / `⌘ + Enter` to insert a newline.
- While an Agent is running, **clicking the stop button once** requests a clean pause after the current turn finishes; **clicking the red stop button a second time** immediately interrupts the active stream or tool call.

### 3. Output Token Limits and Continuation

Each Agent's **Output Token Limit** defaults to blank (`Auto`), which uses the model provider's default budget rather than a hard 4096-token cap (you can also enter a positive integer to cap single-turn output).

If a model reply hits its output token limit:

- Partial text is preserved with a clear truncation notice, and incomplete tool calls are never executed;
- For the Data Preparation Agent and Evaluator Construction Agent, sending `"Continue"` resumes from the partial answer;
- For the Symbolic Regression Agent, the run pauses at the end of the turn by default (configurable via **Pause after truncated output** under Search settings).

### 4. Agent Permissions and Data Safety { #agent-safety }

The Data Preparation Agent and Evaluator Construction Agent use tool calls to inspect files, run sandboxed Python scripts, and write outputs inside the current workspace. While they do not have an unrestricted system shell, they can modify or delete files inside the writable workspace.

!!! warning "Keep Backups of Irreplaceable Data"
    The **Lock** toggle in the workspace file menu helps prevent accidental overwrites, but it is not an OS security boundary against malicious code. Always keep independent backups of irreplaceable datasets and mount them read-only via `--mount`.

Default Agent tools and their boundaries:

| Tool | Capability and Boundary |
|---|---|
| `workspace_shell` | Runs a built-in command parser supporting `ls`, `cat`, `grep`, `cp`, `mv`, `rm`, `mkdir`, `gzip`, `unzip`, and `tar` inside the workspace. It **does not invoke a system shell** and blocks arbitrary binaries, command substitution, redirection, `..` traversal, and symlinks escaping the workspace. |
| `workspace_code_executor` | Executes Python (NumPy, SciPy, pandas, etc.) inside an ephemeral OS sandbox enforced by Linux Landlock and seccomp. It can read/write the active conversation workspace and read `--mount` inputs, but networking and child-process creation are blocked and CPU/memory/output are strictly bounded. |
| `web_search` / `web_fetch` | Queries public search engines or fetches public HTTP/HTTPS pages (`web_fetch` blocks private IP ranges, credentialed URLs, and unsafe redirects). |
| `read_pdf` | Extracts text from workspace PDFs or public URLs without modifying files. |
| `read_skill` | Reads instructions and reference files from enabled Skills. |
| `validate_context_data` | Validates [`context.data`](context-data.md) and reports actionable errors without mutating the live `AgentContext`. |

You can enable or disable individual tools and Skills under **Settings → Capabilities** for each Agent.

During symbolic regression, `code_executor`, `evaluate_code`, custom Tools, and custom Evaluators run under even tighter confinement: they receive only serialized data copies and temporary scratch space, with **no access to the conversation workspace**, API keys, or session internals.

**Two levels of read-only protection**:

1. **CLI mounts (`sr-harness run --mount PATH ...`)**: Application-enforced read-only inputs that cannot be unlocked from the WebUI;
2. **Workspace Lock (`Lock` in the file menu)**: Removes write permission bits to prevent accidental modification by workspace tools.

For kernel-enforced read-only protection on shared servers, have an administrator create a read-only bind mount first, then run SRHarness under a dedicated unprivileged account (without `sudo` or `CAP_SYS_ADMIN` privileges):

```bash
sudo mount --bind /data/original /mnt/srh-original
sudo mount -o remount,bind,ro /mnt/srh-original

sudo -u srharness sr-harness run \
  --workspace-dir /srv/srharness/workspaces \
  --mount /mnt/srh-original
```

## Stage 2: Task Setup

![SRHarness task setup](https://yuzhthu.github.io/SRHarness/assets/webui-task-setup.png)

### 1. Variable Roles and Descriptions

In the variable table:

- **Click the colored role bar** to switch a variable between **Target** (one per run), **Feature**, and **Excluded**;
- **Click any description cell** to edit its scientific meaning and units (changes sync automatically with `context.data/manifest.json`);
- **Drag the `⠿` handle** to reorder variables.

### 2. Problem Description

Describe the scientific goal for the symbolic-regression Agent (for example: *"Find a compact equation for dx_dt using x and t. Prefer a stable, interpretable model."*). There is no need to repeat variable descriptions already listed in the table above.

### 3. Configure Evaluation Protocol (Evaluator) { #evaluator-configuration }

Choose a built-in Evaluator (`DefaultEvaluator` or `GraphEvaluator`) or a custom script from `context.evaluator/` (invalid scripts remain listed with a `⚠` badge and error message so you can fix them):

- **Parameters (`context.args.*`)**: Configure validation split ratio, split strategy (`random` vs. `ood`), OOD ordering variable, and the candidate `ranking_metric`;
- **Test**: Run the selected Evaluator against the current best candidate (or a simple baseline formula if no candidates exist yet) to verify that splitting, fitting, and metric calculation succeed;
- **Save Protocol**: Save edits in the code editor as a custom Evaluator in `context.evaluator/`;
- **Evaluator Construction Agent**: Expand the assistant drawer below the editor and describe the evaluation metric you need in plain language—the Agent will inspect relevant source files, write a `DefaultEvaluator` subclass, and test it against your active dataset.

## Stage 3: Symbolic Regression

Before launching the search, review the variable summary, the generated **User Prompt**, the **System Prompt** (via the bottom toolbar), and the **Settings** panel (models, automatic routing, `R-C-L-K` budget, stop conditions, and enabled tools/Skills). Prompts are never overwritten automatically once edited unless you click **Regenerate**.

Click the send button to start exploring!

![SRHarness symbolic-regression timeline](https://yuzhthu.github.io/SRHarness/assets/webui-symbolic-regression.png)

### 1. Live Timeline Cards

Each interaction event appears as a card in the timeline:

- **System & User Prompts** added to the conversation buffer;
- **Sent Context summaries** showing message and character counts (click the `R · C · L` badge to inspect the exact message buffer sent to the model);
- **Agent replies** with collapsible reasoning traces and a toggle between rendered Markdown/MathML and plain text;
- **Tool calls & results** with execution time, parameters, formatted output, and expandable raw JSON (failed tool calls show a red error icon while still feeding the error message back to the Agent for self-correction).

### 2. Mid-Run Guidance and Pause Controls

The composer button adapts to the current run state:

- **Idle or paused with text**: Starts or resumes the run;
- **Running with text**: Queues your guidance message to be injected at the start of the next turn;
- **Running with empty input (square icon)**: Requests a clean pause after the current turn completes;
- **Pause already requested (red square icon)**: Force-interrupts the active stream or tool call immediately.

For details on how `finish_search`, tool-free stop review rounds, and **Stop Guard** conditions work together, see [SRHarness Agent Workflow: Stopping Controls](agent.md#stopping-controls-in-interactive-search).

### 3. Search Tree and Candidate Formulas

The right panel tracks global search progress:

- **Search Tree**: Visualizes explored `(R, C, L, K)` nodes colored by performance. Click any node to inspect its prompt context, or click **Full viewer ↗** to open the standalone search-tree analyzer.
- **Candidate Formulas**: Switch between **Top-k** (sorted by `ranking_metric`) and the **Pareto Front** (balancing accuracy against formula complexity), and toggle between **Raw**, **Formula**, and **LaTeX** display modes.

## End-to-End Walkthrough: Discovering an ODE from `(t, x)` Data

1. Upload a trajectory file containing `t` and `x` in **Data Preparation**.
2. Ask the Data Preparation Agent to estimate `dx_dt` and validate `context.data/`.
3. Inspect the time series and phase-space scatter plot in the right panel.
4. In **Task Setup**, set `dx_dt` as **Target** and `x`, `t` as **Features**.
5. Start an initial search in **Symbolic Regression** using `DefaultEvaluator`.
6. Pause the search and return to **Task Setup**.
7. Ask the **Evaluator Construction Agent** to add a trajectory rollout metric and test it:

   > Create a TrajectoryRolloutEvaluator subclassing DefaultEvaluator. Keep the default metrics and add rollout_rmse by integrating candidate ODEs in evaluate_candidate.

8. Open **Parameters** (`context.args.*`), set `ranking_metric` to `rollout_rmse`, and uncheck `larger_is_better`.
9. Return to **Symbolic Regression**, inform the Agent that candidates are now ranked by trajectory rollout error, and resume the search.

Both the Pareto Front and `evaluate_formula` outputs will now report `rollout_rmse`, guiding the Agent toward formulas that remain stable under full trajectory integration.

## Multi-User Isolation and Deployment Notes

- `--isolate-users` scopes conversation lists per browser via a persistent cookie;
- `--mount` paths are read-only across all Agents;
- Model credentials, proxies, tools, and Skills are configured independently per Agent;
- Always place public deployments behind external authentication and TLS termination. See [SRHarness CLI Reference](sr-harness.md) for full CLI details.
