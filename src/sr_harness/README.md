# SRHarness 框架开发说明

> 完整的使用文档与 API Reference 请参阅 [`docs/index.md`](../../docs/index.md)。

## 1. `SRAgent` 搜索循环与 `R-C-L-K` 架构

`SRAgent` 是基于大语言模型的符号回归核心智能体。它围绕 **“组装上下文 → 请求模型 → 解析工具调用 → 执行工具并更新候选池”** 的闭环运转，并通过四个维度组织搜索树：

```text
for R in 1..max_restart_loop:         # 外层重启轮数 (Restart)
  for C in 1..global_width:           # 并行对话分支数 (Conversation)
    for L in 1..max_refinement_depth: # 单分支迭代步数 (Refinement Depth)
      for K in 1..local_sample_size:  # 单步局部采样数 (Local Sample)
        ...                           # 单次模型请求与工具调用
```

- **R（Restart，重启）**：外层重启循环。每开启新一轮重启时，系统会从全局候选池中提取前序轮次发现的 Top-k 最优公式写入新的初始提示词，让模型在已有成果的基础上继续探索。
- **C（Conversation，并行分支）**：同一轮重启下的多条独立对话分支。每条分支从相同的初始提示词出发，各自维护独立的对话历史，探索不同的建模思路。
- **L（Refinement Depth，迭代深度）**：单条分支内的多轮迭代。每一轮包含完整的提示词组装、模型采样、工具执行与候选公式收集。
- **K（Local Sample，局部采样）**：在同一个迭代步 `L` 中，同时向模型采样 `K` 个候选回复并执行其中的工具调用。系统会择优挑选候选公式得分最高的一个回复作为主线延续到 `L+1`，同时将其余采样分支中通过数据分析或辅助工具获得的有效信息一并并入对话上下文。

## 2. 核心组件与职责边界

### Agent 继承体系

- **`Agent`（抽象基类）**：封装大模型 API 调用、工具解析器（`BaseParser`）、上下文绑定与工具调度等公共机制。
- **`DataPreparationAgent`**：负责数据准备阶段的持续多轮对话，支持在受限工作区中检查原始文件、运行清洗脚本并生成标准化的 `context.data/`。
- **`EvaluatorConstructionAgent`**：负责根据用户的自然语言需求阅读内置评估器源码、在 `context.evaluator/` 下编写自定义 `DefaultEvaluator` 子类，并在沙箱中完成测试验证。
- **`SRAgent` / `SRAgentInteractive`**：负责执行 `R-C-L-K` 符号回归搜索；`SRAgentInteractive` 在此基础上增加了实时事件推送、安全边界暂停/强制中断、运行期配置热更新以及提前停止守卫（Stop Guard）。

上述 Agent 可共享同一个 `AgentContext` 实例，但各自维护独立的对话缓冲区（Buffer），互不串扰。

### `AgentContext`（共享运行时上下文）

`AgentContext` 保存当前会话在内存中的权威数据集与环境状态，包括：

- 结构化数据字典 `data`（变量与坐标轴数组）、因变量名称 `target` 与自变量列表；
- 变量的物理描述、坐标轴映射、图/超图关系表与节点总数 `num_nodes`；
- 当前生效的公式评估器 `evaluator`、延迟切分并自动缓存的 `train_split` / `validation_split` 视图；
- 当前工作区路径 `workspace` 以及单调递增的数据修订号 `data_revision`。

在交互式工作台中，各工具仅在工作区磁盘上生成或校验 `context.data/`，不会在工具执行中途直接篡改内存中的 `AgentContext`；待当前轮次结束后，由 `InteractiveSession` 统一加载通过校验的新数据集并递增版本号。正在运行的 `SRAgentInteractive` 则会在下一个安全迭代边界处自动刷新训练/验证切分，并将变量变更写入对话上下文。

### `tool_box: BaseParser`（工具箱与解析器）

`tool_box` 持有当前启用的工具实例列表（`tool_box.tools: list[BaseTool]`），同时负责将工具声明格式化给大模型，以及从模型回复中解析出标准 `ToolCall`。工具开发细节请参阅 [`tools/README.md`](tools/README.md)。一次工具调用的标准流程为：

1. 初始化 Agent 时，根据当前上下文 `context` 实例化启用的 `BaseTool` 子类；
2. 模型输出工具调用请求（工具名称 + 参数字典）；
3. Agent 通过 `tool_box[name]` 查找对应工具实例并调用 `tool(**params)`；
4. 工具返回标准的 `ToolCallResult`（包含执行状态 `ok`、结构化字典 `result`、供模型阅读的格式化文本 `result_str` 以及耗时元数据 `meta_data`）。

### `api: BaseAPI`（模型通信接口）

`BaseAPI` 屏蔽不同模型服务商（OpenRouter、DeepSeek、OpenAI、Gemini、SiliconFlow 等）的协议差异：

```python
llm_result = self.api(messages, n=local_sample_size)
for sample in llm_result:
    content = sample.content        # 模型回复的正文内容
    tool_calls = sample.tool_calls  # 解析出的工具调用列表 (list[ToolCall])
    message = sample.message        # 可直接追加到对话历史中的消息字典
```

迭代结束后，`llm_result`（类型为 `APICallSummary`）中保留本次请求的完整统计信息：`llm_result.token_usage`、`llm_result.money_usage`、`llm_result.ok` 与 `llm_result.error`。

## 3. `SRAgent` 单步迭代流程

在单条分支的每一步 `L` 中，主循环依次执行以下方法：

1. **`prepare_iteration()`**：在安全边界处响应暂停请求、应用待生效的模型/工具配置更新、刷新数据集版本，并注入用户中途发送的指导消息。
2. **`prepare_model_messages()`**：根据当前分支的对话缓冲区构建发给模型的消息列表（若开启 `force_initial_diagnostics`，会在 `L=1` 时自动注入初始统计与相关性分析结果）。
3. **`request_llm()`**：调用 `api` 获取 `K` 个候选采样回复。
4. **`execute_tool_calls()`**：并行或串行执行每个采样回复中的工具调用，收集 `ToolCallResult`。
5. **`record_search_iteration()`**：将本轮提示词、采样回复、工具调用结果、父节点链接及资源消耗写入 `SearchRunState`。
6. **`collect_candidates()`**：提取所有 `is_candidate=True` 的有效公式，按所选 `ranking_metric` 更新全局排行榜与帕累托前沿。
7. **`update_conversation()`**：选出本轮表现最佳的采样分支并入主对话缓冲区，同时汇总其余采样分支中非公式评估类工具的有效输出，最后附上当前搜索进度摘要。
8. **`finish_iteration()`**：打印进度日志，检查是否满足提前停止条件或触发交互式暂停。

## 4. 目录结构

```text
src/sr_harness/
├── agents/                          # 智能体实现
│   ├── agent.py                     # Agent 抽象基类与工具调度公共逻辑
│   ├── data_preparation_agent.py    # 数据准备 Agent
│   ├── evaluator_construction_agent.py # 自定义 Evaluator 构建 Agent
│   ├── sr_agent.py                  # SRAgent 主搜索循环 (R-C-L-K)
│   └── sr_agent_interactive.py      # 支持实时事件与人机协同的交互式 SRAgent
├── api/                             # 大模型服务商接口适配
│   ├── base_api.py                  # BaseAPI 抽象基类、重试与流式处理
│   └── *_api.py                     # OpenAI、OpenRouter、DeepSeek、Gemini 等实现
├── cli/                             # sr-harness 命令行子命令入口 (run/synthetic/benchmark/tool)
├── core/                            # 核心数据结构
│   ├── api.py                       # APICallSample 与 APICallSummary
│   ├── context.py                   # AgentContext 与 context.data 校验/加载器
│   ├── search.py                    # SearchRunState、CandidateRecord 与搜索树状态
│   └── tool.py                      # ToolMetadata、ToolCall 与 ToolCallResult
├── evaluator/                       # 公式评估协议与辅助工具库
│   ├── default_evaluator.py         # DefaultEvaluator 与沙箱化自定义 Evaluator 加载
│   ├── graph_evaluator.py           # GraphEvaluator (图与超图数据切分与求值)
│   └── utils/                       # 误差指标、数据切分与 ODE 积分工具函数
├── parser/                          # 工具调用解析器 (OpenAI Function Calling / JSON / XML / Text)
├── runtime/                         # 交互控制、模型自动路由、工作区隔离与 Landlock 沙箱
├── skills/                          # 内置领域技能 (SKILL.md) 与 SkillManager
├── tools/                           # BaseTool 基类与全部内置科学分析/拟合/搜索工具
├── web/                             # FastAPI 网页工作台后端与静态前端资源
└── utils/                           # 日志、计时器、公式等价判定等通用辅助函数
```
