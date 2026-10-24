# 结构化数据与 `context.data`

在 SRHarness 中，所有参与符号回归的数据都统一保存在工作区的 `context.data/` 目录下：每个变量（以及较长的坐标轴）各自存为一个 `.npy` 数组文件，而同目录下的 `manifest.json` 则负责登记这些变量的名称、物理含义、维度对应的坐标轴，以及图或超图的拓扑结构。

为了方便理解，下文将各项要求分为三类：

- **硬性规则**：必须严格遵守，违反时数据加载器会直接报错；
- **语义约定**：决定用户与 Agent 如何理解数据含义（例如图边表的列顺序），程序不一定能自动识别语义错误；
- **实践建议**：有助于提升数据质量与实验可靠性，但不会阻塞数据加载。

!!! warning "实验设计提醒：切勿在变量描述中泄露答案"
    编写变量描述（`description`）时，请只说明变量的物理含义、单位或测量方式，**不要写入待发现的真实公式或暗示其具体函数形式**（例如不要写成“由 `y = 1 + x**2` 生成的目标值”或“指数衰减项”）。加载器只能检查 `description` 是否为非空字符串，无法判断自然语言是否泄题。

## 1. 目录结构

一个标准的 `context.data/` 目录如下所示：

```text
context.data/
├── manifest.json  # 数据清单：登记变量、坐标轴与网络拓扑
├── x.npy          # 变量数组
├── y.npy          # 变量数组
├── time.npy       # 较长的坐标轴也可以单独存为 .npy
└── A.npy          # 图或超图的边关系同样作为变量存储
```

核心要求如下：

- **硬性规则**：目录顶层必须包含合法的 `manifest.json`；所有被引用的 `.npy` 文件都必须直接放在 `context.data/` 根目录下，文件名中不能包含子目录路径。
- **硬性规则**：每个 `.npy` 文件必须保存一个可通过 `np.load(..., allow_pickle=False)` 安全读取的 `numpy.ndarray`。禁止使用 `object` 类型（`dtype=object`）；若需保存文本类别变量，请使用 NumPy Unicode 或定长字符串类型。
- **实践建议**：如果目录中存在未被 `manifest.json` 引用的临时 `.npy` 文件，校验时只会给出警告而不会报错，方便数据清洗过程中暂存中间结果；但在正式启动搜索前，建议清理或登记这些文件。

## 2. `manifest.json` 顶层字段

`manifest.json` 的根对象只允许包含以下三个字段（出现未知字段、缺失必填项或存在重复的 JSON Key 都会导致校验失败）：

| 字段名 | 是否必填 | 说明 |
|---|---|---|
| `variables` | **必填** | 非空字典，登记数据集中所有的观测变量（包括图/超图的关系矩阵）。 |
| `axes` | **必填** | 字典，登记变量所引用的全部坐标轴；若所有变量均为标量，可为空字典 `{}`。 |
| `num_nodes` | **按需必填** | 当存在图或超图关系变量（`kind: "relation"`）时，必须指定为正整数（表示节点总数）；没有关系变量时则**不得**出现该字段。 |

注：哪个变量作为因变量（Target）、哪些作为自变量（Features）、研究问题描述以及评测器（Evaluator）属于具体的**任务配置**，不应写进 `manifest.json` 数据清单中。

## 3. 定义变量（`variables`）

```json
{
  "variables": {
    "theta": {
      "file": "theta.npy",
      "description": "Oscillator phase in radians.",
      "axes": ["time", "node"]
    }
  }
}
```

- **字段要求**：每个变量都必须包含 `file`、`description` 和 `axes` 三个基础字段；此外仅允许按需添加 `kind`（标记关系变量）和 `structure`（绑定边/超边属性）。
- **命名与文件对应**：变量名不能为空，不能是 `.` 或 `..`，也不能包含路径分隔符或空字符（NUL）；对应的数组文件名必须严格为 `<变量名>.npy`。
- **维度与坐标轴对齐**：`axes` 是一个坐标轴名称列表。`.npy` 数组的维度数（ndim）必须与 `axes` 列表长度完全一致，且每一维的长度必须与对应坐标轴的长度相等（0 维标量使用空列表 `[]`）。
- **名称互不冲突**：加载到 `AgentContext` 后，所有变量与坐标轴会合并放入 `context.data` 字典中，因此**变量名与坐标轴名不能重名**。

## 4. 定义坐标轴（`axes`）

每个坐标轴都必须包含 `description`，并从 `values`、`file`、`size` 三种方式中**任选且仅选一种**来指定轴的长度与刻度：

```json
{
  "axes": {
    "time": {"values": [0.0, 0.1, 0.2], "description": "Time in seconds."},
    "node": {"values": ["node1", "node2", "node3"], "description": "Node label."},
    "sample": {"size": 100, "description": "Zero-based sample position."}
  }
}
```

- **`values`（内联数组）**：非空的一维 JSON 标量数组（数字或字符串），适合长度较短或带有明确类别/节点标签的坐标轴。
- **`file`（外部数组）**：指向同目录下的 `<轴名>.npy`，文件内容必须是一维数组，适合时间序列等较长的坐标轴。
- **`size`（仅指定长度）**：正整数，系统会自动生成 `0, 1, ..., size - 1` 的整数索引，适合无特殊标签的样本轴或边索引轴。
- **引用完整性**：`axes` 中登记的每一个坐标轴都必须至少被一个变量使用；反之，变量也不能引用未在 `axes` 中登记的坐标轴。

## 5. 图与超图关系（`relation` 与 `structure`）

对于网络动力学或图结构数据，边的连接关系同样作为变量登记在 `variables` 中：

```json
{
  "num_nodes": 10,
  "variables": {
    "A": {
      "file": "A.npy",
      "description": "Directed graph endpoint pairs.",
      "axes": ["edge", "endpoint"],
      "kind": "relation"
    },
    "weight": {
      "file": "weight.npy",
      "description": "Edge weight at each time.",
      "axes": ["time", "edge"],
      "structure": "A"
    }
  }
}
```

- **显式标记关系变量**：图或超图的边表必须显式声明 `"kind": "relation"`（系统不会仅凭变量名叫 `A` 或 `T` 就自动把它当成邻接关系）。
- **数组形状与取值范围**：关系数组必须是整数类型（integer dtype），形状只能是代表有向图的 `(E, 2)` 或代表三元有向超图的 `(H, 3)`，且所有节点编号都必须落在 `[0, num_nodes)` 范围内。
- **端点列顺序（语义约定）**：`(E, 2)` 每一行的两列依次为 `(target, source)`（目标节点在前，源节点在后）；`(H, 3)` 每一行的三列依次为 `(target, source1, source2)`。建议在 `endpoint` 轴的 `values` 中明确写出对应标签。
- **边上属性变量（`structure`）**：如果某个变量定义在边或超边上（即最后一维对应 `E` 条边或 `H` 条超边，如上例中的动态边权 `weight`），需要通过 `"structure": "A"` 指明它依附于哪个关系变量，且最后一维长度必须与该关系的边数一致。
- **普通节点变量**：定义在节点上的变量（如形状为 `(time, node)` 的节点状态）不需要设置 `structure`；同一个 `manifest.json` 中的所有关系共享顶层的 `num_nodes`。

## 6. 如何写好 `description`

每个变量和坐标轴都必须提供非空字符串形式的 `description`。好的描述能显著帮助 Agent 理解数据背景并提出合理的物理假设：

- 建议写清变量的现实意义、物理量纲/单位、采样或计算方式，以及关键的数据特征（如是否已去均值、是否存在噪声）。
- 字符串类型的分组/类别变量建议直接保留原始字符串，除非你有特殊需求，否则无需提前做 One-Hot 编码（符号引擎原生支持按类别分组拟合参数 `grouped_param`）。
- 再次提醒：请使中立、客观的观测描述（如“观测到的响应变量”），切勿直接把待发现的目标方程写进描述里。

## 7. 完整配置示例

### 示例一：常规表格/时间序列数据

```json
{
  "variables": {
    "population": {
      "file": "population.npy",
      "description": "Annual population count.",
      "axes": ["year"]
    },
    "gdp": {
      "file": "gdp.npy",
      "description": "Annual gross domestic product in constant currency.",
      "axes": ["year"]
    }
  },
  "axes": {
    "year": {
      "values": [2018, 2019, 2020, 2021, 2022],
      "description": "Calendar year."
    }
  }
}
```

### 示例二：复杂网络动力学数据

```json
{
  "num_nodes": 10,
  "variables": {
    "theta": {
      "file": "theta.npy",
      "description": "Oscillator phase in radians.",
      "axes": ["time", "node"]
    },
    "A": {
      "file": "A.npy",
      "description": "Directed interaction endpoints.",
      "axes": ["edge", "endpoint"],
      "kind": "relation"
    }
  },
  "axes": {
    "time": {"file": "time.npy", "description": "Time in seconds."},
    "node": {"values": ["node1", "node2", "node3", "node4", "node5", "node6", "node7", "node8", "node9", "node10"], "description": "Node label."},
    "edge": {"size": 32, "description": "Directed edge position."},
    "endpoint": {"values": ["target", "source"], "description": "Endpoint column order."}
  }
}
```

## 8. 在 Python 中校验与加载数据

你可以使用 `sr_harness.core` 提供的两个辅助函数来检查或加载 `context.data/`：

```python
from sr_harness.core import inspect_context_data, load_context_data

report = inspect_context_data("workspace/context.data")
if report["errors"]:
    print("invalid:", report["errors"])
else:
    loaded = load_context_data("workspace/context.data")
    print(loaded["data"].keys())
    print(loaded["variable_axes"])
    print(loaded["relation_names"], loaded["num_nodes"])
```

- **`inspect_context_data()`**：不会抛出异常，而是返回包含 `errors` 和 `warnings` 的诊断字典，非常适合在数据整理脚本中做自检；
- **`load_context_data()`**：在校验通过后返回可直接载入 `AgentContext` 的数组字典与元数据；若数据不合法则抛出 `ContextManifestError`。

在网页工作台中，数据准备 Agent 每次修改完 `context.data/` 后，都会调用 `validate_context_data` 工具完成上述校验。
