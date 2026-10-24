# SRHarness 命令行参考

SRHarness 命令行工具的通用格式为 `sr-harness <command> [options]`，包含四个子命令：

| 子命令 | 用途 |
|---|---|
| `run` | 启动交互式网页工作台（WebUI） |
| `synthetic` | 根据给定公式合成数据，并运行非交互式符号回归搜索 |
| `benchmark` | 在 LLM-SRBench 基准数据集上评测 SRHarness 及其他算法 |
| `tool` | 查看已注册的工具列表、参数 Schema，或单独调用某个工具 |

## `sr-harness run`

启动交互式 WebUI 工作台，支持在浏览器中完成数据准备、任务配置和符号回归搜索。

```bash
sr-harness run [options]
```

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `--name` | `run` | 任务名称前缀，用于自动生成实验目录名 `{EXP_NAME}=YYYYMMDD_{NAME}_HHMMSS_{HOSTNAME}` |
| `--exp-name` | 自动生成 | 完整实验名称，用于拼接 `{SAVE_PATH}={SAVE_DIR}/{EXP_NAME}`；指定后无需再传 `--name` |
| `--save-dir` | 无 | 实验根目录，用于拼接 `{SAVE_PATH}={SAVE_DIR}/{EXP_NAME}` |
| `--save-path` | 自动推导 | 运行日志的持久化目录；直接指定后无需再传 `--name`、`--exp-name` 和 `--save-dir` |
| `--host` | `127.0.0.1` | Web 服务监听地址 |
| `--port` | `8000` | Web 服务监听端口 |
| `--workspace-dir` | `{SAVE_PATH}` | 对话列表与各对话工作区的根目录 |
| `--isolate-users` | 关闭 | 根据浏览器持久 Cookie 隔离不同访客的对话列表 |
| `--mount` | 空 | 以只读方式挂载到工作区的本地文件或目录，支持传入多个路径（如 `--mount a b c`） |
| `--read-only` | 关闭 | 只读回放模式：仅浏览已有对话与搜索记录，禁用一切修改接口与后台落盘 |

### 保存路径与工作区 { #save-paths-and-workspaces }

SRHarness 会在 `--workspace-dir` 目录下管理所有对话的工作区文件与会话状态（默认与 `--save-path` 相同；若两者都未指定，则使用系统临时目录，服务退出后不会保留历史记录）。目录结构如下：

```text
{WORKSPACE_DIR}/
├── conversations.json          # 已持久化的对话注册表（保存对话 ID 与显示名称）
├── conversation-visits.jsonl   # 访客与会话持久化事件日志
├── workspaces/
│   └── {CONVERSATION_ID}/      # 当前对话的工作区（Agent 工具可读写）
└── sessions/
    └── {CONVERSATION_ID}/      # 当前对话的私有配置（对 Agent 工具不可见）
        ├── .env                # 该对话独立配置的 API Key 与代理地址
        └── interactive-session.json
```

关于存储与会话生命周期，有以下几个实用细节：

- **工作区与隐私隔离**：`workspaces/` 下的文件可供 Agent 工具读写；而 `sessions/` 下保存的 `.env`（API Key、代理配置）和会话快照完全独立，不会暴露给 Agent，导出对话压缩包时也会自动剔除 `.env`。对话的显示名称只记录在 `conversations.json` 中，因此重命名对话不会改变底层目录路径。
- **按需持久化（防空目录垃圾）**：刚打开网页或点击“新建对话”时，系统只会创建一个内存中的临时会话，不会立即写入 `conversations.json` 或在磁盘上创建空文件夹。只有当你真正上传/修改了工作区文件、重命名了对话，或实际调用了 Agent 之后，该对话才会正式落盘。
- **访客统计与闲置恢复**：每次创建临时会话时，系统会在 `conversation-visits.jsonl` 中追加一条 `visit_started` 事件；当会话正式落盘时，再追加一条记录触发原因的 `conversation_persisted` 事件（方便按 `visitor_id` 统计只浏览未操作的访客）。临时会话连续闲置 1 小时后，服务端会释放其内存对象与系统临时目录；但只要用户未清理浏览器 Cookie，哪怕隔几天再回来继续操作，服务端也会用同一个会话 ID 自动重建环境，无需刷新页面。
- **断点恢复**：只要显式指定了 `--save-path`（或 `--save-dir`），SRHarness 就会将每次搜索的运行日志写入 `{SAVE_PATH}/runs/{CONVERSATION_ID}`，并定期在 `sessions/` 中保存会话快照。服务重启后，只要传入相同的 `workspace-dir` 和 `save-path`，之前的时间线、数据集、任务设置、自定义 Evaluator 和搜索进度都会自动恢复。
- **只读浏览模式**：如果只想查看或向他人展示已有的实验记录，可以同时传入 `--save-path`、`--workspace-dir` 和 `--read-only`（要求目录和 `conversations.json` 已存在，且不能与 `--mount` 混用）。`--read-only` 可以与 `--isolate-users` 自由组合。在容器环境中部署只读展示服务时，建议同时将宿主机目录以只读方式（`:ro`）挂载进容器，实现应用层与操作系统层的双重只读保护：

```bash
sr-harness run --save-path /data --workspace-dir /data --read-only --host 0.0.0.0 --port 8000
```

### 网络监听设置

仅在本机访问（默认，最安全）：

```bash
sr-harness run --host 127.0.0.1 --port 8000
```

允许局域网或外部机器访问（需同步开放防火墙端口）：

```bash
sr-harness run --host 0.0.0.0 --port 8000
```

!!! warning
    SRHarness 内置 Web 服务不包含用户登录鉴权或网络安全防护。将服务暴露到不可信网络前，请务必配置反向代理、TLS 加密与访问控制。

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
