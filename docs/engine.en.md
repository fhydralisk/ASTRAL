# SRHarness Engine

`sr_harness_engine` is the symbolic expression layer of SRHarness. It safely parses mathematical strings into expression trees and provides canonical rendering, NumPy evaluation, parameter optimization, constant folding, and expressive syntax for **graphs**, **hypergraphs**, and **time delays**.

The Engine focuses purely on mathematical expressions and their numerical evaluation; dataset splitting, candidate ranking, and task-specific metrics (such as ODE trajectory rollouts) live in [Evaluators](evaluator.md) and the SRHarness runtime.

## 1. Quick Start

Parse a parameterized formula, fit its constants to data, and evaluate predictions in a few lines of Python:

```python
import numpy as np
import sr_harness_engine as engine

x = np.linspace(-2.0, 2.0, 101)
target = 2.5 * np.sin(x) - 0.4
model = engine.parse("param('a') * sin(x) + param('b')")
fit = model.fit({"x": x}, target)

print(fit.expression)          # expression with fitted parameter values bound
print(fit.parameters)          # {'a': ..., 'b': ...}
print(fit.loss)
print(fit.evaluate({"x": x})[:3])
```

Safety boundary: `engine.parse()` validates an allowlist of Python AST nodes—it **does not call `eval()`** or execute arbitrary Python code.

## 2. Basic Syntax

### Numbers, Variables, and Operators

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

Supported operators are `+`, `-`, `*`, `/`, `**` (exponentiation), and unary minus `-`.

!!! tip "Use `**` for Exponentiation"
    In Python, `^` is bitwise XOR rather than exponentiation. While higher-level formula tools automatically normalize `^` to `**` when parsing model output, always use `**` when calling `engine.parse()` directly.

### Built-in Mathematical Functions

Built-in elementwise functions:

```text
sin cos tan sinh cosh tanh
arcsin arccos arctan
exp log log10 log2 sqrt abs
sigmoid sign sec sech csc cot inv
```

Common aliases are normalized automatically so equivalent formulas do not create duplicate candidates:

- Natural logarithm: `log(x)` and `ln(x)` (canonicalized to `log`);
- Base-10 logarithm: `log10(x)` and `lg(x)` (canonicalized to `log10`);
- Base-2 logarithm: `log2(x)`;
- Inverse trigonometric functions: `arcsin`/`asin`, `arccos`/`acos`, and `arctan`/`atan` (canonicalized to `arcsin`, `arccos`, `arctan`).

You can also build expressions programmatically in Python:

```python
x = engine.Symbol("x")
expression = engine.exp(-x) * engine.sin(2 * x)
```

## 3. Fitted Parameters

### Named Scalar Parameters (`param`)

Declare free constants to be optimized with `param('name')`:

```text
param('slope') * x + param('bias')
param('a', value=0.3) * x
```

- Repeated occurrences of `param('a')` with the same name refer to **the same shared parameter**;
- `value` serves both as the default value before fitting and as the initial guess during optimization;
- You can also supply initial guesses via the `initial` dictionary in `engine.fit()`:

```python
fit = engine.fit(
    engine.parse("param('a') * x + param('b')"),
    {"x": x},
    target,
    initial={"a": 1.0, "b": 0.0},
)
```

### Category-Grouped Parameters (`grouped_param`)

When a dataset includes a categorical variable (such as `label` indicating different experimental groups or materials) where each group follows the same formula structure with its own constant, use `grouped_param`:

```text
grouped_param(label, name='rate') * x
```

Each unique category receives its own fitted parameter value. You can also provide initial per-category values and a fallback default:

```text
grouped_param(
    label,
    name='rate',
    value={'A': 1.0, 'B': 2.0},
    default=0.0,
) * x
```

## 4. Parsing, Rendering, and Safety Boundaries

Expressions render cleanly to canonical strings or LaTeX and round-trip losslessly through `engine.parse()`:

```python
expression = engine.parse("x ** (4 / 3) + sqrt(2)")
text = engine.render(expression)
latex = engine.render(expression, latex=True)
assert str(engine.parse(str(expression))) == str(expression)
```

To prevent code injection, the parser rejects attribute access (`.`), slicing (`[a:b]`), comprehensions, lambdas, arbitrary function calls, and non-literal keyword arguments (for example, `np.sin(x)`, `__import__('os')`, `x[0:10]`, and `custom_python_function(x)` are all rejected).

## 5. Numerical Evaluation

```python
expression = engine.parse("sin(x) + y ** 2")
value = expression.evaluate({"x": x, "y": y})
```

Input arrays follow standard NumPy broadcasting rules. Unbound parameter values can also be passed at evaluation time via `parameters`:

```python
expression.evaluate({"x": x}, parameters={"a": 2.0, "b": -0.5})
```

(The module-level helper `engine.evaluate(expression, values)` is equivalent.)

## 6. Expression Trees and Traversal

Every AST node inherits from `Expression`:

| Node Class | Meaning |
|---|---|
| `Number` | Numeric constant |
| `Symbol` / `Variable` | Dataset variable |
| `Parameter` | Named scalar parameter (`param`) |
| `GroupedParameter` | Category-grouped parameter (`grouped_param`) |
| `Unary` / `Binary` | Unary or binary arithmetic operation |
| `Function` | Built-in mathematical function call |
| `Indexed` | Variable with free indices (e.g., `x[i]`, `A[i, j]`) |
| `Reduction` | Index reduction (e.g., `sum[j](...)`) |
| `Gather` / `Aggregate` / `RelationLift` | Graph and hypergraph operations |

Tree traversal and transformation helpers:

```python
for node in expression.iter_preorder():
    print(type(node).__name__, node)

copy = expression.copy()
simplified = expression.fold_constants()
parameter_count = expression.count_parameters()
```

`operands` returns direct child nodes, and `replace(old, new)` returns a new tree with identity-based node replacement.

## 7. Graph and Hypergraph Index Syntax

Relation arrays use **target-first** column ordering:

- **Directed graph `A.shape == (E, 2)`**: Each row is `(target, source)`;
- **Ternary directed hypergraph `T.shape == (H, 3)`**: Each row is `(target, source1, source2)`.

### Neighbor Message Aggregation (`sum`)

To sum messages from source neighbors `j` into target node `i`:

```text
sum[j](A[i, j], x[i] * x[j])
```

Here `A[i, j]` binds column 0 to target index `i` and column 1 to source index `j`, while `sum[j]` reduces over `j` and aggregates results by `i`. Pass `num_nodes` during evaluation so isolated nodes with no incoming edges are preserved in the `(..., N)` output:

```python
prediction = expression.evaluate(data, num_nodes=10)
```

Shape convention: node variables have shape `(..., N)`, edge fields `(..., E)`, and hyperedge fields `(..., H)`. Leading sample/time dimensions broadcast under NumPy rules, while the final dimension is structural.

Hypergraph aggregation uses the exact same notation by reducing over both source indices `j, k`:

```text
sum[j, k](T[i, j, k], x[i] * x[j] * x[k])
```

### Edge-Level `gather` and Relation Fields

Use `gather` to evaluate an expression on each edge or hyperedge without summing (returning shape `(..., E)` or `(..., H)`):

```text
gather(A[i, j], x[i] + x[j])
gather(T[i, j, k], x[i] * x[j] * x[k])
```

Edge-aligned variables `w` of shape `(E,)` or `(..., E)` can also participate directly in indexed sums:

```text
sum[j](A[i, j], w[i, j] * x[i] * x[j])
```

(When multiple relations exist in the same context, `RelationField(w, relation="A")` explicitly binds `w` to relation `A`.)

### Shorthand Syntax (`aggr` / `targ` / `sour`)

```text
aggr(A * targ(x) * sour(x))
aggr(A, targ(x) * sour(x))
```

Both shorthands desugar automatically into the canonical indexed form `sum[j](A[i, j], x[i] * x[j])`.

## 8. Time Delays (`delay`)

For delay differential equations (DDEs) or systems with memory, `delay(x, delta)` evaluates $x(t - \delta)$:

```text
x + delay(x, delta)
```

By default, the evaluator interpolates linearly along axis 0 and returns `NaN` for times prior to the start of the trajectory:

```python
prediction = engine.parse("delay(x, delta)").evaluate(
    {"x": trajectory, "delta": lag},
    time=sample_times,
)
```

Custom ODE/DDE Evaluators can pass a custom `delay_resolver` to plug in their own history buffer or interpolation scheme.

## 9. Constant Folding and Complexity

```python
assert str(engine.parse("(2 + 3) * x")) == "5 * x"
```

Constant folding simplifies constant subexpressions while keeping fractions, powers, and named functions readable. `count_parameters()` counts free parameters, and `len(expression)` counts AST nodes (used by `DefaultEvaluator` as the default `complexity` metric).

## 10. Integration with Evaluators

`DefaultEvaluator` connects the Engine to the rest of SRHarness through five methods:

```python
split(context)
fit(f, y, context)
evaluate(f, y, context)
fit_candidate(f, context)
evaluate_candidate(f, context)
```

General equalities use `fit/evaluate`, whereas formal target candidates use `fit_candidate/evaluate_candidate`. Combined with `sr_harness.evaluator.utils`, this makes it straightforward to add ODE integration or domain-specific metrics. See [Formula Evaluation and Custom Evaluators](evaluator.md) and the [API Reference](https://yuzhthu.github.io/SRHarness/reference/).

## 11. Behavior Test Suite

Runnable examples covering basic expressions, parameters, graph/hypergraph relations, gather, delays, constant folding, and custom Evaluators live in `tests/behavior/`:

```bash
pytest tests/behavior
```

See the [API Reference](https://yuzhthu.github.io/SRHarness/reference/) for every public class and function.
