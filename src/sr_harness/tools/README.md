# 工具开发指南 (`src/sr_harness/tools`)

> 完整的 SRHarness 使用文档与 API Reference 请参阅 [`docs/index.md`](../../../docs/index.md)。

本目录包含可供 `SRAgent` 及辅助 Agent 调用的全部工具。每个工具均继承自 `BaseTool`，通过 `@BaseTool.register(...)` 注册稳定的工具名称，并实现核心的 `execute()` 方法与可选的 `format_result_dict()` 类方法。

## 1. 最小实现示例

```python
from typing import Any, Dict

from .base_tool import BaseTool, ToolMetadata


@BaseTool.register("my_tool")
class MyTool(BaseTool):
    """One-line summary of the tool class."""

    metadata = ToolMetadata(name="my_tool")

    def execute(self, value: str, limit: int = 10) -> Dict[str, Any]:
        """Concise description shown to the Agent as metadata.description.

        Args:
            value: Description of value for the parameter JSON Schema.
            limit: Maximum number of items to process (default 10).

        Returns:
            Dict[str, Any]: Structured result dictionary.
        """
        return {"value": value, "limit": limit}
```

## 2. 开发规范与元数据推断

1. **继承与注册**：
   - 继承 `BaseTool`，并在类定义上添加 `@BaseTool.register("tool_name")`。
   - 设置类属性 `metadata = ToolMetadata(name="tool_name")`，确保 `metadata.name` 与注册名完全一致。
   - **仅注册成熟稳定的工具**：凡是通过 `@BaseTool.register(...)` 注册的工具都会进入全局注册表。若某个实验性工具尚未测试完善，请注释掉装饰器暂不注册，以免降低 Agent 调用成功率或浪费 Token。
2. **实现 `execute()` 方法**：
   - `execute()` 的参数由大模型直接生成，因此应保持扁平、简洁，只使用 JSON 可序列化的基础类型（`str`、`int`、`float`、`bool`、`list`、`dict`），并补齐类型标注。
   - 返回值必须是 `Dict[str, Any]`，用于运行日志记录与候选公式提取。
3. **自动推断与显式指定 `metadata`**：
   - 若未显式传入 `metadata.description` 和 `metadata.parameters`，`BaseTool` 会在子类定义时自动从 `execute()` 的 Google-style docstring 与函数签名推断：
     - `Args:` 之前的段落会作为工具的 `metadata.description`；
     - 函数签名、类型标注、默认值以及 `Args:` 下各参数的说明会自动组装为 JSON Schema。
   - 因为这些文本直接面向大模型 Agent，请务必写得**简练、准确、边界清晰**（例如写明取值范围、支持的表达式写法以及何时会返回可提交的候选公式）。
   - 如果需要更复杂的 JSON Schema 约束，也可以在 `ToolMetadata(name=..., description=..., parameters=...)` 中显式声明，手动指定的字段不会被自动推断覆盖。
4. **重写 `format_result_dict(cls, result)`（推荐）**：
   - 默认实现直接将 `execute()` 返回的字典转为字符串。
   - 当返回字典包含大量中间字段或长数组时，请重写 `format_result_dict()`，将其精炼为结构清晰、高信噪比的短文本（`result_str`）发回给 Agent，既节省上下文窗口，也便于模型抓住重点。

## 3. 读取运行时上下文 (`self.context`)

数据集数组、评测器与工作区状态统一保存在工具实例的 `self.context`（类型为 `AgentContext`）中，无需让模型通过参数传入：

- `self.context.data`：当前数据集字典 `{name: np.ndarray}`，包含所有观测变量与坐标轴。
- `self.context.target`：当前任务的目标因变量名称字符串。
- `self.context.train_split` / `self.context.validation_split`：由当前 `Evaluator` 首次切分后自动缓存的只读训练集与验证集上下文视图。
- `self.context.workspace`：当前对话绑定的隔离工作区对象（`Workspace`）。

## 4. 公式解析与统一评估协议

### 使用 `sr_harness_engine` 处理公式

在工具内部解析或操作数学公式时，请统一调用 `self.parse_formula(expr_str)` 或直接使用 `sr_harness_engine`（如 `engine.parse()`、`Expression.eval()`），不要手写 `eval()` 或私自拼接字符串求值。

### 调用 `self.evaluate()` 返回标准候选结构

凡是会生成、拟合或评估数学公式的工具（如多项式拟合、幂律拟合、有理函数拟合、PySR/SINDy 搜索等），都应调用 `self.evaluate(f=..., y=...)` 生成标准化的评估字典：

```python
evaluation = self.evaluate(
    f=formula_expression,
    y=target_expression,
    show_diagnostics=show_diagnostics,
)
return {
    **evaluation,
    "custom_field": extra_info,
}
```

`self.evaluate()` 的核心行为约定：

- `f` 与 `y` 必须是 `sr_harness_engine.Expression` 实例。
- 当左端项 `y` 恰好等于 `self.context.target`、右端项 `f` 不依赖目标变量且在各数据切分上产生有限 MSE 时，`self.evaluate()` 会自动将 `is_candidate` 设为 `True`，使其自动进入 `SRAgent` 的全局 Top-k 榜单与帕累托前沿。
- 训练集与验证集的评测指标分别保存在 `data_split_results["train"]["metrics"]` 和 `data_split_results["validation"]["metrics"]` 中（当未划分验证集时不包含 `"validation"` 键）。
- 默认开启残差诊断（`show_diagnostics=True`），在 `data_split_results["train"]["diagnostics"]` 中附上误差分位数、最大残差样本及残差相关性最强的变量；工具内部在做网格筛选或 Pareto 备选评估时可传入 `show_diagnostics=False`，仅对最终选出的主公式保留完整诊断。
- 若像 `EvaluateCodeTool` 那样在沙箱中直接得到了数值预测数组，可调用 `self.calculate_metrics(f, y_true, y_pred)` 与 `self.residual_diagnostics(...)` 复用一致的指标计算逻辑。

## 5. 异常处理与警告约定

- **不阻塞主流程的局部警告**：将警告字符串收集到返回字典的 `"exceptions": list[str]` 字段中（例如多个输入特征中某一个表达式求值失败，但其余特征仍可正常拟合），并在 `format_result_dict()` 中展示给 Agent。
- **无法继续执行的错误**：直接抛出 `ValueError` 或 `RuntimeError`（可将已收集的 `exceptions` 附在报错信息中）。`BaseTool.__call__()` 会自动捕获常规异常，将其格式化为 `ok=False` 的工具结果返回给模型，引导模型在下一轮修正参数；只有需要立刻中断整场运行的致命控制流异常才抛出 `ToolRunAbort`。

## 6. 运行时创建与编辑自定义工具 (`create_skill` / `edit_tool`)

Agent 可以在搜索过程中将复用的数据分析脚本或公式提议逻辑沉淀为 Skill 及配套的自定义工具：

```text
skills/<skill-name>/SKILL.md
skills/<skill-name>/tool.py
```

### 通过 `create_skill` 生成技能或工具

调用 `create_skill(request="...")` 时，工具会将当前 Agent 的对话上下文（可通过 `history_messages=N` 限制最近消息条数）与本次需求一并发送给配置的 LLM，由模型自动判断应创建哪一类 Skill 并完成内部多轮校验：

- **`instructions`**：仅生成说明文档 `SKILL.md`，不包含 `tool.py`。
- **`data_analysis`**：同时生成 `SKILL.md` 与用于数据特征分析的 `tool.py`（继承 `BaseTool`，从 `self.context.data` 读取数据并返回分析字典）。
- **`formula_proposer`**：同时生成 `SKILL.md` 与用于提出候选公式的 `tool.py`（必须在 `execute()` 中调用并返回/合并 `self.evaluate(...)` 的结果，以保留 `formula`、`is_candidate` 与 `data_split_results`）。

默认不会覆盖已存在的同名 Skill；若传入 `force=True`，可替换非只读 Skill 下的 `SKILL.md` 与 `tool.py`（保留目录中的其他附件文件）。

### 自定义 `tool.py` 的安全沙箱约定

- `tool.py` 必须且只能定义一个继承自 `BaseTool` 的子类，并声明唯一的 `metadata.name`。
- **禁止在自定义 `tool.py` 中使用 `@BaseTool.register(...)`**：加载器会在独立沙箱进程中静态检查并提取 `metadata`，在主进程中自动生成 `SandboxedCustomTool` 代理类并以 `metadata.name` 完成注册。
- 需要修改已创建的自定义工具时，调用 `edit_tool` 传入 Skill 目录名与精确匹配的 `SEARCH/REPLACE` 补丁块即可完成热更新与重新加载。

## 7. 自定义 Evaluator 与数据划分

SRHarness 内置了面向常规数据的 `DefaultEvaluator` 和面向图/超图数据的 `GraphEvaluator`。如需针对特定科学问题（如常微分方程轨迹积分、网络动力学演化）定制拟合或评价标准，可继承 `DefaultEvaluator` 并按需重写类方法：

- 重写 `fit_candidate(cls, f, context)` / `evaluate_candidate(cls, f, context)`：仅改变正式候选公式的参数拟合或指标计算方式（推荐）；
- 重写 `fit(cls, f, y, context)` / `evaluate(cls, f, y, context)`：同时改变普通探索等式与正式候选公式的拟合或评测方式；
- 重写 `split(cls, context)`：自定义训练集与验证集的切分方式（如按时间先后顺序切分）。

注意：`fit*` 必须返回所有参数均已绑定数值的 `Expression`；`evaluate*` 必须返回仅含 `float` 或 `int` 数值的扁平字典。详细说明与代码示例请参阅 [`docs/evaluator.md`](../../../docs/evaluator.md)。
