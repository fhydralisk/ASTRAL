# Structured Data and `context.data`

SRHarness stores prepared datasets in a `context.data/` directory inside the workspace. Each variable (and any long coordinate axis) is saved as a `.npy` array file, while `manifest.json` records variable names, descriptions, axis dimensions, and graph or hypergraph topology.

Throughout this guide, rules fall into three categories:

- **Hard constraints**: Strictly enforced by the loader—violating them causes loading to fail;
- **Semantic conventions**: Define how users and Agents interpret the data (such as column ordering in an edge list) even when not fully verifiable by type checks alone;
- **Best practices**: Improve data clarity and experimental rigor without blocking data loading.

!!! warning "Experimental Design Tip: Never Leak the Ground-Truth Formula"
    Write `description` fields to explain physical meaning, units, or measurement procedures—**never include the target equation to be discovered or give away its functional form** (e.g., avoid descriptions like `"target generated from y = 1 + x**2"` or `"exponential-decay term"`). The loader can only check that `description` is a non-empty string, not whether its wording leaks the answer.

## 1. Directory Layout

```text
context.data/
├── manifest.json  # Manifest declaring variables, axes, and graph relations
├── x.npy          # Variable array
├── y.npy          # Variable array
├── time.npy       # Long coordinate axes can also be stored as .npy files
└── A.npy          # Graph or hypergraph edge lists are stored as variables too
```

- **Hard constraint**: A valid `manifest.json` must exist at the root of `context.data/`, and every referenced `.npy` file must live directly in `context.data/` (no subdirectory paths).
- **Hard constraint**: Every `.npy` file must store a `numpy.ndarray` loadable with `allow_pickle=False`. Python `object` dtypes are rejected; use NumPy Unicode or fixed-width string dtypes for categorical text.
- **Best practice**: Unreferenced `*.npy` files in `context.data/` trigger warnings rather than errors so temporary scratch files do not break work in progress, but you should clean them up or register them before starting a run.

## 2. Root Fields in `manifest.json`

The root JSON object accepts only the three fields below (unknown keys, missing required fields, or duplicate keys will fail validation):

| Field | Requirement | Description |
|---|---|---|
| `variables` | **Required** | Non-empty object mapping each variable name to its specification (including relation variables). |
| `axes` | **Required** | Object mapping each axis name referenced by variables to its specification (may be `{}` if all variables are scalars). |
| `num_nodes` | **Conditionally required** | Must be a positive integer whenever any variable has `kind: "relation"`, and must be omitted otherwise. |

Note: Choosing the target variable, selecting input features, writing the research question, and picking an Evaluator are **task settings** rather than dataset properties, so they are configured in the task setup rather than stored in `manifest.json`.

## 3. Variables (`variables`)

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

- **Required and optional keys**: Every variable entry must specify `file`, `description`, and `axes`. The only optional keys allowed are `kind` and `structure`.
- **Naming rules**: Variable names must be non-empty, cannot be `.` or `..`, and cannot contain path separators or NUL characters. The array file must be named `<variable_name>.npy`.
- **Axis alignment**: `axes` is a list of axis names. Its length must match the array's number of dimensions (`ndim`), and each array dimension must match the length of the corresponding axis (scalar variables use `[]`).
- **Disjoint names**: Once loaded into `AgentContext`, variables and axes share the `context.data` namespace, so variable names and axis names must not overlap.

## 4. Coordinate Axes (`axes`)

Every axis entry must provide a `description` and specify its values or length using **exactly one** of `values`, `file`, or `size`:

```json
{
  "axes": {
    "time": {"values": [0.0, 0.1, 0.2], "description": "Time in seconds."},
    "node": {"values": ["node1", "node2", "node3"], "description": "Node label."},
    "sample": {"size": 100, "description": "Zero-based sample position."}
  }
}
```

- **`values` (inline array)**: A non-empty 1D JSON array of numbers or strings—ideal for short axes or named node/category labels.
- **`file` (external NPY)**: Must be named `<axis_name>.npy` and store a 1D array—recommended for long axes such as timestamps.
- **`size` (length only)**: A positive integer that generates `0, 1, ..., size - 1`—convenient for generic sample or edge indices.
- **Referential integrity**: Every declared axis must be referenced by at least one variable, and every axis listed in a variable's `axes` must be declared in `axes`.

## 5. Graph and Hypergraph Relations (`relation` and `structure`)

For network dynamics or relational data, edge and hyperedge tables are registered as variables:

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

- **Explicit `kind: "relation"`**: Relation variables must explicitly set `"kind": "relation"` (SRHarness never guesses whether a variable is a graph from its name).
- **Shape and node bounds**: Relation arrays must use an integer dtype, have shape `(E, 2)` for directed graphs or `(H, 3)` for ternary directed hypergraphs, and contain node indices strictly within `[0, num_nodes)`.
- **Endpoint column order (semantic convention)**: Columns in `(E, 2)` are ordered `(target, source)`; columns in `(H, 3)` are ordered `(target, source1, source2)`. We recommend listing these labels explicitly in the endpoint axis `values`.
- **Edge-aligned variables (`structure`)**: Any variable whose last dimension indexes the `E` edges or `H` hyperedges of a relation (such as time-varying edge weights `weight`) must set `"structure": "<relation_name>"` with a matching length.
- **Node variables**: Ordinary node-level variables omit `structure`. All relations in a manifest share the root `num_nodes` count.

## 6. Writing Effective Descriptions

Every variable and axis requires a non-empty string `description`:

- State the scientific meaning, physical units, measurement or derivation method, and any important data characteristics.
- Keep categorical variables as plain strings rather than one-hot encoding them unless specifically needed—SRHarness Engine natively supports category-specific parameters via `grouped_param`.
- Use neutral, domain-appropriate wording (e.g., `"observed response variable"`) and avoid hinting at the ground-truth symbolic formula.

## 7. Complete Examples

### Tabular / Time-Series Data

```json
{
  "variables": {
    "population": {"file": "population.npy", "description": "Annual population count.", "axes": ["year"]},
    "gdp": {"file": "gdp.npy", "description": "Annual gross domestic product in constant currency.", "axes": ["year"]}
  },
  "axes": {
    "year": {"values": [2018, 2019, 2020, 2021, 2022], "description": "Calendar year."}
  }
}
```

### Network Dynamics Data

```json
{
  "num_nodes": 10,
  "variables": {
    "theta": {"file": "theta.npy", "description": "Oscillator phase in radians.", "axes": ["time", "node"]},
    "A": {"file": "A.npy", "description": "Directed interaction endpoints.", "axes": ["edge", "endpoint"], "kind": "relation"}
  },
  "axes": {
    "time": {"file": "time.npy", "description": "Time in seconds."},
    "node": {"values": ["node1", "node2", "node3", "node4", "node5", "node6", "node7", "node8", "node9", "node10"], "description": "Node label."},
    "edge": {"size": 32, "description": "Directed edge position."},
    "endpoint": {"values": ["target", "source"], "description": "Endpoint column order."}
  }
}
```

## 8. Validating and Loading Data in Python

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

- **`inspect_context_data()`** returns a dictionary of `errors` and `warnings` without raising exceptions, making it ideal for self-checks during data preparation.
- **`load_context_data()`** raises `ContextManifestError` if validation fails, or returns a dictionary of arrays and metadata ready for `AgentContext`.

In the WebUI, the Data Preparation Agent calls the `validate_context_data` tool after updating `context.data/` to verify that the dataset is ready for symbolic regression.
