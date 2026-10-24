---
name: sr-harness-engine-graph-syntax
description: Use this skill before writing, evaluating, or submitting SRHarness Engine formulas for graphs, networks, hypergraphs, node interactions, relation reductions, edge or hyperedge fields, gather operations, or message passing.
---

# Write Graph and Hypergraph Formulas

Read `sr-harness-engine-syntax` first for standard arithmetic, elementary functions, `param(...)` declarations, and parser safety rules. This guide covers the **indexed structural syntax** used for complex networks, graphs, and hypergraphs.

Whenever possible, express network dynamics in SRHarness Engine syntax rather than `evaluate_code` so parameters can be fitted automatically and formulas appear in the Top-k and Pareto-front leaderboards.

## 1. Symbolic Indices and Array Shapes

Any expression that uses symbolic subscripts—such as `x[i]`, `A[i, j]`, or `T[i, j, k]`—treats the **last array dimension** as the structural (node/edge/hyperedge) dimension, while all leading dimensions (such as time or sample index) broadcast elementwise.

- **Symbolic identifiers only**: Subscripts must be symbolic index names like `i`, `j`, `k`. Integer indexing (`x[0]`) and slicing (`x[0:10]`) are not allowed.
- **Explicit node count**: Graph datasets must define `num_nodes = N` in `context.data` so isolated nodes with no edges are still preserved in output arrays.
- **Standard array shapes**:

```text
Node variable:      (..., N)
Edge variable:      (..., E)
Hyperedge variable: (..., H)
Scalar / global:    (..., 1)
Binary graph (A):   (E, 2)   with columns (target, source)
Ternary hypergraph: (H, 3)   with columns (target, source1, source2)
```

- **Index every structural variable**: Once an expression uses symbolic indices, every variable whose last dimension has size `N`, `E`, or `H` must carry an index. For example, when `x` has shape `(..., N)`, writing `x + x[i]` is invalid—write `x[i] + x[i]`. (Variables with a trailing singleton dimension `(..., 1)` or 1D sample-only variables can remain unindexed and broadcast automatically.)
- **Free indices determine output shape**: Any index that is *not* summed over by `sum[...]` remains as a trailing axis in first-appearance order:

```text
x[i]                   -> shape (..., N)
x[i] + x[j]            -> shape (..., N, N)
x[i] * x[j] * x[k]     -> shape (..., N, N, N)
```

Avoid materializing dense `N × N` or `N × N × N` intermediate arrays when a sparse relation reduction `sum[j](A[i, j], ...)` or `gather(A[i, j], ...)` can compute only the connected pairs.

## 2. Neighbor Reductions with `sum[...]`

In `context.data`, binary relation tables `A` of shape `(E, 2)` store directed edges in **`(target, source)`** column order, and ternary hypergraph tables `T` of shape `(H, 3)` store **`(target, source1, source2)`**.

Therefore, writing:

```text
A[i, j]
```

binds `i` to the **target** node (column 0) and `j` to the **source** neighbor (column 1).

### Sparse Relation-Restricted Sums (Recommended)

Use the two-argument `sum[index](relation, message)` form to sum incoming messages over connected edges only:

```text
sum[j](A[i, j], x[j] - x[i])
sum[j, k](T[i, j, k], x[i] * x[j] * x[k])
```

Mathematically, `sum[j](A[i, j], expr)` is equivalent to $\sum_{j} A_{ij} \cdot \text{expr}$, but the two-argument form evaluates `expr` **only along existing edges**, avoiding dense $O(N^2)$ or $O(N^3)$ memory blow-ups.

### Edge-Aligned and Hyperedge-Aligned Variables

If your dataset includes a variable defined on edges (shape `(..., E)`, such as edge weights `w`) or hyperedges (shape `(..., H)`), index it with the same indices as its relation:

```text
sum[j](A[i, j], w[i, j] * sin(theta[j] - theta[i]))
```

### Algebra on Multiple Relations and Scoping Rules

You can combine multiple relation tables algebraically inside the first argument of `sum`:

```text
sum[j](A1[i, j] + A2[i, j], x[j])
sum[j](A1[i, j] * A2[i, j], x[j])
sum[j](A1[i, j] + 0.5 * A2[i, j], x[j])
```

**Never reuse a bound index name inside a nested scope**:

```text
sum[j](A[i, j], sum[j](x[j]))    # Invalid: index j is already bound!
sum[j](A[i, j], sum[k](x[k]))    # Valid: inner sum uses a distinct index k
```

## 3. Common Network Dynamics Examples

- **Coupled Kuramoto oscillators**:

```text
omega[i] + param('K') * sum[j](A[i, j], sin(theta[j] - theta[i]))
```

- **In-degree normalized coupling**:

```text
omega[i] + param('K') * sum[j](A[i, j], sin(theta[j] - theta[i])) / sum[j](A[i, j], 1)
```

- **Combined node self-dynamics, weighted pairwise edges, and ternary hyperedges**:

```text
(param('a') * x[i]
 + param('b') * sum[j](A[i, j], w[i, j] * tanh(x[j] - x[i]))
 + param('c') * sum[j, k](T[i, j, k], x[j] * x[k]))
```

*(Tip: When dividing by node degree `sum[j](A[i, j], 1)`, check whether any node has zero in-degree so you don't divide by zero.)*

## 4. Edge-Level Evaluation with `gather`

When the target variable itself is defined on edges `(..., E)` or hyperedges `(..., H)`—or when you need an intermediate edge-level quantity without summing over neighbors—use `gather(relation, expression)`:

```text
gather(A[i, j], x[i] + x[j])            -> shape (..., E)
gather(T[i, j, k], x[i] * x[j] * x[k])  -> shape (..., H)
```

The output of `gather(...)` behaves just like an edge or hyperedge variable:

```text
2 * gather(A[i, j], x[i] + x[j])
sin(gather(A[i, j], x[i] + x[j]))
gather(A[i, j], x[i] + x[j]) + w
```

Summary of when to use each construct:

- Use **`sum[j](A[i, j], ...)`** when the output should be aligned with **nodes** `(..., N)`.
- Use **`gather(A[i, j], ...)`** when the output should be aligned with **edges** `(..., E)` or **hyperedges** `(..., H)`.

## 5. Shorthand Syntax: `aggr`, `targ`, and `sour`

For standard pairwise graph message passing, the parser also accepts `aggr`, `targ` (target node $i$), and `sour` (source neighbor $j$):

```text
aggr(A * targ(x) * sour(x))
aggr(A, targ(x) * sour(x))
aggr(A, targ(A, x) * sour(A, x))
```

All three forms automatically desugar to the canonical indexed reduction:

```text
sum[j](A[i, j], x[i] * x[j])
```

`targ(...)` and `sour(...)` are valid only inside `aggr(...)`. For hypergraphs, multi-relation expressions, or custom index combinations, always write explicit `sum[j](A[i, j], ...)` syntax.

## Pre-Submission Checklist for Graph Formulas

1. Check that `context.data` declares `num_nodes` and marks relation variables with `kind: "relation"`.
2. Remember that relation columns are ordered `(target, source)`—so in `A[i, j]`, `i` is the receiving node and `j` is the sending neighbor.
3. Attach symbolic indices (`[i]`, `[i, j]`, etc.) to every node, edge, or hyperedge variable in the formula, and keep index names distinct in nested reductions.
4. Use two-argument `sum[j](A[i, j], ...)` instead of dense unguarded sums whenever aggregating over a graph or hypergraph.
