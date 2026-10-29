# SRHarness 命令行参考

SRHarness 命令行工具的通用格式为 `sr-harness <command> [options]`，包含四个子命令：

| 子命令 | 用途 |
|---|---|
| `serve` | 启动交互式网页工作台（WebUI） |
| `synthetic` | 根据给定公式合成数据，并运行非交互式符号回归搜索 |
| `benchmark` | 在 LLM-SRBench 基准数据集上评测 SRHarness 及其他算法 |
| `tool` | 查看已注册的工具列表、参数 Schema，或单独调用某个工具 |

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

`sr-harness synthetic` 会根据你给定的数学公式自动生成合成样本，并在命令行下直接运行非交互式的符号回归搜索，适合快速测试模型能力或调试工具链。

### 数据生成参数

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `-f`, `--equation` | `y = sin(x1 - x2)` | 用于生成合成数据的真实方程 |
| `--features` | 自动解析 | 空格分隔的输入自变量名。默认提取方程等号右侧出现的所有变量；也可手动指定，用于测试掺入无关干扰变量或遗漏关键变量的场景 |
| `--n-samples` | `100` | 采样点数量 |
| `--seed` | `-1` | 随机数种子（`-1` 表示使用当前系统时间） |
| `--x-low` / `--x-high` | `0.0` / `1.0` | 自变量的均匀采样区间上下界 |
| `--noise-std-ratio` | `0.0` | 叠加到因变量上的高斯噪声比例，实际噪声标准差为 `NOISE_STD_RATIO * std(y)` |
| `--problem-description` | 自动生成 | 传给 Agent 的背景描述文字 |

### 模型与工具参数

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--llm-provider` | `openrouter` | 基础模型服务商 |
| `--llm-model` | `deepseek/deepseek-v4-flash-0731` | 基础模型名称 |
| `--strong-llm-provider` | 同基础模型 | 启用自动路由时使用的强模型服务商 |
| `--strong-llm-model` | 无 | 启用自动路由时调用的强模型名称 |
| `--llm-max-tokens` | 自动 | 单次模型回复的最大 Token 数上限；留空则使用服务商默认值 |
| `--tool-parser` | `openai` | 工具调用解析方式：`openai`（原生 Function Calling）、`text`、`json` 或 `xml` |
| `--tools` | 默认工具集 | 允许 Agent 调用的工具列表 |
| `--ban-tools` | 空 | 从 `--tools` 中剔除指定工具（常用于消融实验） |
| `--max-workers` | `0` | 单轮工具调用的最大并行线程/进程数（`0` 表示串行执行） |
| `--verbose` | 关闭 | 打印详细的运行期日志 |
| `--debug` | 关闭 | 开启详细日志，并在遇到未捕获异常时立即中断抛出而非继续运行 |

### 搜索预算与评估参数

关于 `R-C-L-K` 四个搜索维度的详细配合机制，请参阅 [SRHarness 智能体工作流](agent.md#r-c-l-k)。

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `-R`, `--max-restart-loop` | `1` | 最大重启轮数（Restart） |
| `-C`, `--global-width` | `1` | 每次重启并行的独立对话分支数（Conversation） |
| `-L`, `--max-refinement-depth` | `30` | 每条分支的最大迭代轮数（Refinement Depth） |
| `-K`, `--local-sample-size` | `1` | 每轮迭代向模型采样的候选回复数（Local Sample） |
| `--restart-top-k` | `1` | 每次重启时带入新初始提示词的历史最优候选公式数量 |
| `--validation-fraction` | `0.2` | 验证集占总样本的比例 |
| `--split-by` | `random` | 数据切分方式：`random`（随机切分）或 `ood`（按指定变量排序后切分外推验证集） |
| `--split-ood-variable` | 无 | 当 `--split-by ood` 时，用于排序切分的变量名 |
| `--split-random-state` | `42` | 随机切分使用的随机种子 |
| `--force-initial-diagnostics` | 开启 | 是否在每条分支第 1 轮强制先运行统计与相关性诊断工具 |
| `--auto-routing` | 开启 | 是否根据当前搜索进展在基础模型与强模型之间自动切换 |

所有布尔开关均支持 `--no-...` 形式反向关闭，例如：

```bash
sr-harness synthetic --no-auto-routing --no-force-initial-diagnostics
```

## `sr-harness tool`

`sr-harness tool` 允许你在不启动完整 Agent 的情况下，直接查看已注册的工具列表、检查参数 JSON Schema，或者针对某份数据单独执行一次工具调用。这在开发调试自定义工具或编写自动化脚本时非常实用。

```bash
sr-harness tool list [--json]
sr-harness tool schema [TOOL]
sr-harness tool call TOOL \
  [--context context.npz] \
  [--target NAME] \
  [--params JSON] \
  [--params-file FILE]
```

- **`list`**：列出当前环境中所有已注册的工具及其功能简介；加上 `--json` 则只输出工具名称的 JSON 数组。
- **`schema [TOOL]`**：查看指定工具的参数 JSON Schema（省略工具名则输出所有工具的 Schema），方便核对参数名、类型与必填项。
- **`call TOOL`**：从 `--context` 指定的 `.npz` 文件（默认为当前目录下的 `context.npz`）加载数据并构造 `AgentContext`，然后传入 JSON 参数执行该工具。可通过 `--target` 临时覆盖目标因变量名。

调用参数既可以通过 `--params-file` 从 JSON 文件读取，也可以通过 `--params` 直接传入 JSON 字符串（若两者同时提供，`--params` 中的同名字段会覆盖文件中的值）。工具执行成功时会将格式化结果打印到标准输出；若工具返回失败（`ok=False`），命令退出码为 `1`。

例如，查看 `evaluate_formula` 的参数定义并手动评估一个公式：

```bash
sr-harness tool schema evaluate_formula
sr-harness tool call evaluate_formula \
  --context context.npz \
  --params '{"f": "x1 ** 2", "y": "y"}'
```

## `sr-harness benchmark`

`sr-harness benchmark` 用于在 LLM-SRBench 标准基准集上批量评测 SRHarness 或其他已注册的符号回归基线算法。它会自动加载题目、运行指定算法，并在域内（ID）与域外（OOD）测试集上计算 $R^2$、MSE、NMSE、MAPE、Kendall 相关系数等数值指标，同时检验找到的公式与标准答案是否符号等价。

运行时必须通过 `--algorithm` 指定要评测的算法。默认会跑完全部受支持的数据集，你也可以用 `--datasets` 限定数据集，或用 `--problem-names` 只跑特定题目。由于不同基线算法各自注册了专属参数，建议先通过 `--help` 查看当前环境支持的完整选项：

```bash
sr-harness benchmark --help
```

运行单道题目的冒烟测试示例：

```bash
sr-harness benchmark \
  --algorithm sr_harness \
  --datasets lsrtransform \
  --problem-names II.6.15b_1_0 \
  --save-path ./logs/benchmark-smoke
```

每道题目的详细结果会写入 `--save-path`，整个数据集的汇总统计则保存在 `--save-path/summary/` 目录下。常用辅助参数：

- `--skip-successful`（默认开启）：自动跳过已有成功记录的题目，方便任务中断后断点续跑；
- `--skip-existing`：跳过所有已有运行记录的题目（无论上次是否成功）；
- `--anonymize`：隐去变量名与科学背景描述（替换为通用符号），用于测试算法在缺乏领域文本线索时的纯数据发现能力。
