# SRHarness 核心抽象

如果你想为 SRHarness 编写自定义工具，或接入不同格式的大模型接口，只需要了解两个核心基类：

- **`BaseTool`**：定义工具如何声明参数、读取运行环境并返回结构化结果；
- **`BaseParser`**：负责把不同大模型的输出（原生 Function Calling、JSON 或纯文本）统一转换为标准工具调用。

关于公式评估协议与数据结构规范，请分别参阅 [公式评估与自定义 Evaluator](evaluator.md) 和 [结构化数据与 `context.data`](context-data.md)；关于 Agent 如何在搜索循环中调度这些组件，请参阅 [SRHarness 智能体工作流](agent.md)；完整的类与方法签名可查询 [API Reference](reference/index.md)。

## 工具基类：`BaseTool` { #base-tool }

在 SRHarness 中，所有可供 Agent 调用的工具都继承自 `BaseTool`。编写一个新工具通常只需要声明 `metadata` 并实现 `execute()` 方法，参数校验、计时、异常捕获和结果格式化等公共逻辑均由基类自动处理。

```python
from typing import Any

from sr_harness.tools import BaseTool, ToolMetadata


@BaseTool.register("example_tool")
class ExampleTool(BaseTool):
    metadata = ToolMetadata(name="example_tool")

    def execute(self, expression: str, limit: int = 10) -> dict[str, Any]:
        """Inspect an expression.

        Args:
            expression: Expression supplied by the model.
            limit: Maximum number of returned items.

        Returns:
            Structured inspection results.
        """
        parsed = self.parse_formula(expression)
        return {"expression": parsed.to_str(), "limit": limit}
```

### 输入规范

- **参数尽量简洁明确**：`execute()` 的参数由大模型直接生成，因此应使用简单、可 JSON 序列化的基础类型，并加上完整的 Python 类型标注。
- **通过 `self.context` 获取环境数据**：数据集、当前 Evaluator、工作区路径及运行配置都挂载在 `self.context`（即 `AgentContext`）上，不要让模型在每次调用工具时手动传这些环境信息。
- **自动生成工具说明与 Schema**：你可以显式指定 `metadata.description` 和参数的 JSON Schema；如果省略，`BaseTool` 会自动根据 `execute()` 的函数签名、类型标注以及 Google 风格的 docstring 推断生成。
- **按需暴露**：所有通过 `@BaseTool.register` 注册的工具都可以被系统发现，但 Agent 在实际运行时只会向模型暴露当前任务勾选启用的工具。

### 返回值与错误处理规范

- **结构化返回与文本展示分离**：
  - `execute()` 应返回一个结构化的 Python `dict`，供程序记录日志和提取候选公式；
  - `format_result_dict()` 负责把这个 `dict` 转换成简洁易读的文本（`result_str`）反馈给大模型。你可以按需重写 `format_result_dict()` 来优化模型看到的提示文本，而不会影响底层保存的机器可读数据。
- **统一的调用封装**：外部调用工具时统一走 `BaseTool.__call__()`，它会自动统计耗时并返回 `ToolCallResult(ok, result, result_str, meta_data)`。其中 `result` 保留完整结构化数据，而 `result_str` 会做长度截断保护，避免超长输出占用过多模型上下文。
- **异常自愈与中断传播**：工具内部抛出的常规异常（包括执行超时）会被自动捕获并包装为 `ok=False` 的 `ToolCallResult` 返回给模型，让模型能够看到报错原因并自行修正参数重试；而用于终止整轮运行的控制流异常 `ToolRunAbort` 则会正常向上抛出，不会被当作普通工具报错吞掉。
- **支持中途取消**：耗时较长的工具可以实现可选的 `cancel()` 方法，并在循环或阻塞操作中检查运行时的取消信号，以便用户在网页端点击“强制停止”时能及时退出。

此外，涉及数学公式的工具可以直接调用 `BaseTool` 内置的公式规范化、语法解析、调用 Evaluator 评估以及结果格式化等辅助方法，无需重复实现底层逻辑。

## 工具调用解析器：`BaseParser` { #tool-call-parser }

注意：这里的 Parser 指的是**大模型工具调用解析器**（解析“调哪个工具、传什么参数”），而不是数学表达式解析器（解析数学公式本身由 [SRHarness 符号引擎](engine.md) 负责）。

不同模型服务商返回工具调用的方式各不相同：有的支持 OpenAI 原生 Function Calling，有的只能输出特定格式的 JSON 或 XML/文本块。`BaseParser` 的作用就是屏蔽这些差异，让 `SRAgent` 主循环始终只面对统一的 `ToolCall` 和 `ToolCallResult` 对象。

`BaseParser` 负责以下三步转换：

1. **声明工具（Tools → Prompt / Schema）**：将当前启用的工具名称、功能说明和参数 Schema 转换成模型接口要求的格式；
2. **解析调用（Model Output → `ToolCall`）**：从模型的回复中提取出零个或多个标准的 `ToolCall` 对象；
3. **回填结果（`ToolCallResult` → Messages）**：将工具执行结果组装成下一轮对话所需的消息格式。

在实际运行中：

- 当选用 **`openai` 模式**时，支持原生 Function Calling 的模型会直接收到 JSON Schema，`BaseAPI` 会将服务商返回的原生工具调用转换为标准 `ToolCall`；
- 当对接不支持原生工具调用的模型时，可切换为 **`text`、`json` 或 `xml` 模式**。此时 Parser 会把工具说明与调用格式约定写进提示词，再从模型生成的纯文本中解析出 `ToolCall`。

如果模型某一轮只输出了自然语言分析而没有调用任何工具，Parser 会返回空列表 `[]`，不会虚构调用，也不会把纯文本回复当成解析错误。
