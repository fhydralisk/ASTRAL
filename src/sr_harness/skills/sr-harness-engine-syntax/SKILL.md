---
name: sr-harness-engine-syntax
description: Use this skill before writing, evaluating, or submitting ordinary SRHarness Engine formulas, especially formulas with fitted parameters, categorical grouped parameters, nonlinear functions, broadcasting, or delays.
---

# Write SRHarness Engine Formulas

Whenever a candidate model can be expressed as a mathematical formula, write it in **SRHarness Engine** syntax and evaluate it with `evaluate_formula` or `submit_formula` rather than `evaluate_code`. Engine formulas support automatic parameter optimization, residual diagnostics, symbolic complexity tracking, and Pareto-front ranking.

**Important**: Pass only the **right-hand side (RHS)** expression to `evaluate_formula` or `submit_formula`. For example, to test $y = a x + b$, pass `f="param('a') * x + param('b')"` (and pass `y` via the separate `y` argument only when testing an equality for a variable other than the default target).

## 1. Operators and Built-in Functions

Supported arithmetic operators (following standard Python precedence and NumPy broadcasting):

```text
+   -   *   /   **
```

Always use `**` for exponentiation. Numeric literals written directly in an expression (such as `2.0` in `2.0 * sin(x1)`) are treated as fixed constants and are **not** modified during parameter fitting:

```text
x1 + x2
2.0 * sin(x1)
x1**2 + exp(-x2)
max(x1, x2) / (1 + abs(x3))
```

Supported single-argument elementwise functions:

```text
abs     arccos  arcsin  arctan  cos     cosh    cot     csc     exp     inv
log     log10   log2    pow2    pow3    sec     sech    sigmoid sign    sin
sinh    sqrt    tan     tanh
```

- **Logarithms and inverse trig aliases**: `log(x)` (or `ln(x)`) is the natural logarithm; `log10(x)` (or `lg(x)`) is base-10; `log2(x)` is base-2. `asin`, `acos`, and `atan` are accepted as aliases for `arcsin`, `arccos`, and `arctan`. Prefer the canonical names listed above.
- **Two-argument functions**: `min(a, b)` and `max(a, b)` take exactly two arguments.
- **Bare function names only**: Always write `sin(x)` or `exp(x)`—never `np.sin(x)` or `math.exp(x)`.

## 2. Fitted Parameters (`param` and `grouped_param`)

### Scalar Parameters (`param`)

Every free constant that should be optimized against the training data must be declared explicitly with `param('name')`:

```text
param('a') * x + param('b')
param('alpha', value=0.3) * x / (1 - param('alpha'))
```

- **Never use undeclared variable names for coefficients**: Writing `a * x` tells the parser to look for a dataset column named `a` in `context.data`. Always write `param('a') * x` for fitted constants.
- **Shared parameters**: Using `param('alpha')` multiple times in the same formula binds all occurrences to a **single shared parameter** (do not pass conflicting initial `value` arguments to the same parameter name).
- **Enabling optimization**: Pass `fit=true` when calling `evaluate_formula` so unbound parameters are optimized on the training split.

### Category-Grouped Parameters (`grouped_param`)

When your dataset includes a categorical variable (such as `category` or `label`) and a coefficient should take a separate fitted value for each group while sharing the rest of the formula structure, use `grouped_param`:

```text
grouped_param(category) * x
grouped_param(category, name='slope', default=0.0) * x
grouped_param(category, name='slope', value={'A': 1.0, 'B': 2.0}) * x
```

Do not manually one-hot encode categorical columns just to fit per-group constants—`grouped_param` handles per-category fitting directly.

## 3. Graph and Hypergraph Expressions

If your dataset involves networks, adjacency matrices, node/edge interactions, symbolic indices (`[i, j]`), neighbor reductions, or `gather`, read the companion skill `sr-harness-engine-graph-syntax` via `read_skill` before writing formulas.

## 4. Time Delays (`delay`)

To reference the value of a time-dependent expression at an earlier time $t - \delta$, use `delay(value, delta)`:

```text
x + delay(x, delta)
```

By default, the evaluator linearly interpolates along the first axis (time) and returns `NaN` where $t - \delta$ falls before the start of the observed trajectory. Custom ODE/DDE evaluators can also plug in their own history interpolation logic.

## 5. Disallowed Python Syntax

SRHarness Engine uses a restricted mathematical AST parser and never executes arbitrary Python. The following constructs are rejected:

```text
y = x + 1                 # Invalid: assignment statement (pass only the RHS)
np.sin(x)                 # Invalid: module/attribute access
custom_function(x)        # Invalid: unregistered function name
lambda x: x               # Invalid: lambda expression
__import__('os')          # Invalid: arbitrary Python call
```

## Pre-Submission Checklist

Before calling `evaluate_formula` or `submit_formula`:

1. Verify that every bare variable name exists in `context.data`, and wrap all trainable constants in `param(...)` or `grouped_param(...)`.
2. Set `fit=true` whenever the expression contains `param` or `grouped_param` nodes.
3. Check that denominators, `log` arguments, `sqrt` arguments, and `delay` shifts stay within valid numerical domains across your dataset.
4. Review train/validation metrics and residual diagnostics to confirm the formula generalizes cleanly.
