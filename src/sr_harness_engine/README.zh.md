# SRHarness Engine 符号模型语言规范

> 网页版完整指南与自动生成的 API Reference 请参阅 [`docs/engine.md`](../../docs/engine.md)。

`sr_harness_engine` 是 SRHarness 的底层符号表达式引擎，负责将数学公式字符串安全地解析为结构化语法树（AST），并提供规范化字符串/LaTeX 渲染、NumPy 向量化求值、常数优化拟合以及面向**有向图**、**超图**与**时延（Delay）**的扩展下标语法。

在职责划分上，本引擎专注于描述和计算方程的**右端项（RHS）**；至于左端目标变量（如 `y = f(x)`、`dx/dt = f(x)`）、数据集切分、ODE 轨迹积分以及评价指标汇总，则由上层的 [Evaluator](../../docs/evaluator.md) 与 SRHarness 运行时负责。

## 1. 核心设计原则

1. **结构化表示优先**：所有正式候选公式都必须表示为可遍历、可分析的结构化表达式树（`Expression`），而非黑盒 Python 函数。
2. **贴近直觉且语义严格**：表层写法尽量贴近日常数学与 Python 算术习惯，同时每个语法树节点都具备明确、可静态检查的计算语义。
3. **统一的指标缩并机制**：图（二元关系）、超图（三元及更高阶关系）共用同一套“显式下标绑定 + 求和归约（`sum`）”模型，无需引入互不兼容的专用 DSL。
4. **严格区分变量、参数与常数**：数据集变量（`Symbol`/`Variable`）、待拟合自由参数（`param`/`grouped_param`）与字面数值（`Number`）是三类截然不同的节点；引擎本身不会把拼写错误的变量名悄悄当成待拟合参数。
5. **安全解析边界**：字符串解析基于受限 AST 白名单，不调用 `eval()`，也不执行任何任意 Python 代码。
6. **由自由下标决定输出维度**：表达式求值结果的末尾结构维度由尚未被 `sum[...]` 归约消去的自由下标按首次出现顺序决定。

## 2. Python 快速示例

```python
import numpy as np
import sr_harness_engine as engine

expression = engine.parse(
    "param('alpha', value=0.3) * x1 / (1 - param('alpha')) + param('beta')"
)
fit = expression.fit(
    {"x1": np.arange(10, dtype=float)},
    2 * np.arange(10, dtype=float) + 1,
)

print(expression)             # 规范化公式字符串
print(fit.parameters)         # 拟合得到的命名参数字典 {'alpha': ..., 'beta': ...}
prediction = fit.predict({"x1": np.array([10.0, 11.0])})
```

除了从字符串解析，也可以使用 `Symbol` 在 Python 中直接组合表达式：

```python
x1 = engine.Symbol("x1")
x2 = engine.Symbol("x2")
expression = 2.0 * engine.sin(x1) + x2
```

`Symbol` 支持绑定默认数组（测试时很方便），但在正式工具与 Evaluator 中建议始终在 `evaluate(data)` 时显式传入数据字典：

```python
x = engine.Symbol("x", value=np.array([1.0, 2.0]))
assert np.allclose((x + 1).evaluate(), [2.0, 3.0])
```

## 3. 标量运算、初等函数与常量折叠

基础算术使用标准的 Python 运算符 `+`、`-`、`*`、`/` 和乘方 `**`：

```text
x1 + x2
2.0 * sin(x1)
x1 ** 2 + exp(-x2)
```

内置支持的逐元素（Elementwise）初等函数包括：

```text
abs  sin  cos  tan  sinh  cosh  tanh
arcsin  arccos  arctan
exp  log  log10  log2  sqrt
sigmoid  sign  sec  sech  csc  cot  inv
```

常用函数别名会在解析时自动归一为标准名称：

- 自然对数：`log`（别名 `ln`）；
- 常用对数（以 10 为底）：`log10`（别名 `lg`）；
- 二进制对数：`log2`；
- 反三角函数：`arcsin`（别名 `asin`）、`arccos`（别名 `acos`）、`arctan`（别名 `atan`）。

公式中的字面数字（如 `2.0`、`3`）视为固定常数，不参与参数优化。解析器会自动折叠不依赖变量和待拟合参数的纯常数加、减、乘法子表达式，但会刻意保留除法、幂次和函数调用形式（如 `2 / 3`、`x ** (4 / 3)`、`sqrt(2)`），避免有意义的精确有理数或根式退化为近似浮点数：

```python
expression = engine.parse("y + (2 * 3) * x")
assert str(expression) == "y + 6 * x"
```

## 4. 待拟合参数（`param` 与 `grouped_param`）

### 命名标量参数：`param`

需要由数值优化器拟合的自由标量参数必须用 `param` 显式声明：

```text
param('alpha', value=0.3) * x1 / (1 - param('alpha')) + param('beta')
```

- 同一表达式中多次出现的同名 `param('alpha')` 共享同一个参数值；
- 可选的 `value` 同时作为未拟合时的默认求值初值和优化器的初始猜测值（同一表达式内对同名参数声明冲突的 `value` 会直接报错）；
- 未指定 `value` 的参数在拟合前不能直接求值；拟合时默认以 `1.0` 作为初值，也可通过 `initial` 字典传入自定义初值：

```python
fit = expression.fit(data, target, initial={"beta": 0.0})
value = fit.expression.evaluate(data)
```

`expression.fit(...)` 默认最小化均方误差（MSE，基于 `scipy.optimize.minimize`），返回包含已绑定参数新表达式 `fit.expression` 的 `FitResult` 对象，不会原地修改原表达式。若传入的对象自带 `data`、`target` 和可选的 `num_nodes`（如 `AgentContext`），也可简写为 `expression.fit(context)` 与 `expression.evaluate(context)`。

`expression.count_parameters(data)` 用于统计表达式中独立待拟合参数的总数（同名 `param` 只计一次，字面常数不计入；`grouped_param` 在传入数据时按实际离散类别数计入）。

### 按类别分组参数：`grouped_param`

当数据集中包含离散分组或类别变量 `s`（如不同实验批次、不同材料）时，可用 `grouped_param` 为每个类别分别拟合一个专属参数：

```text
grouped_param(s) * x
grouped_param(s, name='slope', default=0.0) * x
grouped_param(s, name='slope', value={'A': 1.0, 'B': 2.0}) * x
```

同一类别下的样本共享同一个系数值，不同类别各自独立优化。省略 `name` 时，分组变量 `s` 的默认参数键名为 `grouped:s`。

## 5. 图与超图的显式下标语法

网络与高阶交互关系通过整数端点表表示，约定**目标节点（Target）在第 0 列、源节点（Source）在后续列**：

- **二元有向图 `A.shape == (E, 2)`**：每行依次为 `(target, source)`；
- **三元有向超图 `T.shape == (H, 3)`**：每行依次为 `(target, source1, source2)`。

表达式中的下标按关系表的列顺序依次绑定：

```text
x[i] + sum[j](A[i, j], x[i] * x[j])
```

求值含下标的表达式时必须显式传入节点总数 `num_nodes`（引擎不会仅从边表中的最大节点编号猜测总节点数，从而保证没有任何入边的孤立节点也能完整保留）：

```python
prediction = expression.evaluate(data, num_nodes=10)
```

上面公式的求值过程分为五步：

1. `A[i, j]` 将目标下标 `i` 绑定到 `A` 的第 0 列，源下标 `j` 绑定到第 1 列；
2. `x[i]` 与 `x[j]` 按各条边的端点索引收集对应的节点状态；
3. `sum[j]` 沿源下标 `j` 求和归约，将结果按自由目标下标 `i` 聚合到各个目标节点；
4. 聚合结果排列为长度为 `num_nodes` 的节点轴（孤立节点处取值为 `0`）；
5. 与外层的节点项 `x[i]` 按相同的自由下标 `i` 对齐相加。

**维度与广播约定**：结构化变量的最后一维固定为结构维——节点变量形状为 `(..., N)`，边属性为 `(..., E)`，超边属性为 `(..., H)`，前面的样本或时间维遵循标准 NumPy 广播规则。同一公式中凡是涉及结构维的变量都必须显式写出下标（例如已使用 `x[i]` 的公式中不能混用不带下标的 `x`）。

如果最终表达式保留了多个自由下标，它们会按首次出现顺序展开为结果末尾的稠密维度（例如 `x[i] + x[j]` 输出形状为 `(..., N, N)`，`x[i] * x[j] * x[k]` 输出形状为 `(..., N, N, N)`）。

在 `sum[j](A[i, j], eq)` 中，第一个参数 `A[i, j]` 是稀疏关系掩码/权重因子，第二个参数 `eq` 是仅需在存在边的位置求值的被加数。三元超图及全局节点求和也可自然组合：

```text
x[i]
+ sum[j](A[i, j], x[i] * x[j])
+ sum[j, k](T[i, j, k], x[i] * x[j] * x[k])
+ sum[j](A[i, j], x[i] * sum[k](x[k]) * x[j])
```

关系项自身也支持代数运算（如 `A1[i, j] + A2[i, j]` 表示边叠加，`A1[i, j] * A2[i, j]` 表示边交集）。即使对关系做平移或非线性变换（如 `A[i, j] + 1`、`exp(A[i, j])`），求值器依然通过记录背景默认值 `fill_value` 与稀疏偏离坐标来计算，避免构造稠密的 $N \times N$ 矩阵。同一关系表内的重复边按集合语义自动去重；若需表示重边权重，请使用独立的边属性变量。

### `gather`：提取边级或超边级特征

当需要在每条边或超边上计算特征而不立即对邻居求和时，使用 `gather`：

```text
gather(A[i, j], x[i] + x[j])          # 输出形状: (..., E)
gather(T[i, j, k], x[i] * x[j] * x[k]) # 输出形状: (..., H)
```

`gather` 的结果与普通边属性数组完全一样，可以直接参与四则运算、初等函数调用，或者再次附加上标 `[i, j]` 放回 `sum` 中聚合：

```text
2 * gather(A[i, j], x[i] + x[j]) + w
sum[i](A[i, j], gather(A[i, j], x[i] + x[j])[i, j] * x[i] * x[j])
```

### `aggr / targ / sour` 简写语法糖

对于常见的二元有向图消息传递，引擎兼容类似 `nd2py` 的简写语法：

```text
aggr(A * targ(x) * sour(x))
aggr(A, targ(A, x) * sour(A, x))
aggr(A, targ(x) * sour(x))
```

其中 `targ` 取第 0 列目标节点，`sour` 取第 1 列源节点，`aggr` 对入边邻居求和。解析器在读取这三种写法后会立即将其展开（Desugar）为标准下标形式 `sum[j](A[i, j], x[i] * x[j])`，因此 `str(expression)` 会统一渲染为显式下标表达式。

### 边属性字段（Relation Fields）

在关系求和内部，带完整关系下标的普通变量代表按边/超边行顺序对齐的属性字段（如边权重 `w`，形状为 `(E,)` 或 `(..., E)`）：

```text
sum[j](A[i, j], w[i, j] * x[i] * x[j])
```

当上下文中仅有一个同元数、同长度的关系表时，引擎会自动将 `w[i, j]` 关联到该关系；若存在多个同尺寸关系表，可通过 `RelationField(w, relation="A")` 显式指定，无需把边权展开成 $N \times N$ 稠密矩阵。

注意：显式编写嵌套 `sum` 时，内层不能重复使用外层尚未归约的同名下标（即 `sum[j](... sum[j](...) ...)` 会报错，内层应改用 `sum[k]`）。

## 6. 时延表达式（`delay`）

```text
x + delay(x, delta)
```

`delay(value, delta)` 表示读取状态序列在 $t - \delta$ 时刻的历史值。默认求值器沿数组第 0 轴（时间维）进行一维线性插值，`delta` 可以是正标量或与时间轴等长的数组，早于初始时刻的位置返回 `NaN`：

```python
expression.evaluate(
    {"x": x, "delta": delta},
    time=np.asarray(time),
)
```

自定义 ODE/DDE 评估器也可以通过 `delay_resolver` 参数接入外部积分器的历史状态查询函数：

```python
expression.evaluate(data, delay_resolver=my_history_lookup)
```

## 7. 字符串往返（Round-trip）与安全边界

任何合法表达式均满足 `parse(str(expression))` 结构等价：渲染器会自动补齐保持运算优先级所需的最小括号，并完整保留命名参数的名称与初值。

解析器严格拒绝属性访问（`.`）、切片（`x[0:10]`）、推导式、`lambda`、未注册函数调用及非常量关键字参数，确保所有表达式树都能被安全遍历、求值与比较。

## 8. 引擎边界与后续演进方向

当前版本的 `sr_harness_engine` 已完整支持算术与初等函数解析、规范化与 LaTeX 渲染、NumPy 广播求值、命名参数与分组参数优化、二元关系语法糖、任意元关系的显式下标缩并、`gather` 边特征提取以及基础时延插值。

为了保持底层引擎精简可靠，以下能力有的由上层 `sr_harness` 运行时与工具层提供，有的作为后续演进方向：

- **已由上层运行时与工具层提供**：
  - 子树级数值稳定性诊断（由 `src/sr_harness/tools/eic.py` 中的 `EICTool` 基于本引擎的树遍历与路径替换接口实现）；
  - 数据切分、常微分方程轨迹积分与任务级指标评测（由 `sr_harness.evaluator` 中的 `DefaultEvaluator`、`GraphEvaluator` 与 `evaluator.utils` 实现）；
  - 任意 Python 代码沙箱评估（由 `EvaluateCodeTool` 在操作系统沙箱中实现，不属于本符号模型语言）。
- **后续引擎演进方向**：
  - 量纲、物理单位与输出形状的静态类型检查；
  - 跨代数变形的规范化（Canonicalization）与结构哈希等价判定；
  - 多方程联立（多 RHS）的具名系统模型表示；
  - 可选的 JAX / PyTorch 自动微分求值后端，以及支持参数上下界约束与鲁棒损失的优化器选项。

## 9. 与 SRHarness `Evaluator` 的对接方式

在 SRHarness 中，`DefaultEvaluator` 与 `GraphEvaluator` 接收本引擎的 `Expression` 对象，负责数据切分、参数拟合与指标打分。用户只需继承 `DefaultEvaluator` 即可定制候选公式的评测协议：

```python
from sr_harness import DefaultEvaluator


class MyEvaluator(DefaultEvaluator):
    @classmethod
    def evaluate_candidate(cls, f, context):
        metrics = super().evaluate_candidate(f, context)
        metrics["custom_metric"] = 0.0
        return metrics
```

其中 `fit` / `evaluate` 处理一般探索等式 `y = f`，`fit_candidate` / `evaluate_candidate` 处理预测目标变量的正式候选公式；复杂度统计、残差诊断与文本格式化由工具层统一完成。
