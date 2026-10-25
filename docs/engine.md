# SRHarness 符号引擎

`sr_harness_engine` 是 SRHarness 的底层数学表达式引擎。它负责把公式字符串安全地解析为抽象语法树（AST），并提供规范化渲染、NumPy 数值求值、常数优化拟合、常量折叠化简，以及面向**图（Graph）**、**超图（Hypergraph）**和**时延（Delay）**的扩展数学语法。

符号引擎专注于“数学表达式本身的计算与变换”；至于数据集切分、候选公式筛选或 ODE 轨迹积分等任务级逻辑，则由 [Evaluator](evaluator.md) 和上层运行时负责。

## 1. 快速上手

几行代码即可完成“解析含参公式 → 在数据上拟合参数 → 求值预测”的全流程：

```python
import numpy as np
import sr_harness_engine as engine

x = np.linspace(-2.0, 2.0, 101)
target = 2.5 * np.sin(x) - 0.4

model = engine.parse("param('a') * sin(x) + param('b')")
fit = model.fit({"x": x}, target)

print(fit.expression)          # 填入拟合后数值的完整表达式
print(fit.parameters)          # 拟合得到的参数字典 {'a': ..., 'b': ...}
print(fit.loss)                # 拟合损失
print(fit.evaluate({"x": x})[:3])
```

安全边界：`engine.parse()` 基于受限的 Python AST 白名单解析语法节点，**不调用 `eval()`**，也不执行任意 Python 代码。

## 2. 基础表达式语法

### 数值、变量与四则/幂运算

```text
1.5
x
x1 + x2
x1 - x2
x1 * x2
x1 / x2
x ** 2
-x
```

支持加（`+`）、减（`-`）、乘（`*`）、除（`/`）、幂运算（`**`）和一元负号（`-`）。

!!! tip "关于乘方符号 `**` 与 `^`"
    在 Python 中，`^` 是按位异或运算符而非乘方。虽然上层公式评估工具在接收大模型输出时会自动将 `^` 转换为 `**`，但在 Python 代码中直接调用 `engine.parse()` 时，请始终使用 `**` 表示乘方。

### 内置数学函数

引擎内置了常用的逐元素（Elementwise）初等函数：

```text
sin cos tan sinh cosh tanh
arcsin arccos arctan
exp log log10 log2 sqrt abs
sigmoid sign sec sech csc cot inv
```

常用别名会自动归一为标准名称，避免同一公式因函数名写法不同而在候选池中产生重复条目：

- 自然对数：`log(x)` 与 `ln(x)` 等价（解析后统一为 `log`）；
- 常用对数（以 10 为底）：`log10(x)` 与 `lg(x)` 等价（统一为 `log10`）；
- 二进制对数：`log2(x)`；
- 反三角函数：`arcsin`/`asin`、`arccos`/`acos`、`arctan`/`atan` 均支持（统一为带 `arc` 前缀的标准名）。

除了用字符串解析，你也可以直接用 Python 符号 API 拼接表达式：

```python
x = engine.Symbol("x")
expression = engine.exp(-x) * engine.sin(2 * x)
```

## 3. 待拟合参数（Parameters）

### 命名标量参数：`param`

在公式中用 `param('名称')` 声明一个需要由优化器拟合的自由常数：

```text
param('slope') * x + param('bias')
param('a', value=0.3) * x
```

- 同一个公式中出现多次同名 `param('a')` 时，它们代表**同一个共享参数**；
- `value` 既是未拟合直接求值时的默认值，也是优化器拟合时的初始猜测值；
- 也可在调用 `engine.fit()` 时通过 `initial` 参数统一指定初值：

```python
fit = engine.fit(
    engine.parse("param('a') * x + param('b')"),
    {"x": x},
    target,
    initial={"a": 1.0, "b": 0.0},
)
```

### 按类别分组参数：`grouped_param`

当数据集中包含离散类别标签（如不同材料、不同实验批次 `label`），且不同类别遵循相同的公式结构但具有不同的系数值时，可以使用 `grouped_param`：

```text
grouped_param(label, name='rate') * x
```

优化器会自动为每个类别单独拟合一个专属参数值。你也可以显式传入各类别的取值字典与默认值：

```text
grouped_param(
    label,
    name='rate',
    value={'A': 1.0, 'B': 2.0},
    default=0.0,
) * x
```

## 4. 解析、渲染与安全边界

引擎支持将表达式树渲染为标准字符串或 LaTeX 公式，且渲染结果再次解析后完全一致（Round-trip）：

```python
expression = engine.parse("x ** (4 / 3) + sqrt(2)")
text = engine.render(expression)
latex = engine.render(expression, latex=True)

assert str(engine.parse(str(expression))) == str(expression)
```

为了杜绝代码注入风险，解析器严格拒绝属性访问（`.`）、切片（`[a:b]`）、列表推导式、`lambda`、未注册函数调用以及非常量关键字参数。例如以下写法都会被直接拦截报错：

```text
np.sin(x)
__import__('os')
x[0:10]
custom_python_function(x)
```

## 5. 数值求值（Evaluation）

```python
expression = engine.parse("sin(x) + y ** 2")
value = expression.evaluate({"x": x, "y": y})
```

各变量数组之间遵循标准的 NumPy 广播（Broadcasting）规则。如果表达式中含有未绑定数值的 `param`，求值时可以通过 `parameters` 字典临时传入：

```python
expression.evaluate(
    {"x": x},
    parameters={"a": 2.0, "b": -0.5},
)
```

（也可调用等价的模块级函数 `engine.evaluate(expression, values)`。）

## 6. 表达式树结构与遍历

所有语法树节点均继承自 `Expression`，常见节点类型如下：

| 节点类名 | 表示内容 |
|---|---|
| `Number` | 固定数值常量 |
| `Symbol` / `Variable` | 数据集变量 |
| `Parameter` | 命名标量参数（`param`） |
| `GroupedParameter` | 按类别分组参数（`grouped_param`） |
| `Unary` / `Binary` | 一元或二元算术运算 |
| `Function` | 内置数学函数调用 |
| `Indexed` | 带自由下标的变量（如 `x[i]`、`A[i, j]`） |
| `Reduction` | 下标求和归约（如 `sum[j](...)`） |
| `Gather` / `Aggregate` / `RelationLift` | 图与超图关系运算节点 |

常用的树遍历、拷贝、常量折叠与参数统计操作：

```python
for node in expression.iter_preorder():
    print(type(node).__name__, node)

copy = expression.copy()
simplified = expression.fold_constants()
count = expression.count_parameters()
```

其中 `node.operands` 返回当前节点的直接子节点元组，`expression.replace(old, new)` 则按节点对象身份（Identity）返回替换后的新表达式树。

## 7. 图与超图下标语法

处理复杂网络或耦合动力学系统时，关系变量采用**“目标节点在前、源节点在后”**的存储约定：

- **有向图 `A.shape == (E, 2)`**：每行表示一条有向边 `(target, source)`；
- **三元有向超图 `T.shape == (H, 3)`**：每行表示一条超边 `(target, source1, source2)`。

### 邻居消息聚合（`sum`）

要对节点 $i$ 的所有入边邻居 $j$ 求和，可以直接使用直观的下标语法：

```text
sum[j](A[i, j], x[i] * x[j])
```

这里 `A[i, j]` 将边的第 0 列（目标节点）绑定为下标 `i`，第 1 列（源节点）绑定为下标 `j`；外层的 `sum[j]` 则沿着源节点 `j` 求和归约，最终输出按目标节点 `i` 对齐的数组。

在图数据上求值时，建议传入 `num_nodes` 参数，以确保即使图中存在没有任何入边的孤立节点，输出数组依然保持完整的节点维度 `(..., N)`：

```python
prediction = expression.evaluate(data, num_nodes=10)
```

数据维度约定：节点变量形状为 `(..., N)`，边属性为 `(..., E)`，超边属性为 `(..., H)`；前面的样本/时间维按 NumPy 规则自动广播，最后一维为结构维。

### 超图消息聚合

三元超图的高阶交互写法完全一致，只需同时消去两个源节点下标 `j, k`：

```text
sum[j, k](T[i, j, k], x[i] * x[j] * x[k])
```

### 边级特征提取（`gather`）与边属性字段

如果不想立即对邻居求和，而是想在每条边或超边上计算一个值（输出形状为 `(..., E)` 或 `(..., H)`），可以使用 `gather`：

```text
gather(A[i, j], x[i] + x[j])
gather(T[i, j, k], x[i] * x[j] * x[k])
```

如果数据集中还包含定义在边上的权重或属性 `w`（形状为 `(E,)` 或 `(..., E)`），也可以直接用相同的下标 `[i, j]` 参与聚合：

```text
sum[j](A[i, j], w[i, j] * x[i] * x[j])
```

（当上下文中存在多张不同的关系图时，可通过 `RelationField(w, relation="A")` 明确指定 `w` 对应哪张关系表。）

### 语法糖（`aggr` / `targ` / `sour`）

为了兼容部分简写习惯，引擎还支持 `aggr`、`targ`（目标节点）与 `sour`（源节点）简写：

```text
aggr(A * targ(x) * sour(x))
aggr(A, targ(x) * sour(x))
```

解析时，这两种写法都会自动展开（Desugar）为标准的下标表达式 `sum[j](A[i, j], x[i] * x[j])`，因此在渲染输出时统一显示为标准下标形式。

## 8. 时延表达式（`delay`）

对于时滞微分方程（DDE）或带有历史记忆的系统，可以使用 `delay(x, delta)` 表示状态 $x$ 在 $t - \delta$ 时刻的取值：

```text
x + delay(x, delta)
```

默认求值器会沿着时间轴（第 0 轴）对 $x(t - \delta)$ 进行线性插值，早于初始时刻的位置返回 `NaN`：

```python
prediction = engine.parse("delay(x, delta)").evaluate(
    {"x": trajectory, "delta": lag},
    time=sample_times,
)
```

如果你编写了自定义的 ODE/DDE Evaluator，也可以在求值时传入自定义的 `delay_resolver` 来对接外部积分器的历史状态缓存。

## 9. 常量折叠与复杂度计算

`fold_constants()`（以及解析时的默认化简）会自动合并纯常数子表达式，同时保留分数、幂次和命名函数的可读结构：

```python
expression = engine.parse("(2 + 3) * x")
assert str(expression) == "5 * x"
```

- `expression.count_parameters()`：统计表达式中待拟合参数的数量；
- `len(expression)`：返回表达式树的总节点数（`DefaultEvaluator` 默认将节点数作为公式复杂度 `complexity`）。

## 10. 与 Evaluator 协同工作

如 [公式评估与自定义 Evaluator](evaluator.md) 所述，`DefaultEvaluator` 通过以下 5 个入口调用符号引擎：

```python
split(context)
fit(f, y, context)
evaluate(f, y, context)
fit_candidate(f, context)
evaluate_candidate(f, context)
```

一般等式走 `fit` / `evaluate`，而预测目标变量的正式候选公式走 `fit_candidate` / `evaluate_candidate`。配合 `from sr_harness.evaluator import utils` 中的指标与积分工具，你可以轻松组合出适应各种物理与工程场景的评测器。

## 11. 行为测试与代码示例

仓库中的 `tests/behavior/` 目录包含了覆盖所有语法特性的可执行示例：

- `test_basic_expressions.py`：基础算术、函数解析、渲染与安全拦截测试；
- `test_parameters.py`：命名标量参数与分组参数拟合；
- `test_relations.py`、`test_gather.py`：图、超图聚合与边特征提取；
- `test_delay.py`：时延插值求值；
- `test_simplification.py`：常量折叠与参数计数；
- `test_custom_evaluator.py`：自定义 Evaluator 扩展边界。

可通过以下命令直接运行这些行为测试：

```bash
pytest tests/behavior
```

完整的公开类与函数签名请查阅 [API Reference](reference/index.md)。
