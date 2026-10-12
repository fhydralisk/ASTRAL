# SRHarness

SRHarness 命令采用 `sr-harness <command> [options]` 的形式：

| 命令 | 用途 |
|---|---|
| `run` | 启动交互式 Web 工作台 |
| `synthetic` | 使用合成数据运行 SRHarness |
| `benchmark` | 在 LLM-SRBench 上评测 SRHarness 和其他已注册算法 |
| `tool` | 查看可用工具，或者单独调用某个工具 |

## `sr-harness run`

`sr-harness run` 启动交互式 WebUI 工作台，允许用户在浏览器中完成数据准备、任务配置和符号回归搜索。

```bash
sr-harness run [options]
```

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--name` | `run` | 任务名，用于生成 `{EXP_NAME}=YYYYMMDD_{NAME}_HHMMSS_{HOSTNAME}` |
| `--exp-name` | 自动生成 | 完整任务名，用于生成 `{SAVE_PATH}={SAVE_DIR}/{EXP_NAME}`；显式指定时可不提供 `--name` |
| `--save-dir` | 无 | 实验目录，用于生成 `{SAVE_PATH}={SAVE_DIR}/{EXP_NAME}` |
| `--save-path` | 自动推导 | 运行日志的持久化保存目录；显式指定时可不提供 `--name`、`--exp-name` 和 `--save-dir` |
| `--host` | `127.0.0.1` | 服务监听地址 |
| `--port` | `8000` | 服务监听端口 |
| `--workspace-dir` | `{SAVE_PATH}` | 对话注册表和各对话工作区的存储目录 |
| `--isolate-users` | 关闭 | 按浏览器持久 Cookie 隔离不同用户的对话 |
| `--mount` | 空 | 需要挂载到工作区的文件或目录，可通过 `--mount a b c ...` 提供多个文件和/或目录 |
| `--read-only` | 关闭 | 只读浏览已有对话；禁用所有变更状态的 API 和后台持久化 |

### 保存路径与工作区

SRHarness 会在 `--workspace-dir` 中保存对话注册表、每个对话的 Agent 工作区和私有会话状态。默认使用 `--save-path` 作为 `workspace-dir`，但也可以显式地指定不同目录。当两者均未指定时，将使用临时目录，此时对话记录无法持久保存。

```text
{WORKSPACE_DIR}/
├── conversations.json
├── conversation-visits.jsonl
├── workspaces/
│   └── {CONVERSATION_ID}/
└── sessions/
    └── {CONVERSATION_ID}/
        ├── .env
        └── interactive-session.json
```

`workspaces/` 中的内容可由 Agent 工具访问；`sessions/` 保存每个对话独立的 API Key、代理配置和会话快照，不向工作区工具暴露。对话显示名称只存储在 `conversations.json` 中，因此重命名不会改变目录路径。导出对话时不会包含 `.env`。

首次访问和点击“新建对话”只创建临时会话，不会写入 `conversations.json`，也不会在 `workspaces/`、`sessions/` 或 `runs/` 中留下空目录。只有成功修改工作区、调整对话名称或实际调用 Agent 后，对话才会持久化。每个临时会话会在 `conversation-visits.jsonl` 中写入 `visit_started` 事件；升级后再写入带有原因的 `conversation_persisted` 事件。因此可按 `visitor_id` 去重，并把没有对应持久化事件的访问统计为“只看看”的用户。临时会话的逻辑 ID 不会过期。打开的页面会通过正常状态轮询保持其内存状态；连续空闲一小时后，服务端只释放对应的内存对象和系统临时目录。用户即使隔几天再操作，服务端也会使用浏览器 Cookie 中相同的临时会话 ID 透明重建，不需要刷新页面。只读模式不会写入该日志。

当显式指定了 `--save-path`（或 `--save-dir`）时，SRHarness 会将各对话的运行日志写入 `{SAVE_PATH}/runs/{CONVERSATION_ID}`，并定期更新 `sessions/` 中的会话快照。即使服务中断，也可以使用相同的 `workspace-dir` 和 `save-path` 重启，以恢复时间线、数据、设置、评估器和搜索状态。

只读查看已有存储时，同时指定 `--save-path`、`--workspace-dir` 和 `--read-only`。该模式要求目录以及 `conversations.json` 已存在，并且不能与 `--mount` 同时使用。`--read-only` 与 `--isolate-users` 相互独立：可以只读查看全部对话，也可以根据浏览器持久 Cookie 只读查看当前用户的对话。为提供纵深防护，容器部署还应把该目录以只读 bind mount 挂载；应用层只读开关不能替代操作系统级只读权限。

```bash
sr-harness run --save-path /data --workspace-dir /data --read-only --host 0.0.0.0 --port 8000
```

### 网络暴露

本机使用：

```bash
sr-harness run --host 127.0.0.1 --port 8000
```

允许外部主机连接（需打开防火墙）：

```bash
sr-harness run --host 0.0.0.0 --port 8000
```

!!! warning
    SRHarness 未提供完整的认证、授权或网络安全边界。把服务暴露到不可信网络前，应配置反向代理、TLS 和访问控制。

## `sr-harness synthetic`

`sr-harness synthetic` 根据用户指定方程生成随机样本，并基于此运行非交互式的符号回归 Agent。

### 数据生成参数

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `-f`, `--equation` | `y = sin(x1 - x2)` | 生成目标数据的方程 |
| `--features` | 自动解析 | 空格分隔的可观测自变量名。默认使用方程等号右侧的所有变量，也可显式指定以引入干扰变量或遗漏部分变量 |
| `--n-samples` | `100` | 样本数 |
| `--seed` | `-1` | 随机种子。默认使用系统时间 |
| `--x-low` / `--x-high` | `0.0` / `1.0` | 自变量采样范围 |
| `--noise-std-ratio` | `0.0` | 添加到目标变量的高斯噪声比例，`噪声强度 = {NOISE_STD_RATIO} * std(目标变量)` |
| `--problem-description` | 从方程生成 | 传给 Agent 的任务描述 |

### 模型与工具参数

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--llm-provider` | `openrouter` | 基础模型 provider |
| `--llm-model` | `deepseek/deepseek-v4-flash-0731` | 基础模型名 |
| `--strong-llm-provider` | 基础 provider | 自动路由的强模型 provider |
| `--strong-llm-model` | 无 | 自动路由的强模型 |
| `--llm-max-tokens` | `4096` | 单次模型回复最大 token |
| `--tool-parser` | `openai` | `openai`、`text`、`json` 或 `xml` |
| `--tools` | 符号回归默认工具集 | 可用工具列表；显式指定时也可禁用部分工具或启用非默认工具 |
| `--ban-tools` | 空 | 从 `--tools` 中移除（消融）部分工具 |
| `--max-workers` | `0` | 并行工具 worker 数；`0` 表示串行 |
| `--verbose` | 关闭 | 输出详细运行日志 |
| `--debug` | 关闭 | 启用详细日志，并在所有非预期的异常处中断而非继续运行 |

### 搜索与评测参数

R-C-L-K 四个搜索维度及其相互关系见 [SRHarness 智能体工作流](agent.md#r-c-l-k)。

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `-R`, `--max-restart-loop` | `1` | Restart 数 |
| `-C`, `--global-width` | `1` | 每个 Restart 的 Conversation 数 |
| `-L`, `--max-refinement-depth` | `30` | 每条分支最大迭代深度 |
| `-K`, `--local-sample-size` | `1` | 每一步模型采样数 |
| `--restart-top-k` | `1` | 注入下一 Restart 的历史候选数 |
| `--validation-fraction` | `0.2` | 验证集比例 |
| `--split-by` | `random` | `random` 或 `ood` |
| `--split-ood-variable` | 无 | OOD 排序变量；`split-by=ood` 时必填 |
| `--split-random-state` | `42` | 随机切分种子 |
| `--force-initial-diagnostics` | 开启 | 每个分支首次请求前执行初始诊断 |
| `--auto-routing` | 开启 | 根据任务和搜索进度选择基础/强模型 |

布尔选项同时支持 `--no-...` 形式，例如：

```bash
sr-harness synthetic --no-auto-routing --no-force-initial-diagnostics
```

## `sr-harness tool`

`sr-harness tool` 提供工具注册表的命令行入口，可用于查看当前安装中有哪些工具、检查工具接受的参数，以及在不启动完整 Agent 搜索的情况下单独执行某个工具。这适合调试工具、验证输入数据，或将单个工具接入脚本化工作流。

```bash
sr-harness tool list [--json]
sr-harness tool schema [TOOL]
sr-harness tool call TOOL \
  [--context context.npz] \
  [--target NAME] \
  [--params JSON] \
  [--params-file FILE]
```

- `list` 列出所有已注册工具及其说明；添加 `--json` 可只输出便于程序读取的工具名称数组。
- `schema [TOOL]` 输出指定工具的 JSON schema；省略工具名时输出全部工具的 schema，可据此确认参数名称、类型和必填项。
- `call TOOL` 从 `--context` 指定的 NPZ 文件构造 `AgentContext`，再使用 JSON 参数调用工具。`--context` 默认为当前目录下的 `context.npz`，`--target` 可覆盖文件中记录的目标变量名。

工具参数可以通过 `--params-file` 从 JSON 文件读取，也可以通过 `--params` 直接传入 JSON 对象。两者同时使用时，参数文件先加载，`--params` 中的同名字段随后覆盖。调用成功后会将工具的格式化结果写到标准输出；工具返回失败结果时，命令退出码为 `1`。

例如，查看 `evaluate_formula` 的参数并单独调用它：

```bash
sr-harness tool schema evaluate_formula
sr-harness tool call evaluate_formula \
  --context context.npz \
  --params '{"f": "x1 ** 2", "y": "y"}'
```

## `sr-harness benchmark`

`sr-harness benchmark` 在 LLM-SRBench 数据集上评测 SRHarness 或其他已注册的符号回归算法。它会依次加载问题、运行所选算法，并在域内测试集以及可用的域外测试集上计算 R²、MSE、NMSE、MAPE、Kendall 相关系数等指标；同时检查发现的表达式是否与参考表达式符号等价。

必须使用 `--algorithm` 选择算法。默认评测全部受支持的数据集，也可以用 `--datasets` 选择一个或多个数据集，并用 `--problem-names` 进一步限制到指定问题。算法还可以注册自己的专属命令行参数，因此完整算法列表、数据集选项和算法参数应以当前安装版本的帮助信息为准：

```bash
sr-harness benchmark --help
```

示例：

```bash
sr-harness benchmark \
  --algorithm sr_harness \
  --datasets lsrtransform \
  --problem-names II.6.15b_1_0 \
  --save-path ./logs/benchmark-smoke
```

每个问题的评测结果会被写入 `--save-path`，数据集级别的汇总结果则保存在其 `summary/` 目录中。默认开启的 `--skip-successful` 会跳过已有成功结果的问题，便于中断后继续评测；`--skip-existing` 可进一步跳过任何已有记录的问题。`--anonymize` 只将 Agent 可见的变量名和描述替换为通用名称，不改变数值数据。

