---
name: discover-symbolic-laws
description: Use this skill when solving a symbolic-regression problem from tabular numerical data, especially when direct formula guesses fail, predictive accuracy has not yielded a compact law, or numerical evidence is needed to choose transformations and discovery tools.
---

# Discover Symbolic Laws from Tabular Data

Approach symbolic regression as a step-by-step scientific investigation rather than blind trial-and-error. Each tool call should answer a specific question about the data's structure, and you should always distinguish between a temporary **diagnostic probe** (such as a spline or high-degree polynomial that merely shows a relationship exists) and a **compact, interpretable symbolic law**.

## Core Working Principles

- **Summarize, never dump raw arrays**: Run calculations across all samples inside tools or scripts, but print only concise summary statistics—shapes, domain flags, quantiles, fitted coefficients, and top candidate metrics.
- **Inspect only the most informative rows**: When checking specific data points, print at most 5–10 rows chosen by a clear criterion (e.g., largest residual or smallest denominator).
- **Keep candidate lists focused**: Limit printed candidate tables to the top 5–10 formulas, and always record your best simple formula before exploring complex branches.
- **Ensure reproducibility**: Use fixed random seeds and single-threaded BLAS settings whenever running custom numerical scripts.

## Step-by-Step Discovery Workflow

### Step 1: Check Variable Distributions and Domains

Before proposing any formula, check each variable's sign, proximity to zero, quantiles, mean, standard deviation, and overall dynamic range. This tells you which transformations (such as `log`, `sqrt`, or `1/x`) are mathematically valid and whether absolute, relative, or log-scale error is most appropriate.

Start with:

```text
statistics_analysis(n_bins=10, near_zero_threshold=1e-8)
```

You can also pass candidate transformations directly to inspect their distributions:

```text
statistics_analysis(variables=["y*x2", "log(y)"])
```

- **Logarithm rules**: Only apply `log` when values are strictly positive. If a variable crosses zero, use `sign(z)*log1p(abs(z))`, separate its sign and magnitude, or apply a physically justified shift. In SRHarness Engine syntax, `log` (or `ln`) is the natural logarithm; use `log10` (or `lg`) for base 10 and `log2` for base 2.
- **Fallback script** (only if `statistics_analysis` is disabled and `code_executor` is available):

```python
import numpy as np

# `data` is the dictionary of variable arrays provided by the runtime.
for name, a in data.items():
    a = np.asarray(a, float).ravel()
    finite = np.isfinite(a)
    z = a[finite]
    q = np.quantile(z, [0, 0.01, 0.25, 0.5, 0.75, 0.99, 1])
    print(
        name,
        "n", len(a),
        "finite", round(finite.mean(), 4),
        "negative", round(np.mean(z < 0), 4),
        "near_zero", round(np.mean(np.abs(z) <= 1e-8), 4),
        "quantiles", np.round(q, 6).tolist(),
        "mean", float(np.mean(z)),
        "std", float(np.std(z)),
    )
```

### Step 2: Analyze Variable Relationships and Dimensional Collapse

Test how well individual features—or composite coordinates like ratios and products—explain the target `y`:

```text
relationship_analysis(
  variables=["x1", "x2", "x1/x2"], y="y", n_bins=5,
  n_folds=5, collapse_model="bins"
)
```

- Compare Pearson/Spearman correlations, binned conditional means, and 5-fold cross-validated collapse scores across candidate coordinates.
- Enable `pairwise=true` only when you specifically need to check collinearity or interactions between input features (since pairwise output grows quadratically with feature count).
- If a coordinate achieves a high in-sample score but a poor held-out score, it is overfitting. You can switch `collapse_model` to `"spline"` (to test smooth non-monotone curves) or `"isotonic"` (to test monotone relationships).
- **Important**: Near-zero Pearson and Spearman correlations do *not* mean a variable is irrelevant! Symmetric (e.g., $y = x_1^2$), periodic, or interaction-driven relationships often have zero linear/rank correlation. Always check combinations such as `x1 + x2`, `x1 - x2`, `x1 * x2`, and `x1 / x2` before dropping a variable.

### Step 3: Identify the Likely Functional Family

Match the empirical behavior of the data to simple mathematical families before launching broad symbolic searches:

- **Additive or low-degree polynomial**: Smooth trends without asymptotes or blow-ups.
- **Multiplicative power law**: Variables span several orders of magnitude with a roughly constant log-log slope.
- **Rational, saturating, or singular form**: Values blow up near zero/poles (suggesting inverse powers or denominators) or level off toward an asymptote (suggesting rational or exponential saturation).
- **Exponential or logarithmic**: Rapid growth/decay where `log(y)` becomes linear in `x`, or slow growth where `y` is linear in `log(x)`. Near zero, prefer numerically stable forms like `expm1(z)` over `exp(z) - 1`.
- **Periodic or angular**: Repeated zero crossings or oscillations (suggesting `sin`/`cos` of differences or phases).

### Step 4: Test Invariants and Reduce Dimensionality

Look for combinations of variables that cancel out part of the target's variation or collapse a multi-variable problem into fewer dimensions:

```text
y * g(xi),  y / g(xi),  log(abs(y)) - log(abs(g(xi)))
y * product(xi ** pi),  residual / g(xi),  residual * g(xi)
```

You can test several candidate invariants in a single call:

```text
statistics_analysis(variables=["y*x1", "y*x1/x2", "y*x2/x1"])
relationship_analysis(variables=["x1/(x3*x4)"], y="y*x2")
```

When checking whether a combination is truly constant, verify that its variance, interquartile range, and min/max spread are small across all finite samples—a stable mean alone is not enough.

### Step 5: Fit Candidate Functional Forms

Use targeted fitting tools that match your structural hypothesis:

- **Power laws**: Call `power_law_fit(x=["x1", "x2"], y="y")`. Once raw exponents look stable, test integer/simple-fraction snapping with `power_law_fit(..., snap_exponents=true, snap_tolerance=0.03)` and accept the snapped form only if `snap_accepted=true`.
- **Rational functions** (when poles or saturation are present):

```text
rational_fit(
  x=["x1"], y="y",
  numerator_degrees=[0, 1, 2], denominator_degrees=[0, 1, 2],
  validation_fraction=0.2, top_k=5
)
```

  Reject high-degree rational fits if they barely improve validation error, have ill-conditioned coefficients, or introduce near-zero denominators.
- **Polynomial and sparse linear libraries**: Use `polynomial_fit` or `call_sindy` for additive combinations of basis terms. For strictly positive variables, you can also test sparse log-space combinations:
  `call_sindy(y="log(y)", x=["log(x1)", "log(x2)", "log(x3)"], poly_degree=1, include_trig=false, threshold=0.01)`.
- **Evolutionary search (`call_pysr`)**: Invoke PySR only *after* you have narrowed down the relevant variables, operators, and target transformations.

### Step 6: Inspect Residuals to Find Missing Terms

For every promising candidate formula, run:

```text
evaluate_formula(f="candidate_expression", show_diagnostics=true)
```

Examine the residual quantiles, worst-error rows, and correlations between the residuals and input variables:

- **Recursive residual discovery**: If a clear pattern remains in the residuals, treat the residual (`y - f_dominant` or `y / f_dominant`) as a new target and discover its structure step by step.
- **Symmetry checks**: Check whether swapping two similarly distributed variables (`xi` and `xj`) leaves the formula unchanged or flips its sign—this strongly points to natural coordinates like `xi + xj`, `xi - xj`, `xi * xj`, or `xi / xj`.
- **Pole vs. precision errors**: If large errors occur only near a zero or pole, check whether the discrepancy comes from a missing singular factor or simply floating-point cancellation before adding extra polynomial terms.

### Step 7: Simplify Constants and Recover Exact Form

- Snap exponents to integers or simple fractions only when validation error remains nearly unchanged.
- When a formula contains fitted floating-point constants that might represent simple rationals or mathematical constants, run `constant_fit(eq="proposed_formula", y="y")` to test clean replacements at each constant position, then re-evaluate the simplified formula with `evaluate_formula`.
- When two formulas achieve virtually identical validation error, always prefer the simpler expression.

### Step 8: Final Validation and Submission

- While rank correlations, trimmed errors, or log-space scores are great for *discovering* structure, always judge your final candidate on the task's actual evaluation metric across all valid samples.
- Verify that the formula produces finite predictions across the entire domain (including extrema and near-zero regions).
- Abandon bloated polynomial or genetic-programming branches when complexity grows without meaningful validation gains, and submit your best compact formula.

---

## Fallback Diagnostic Scripts (`code_executor`)

Use the Python recipes below **only** when the built-in analysis tools above are disabled or cannot test a specific hypothesis, and `code_executor` is enabled.

### 1. Probe 1D Curve Shape and Local Elasticity

Estimates whether `y` collapses onto a smooth 1D curve of a proposed coordinate `z`, and checks turning points and log-log elasticity ($z f'(z) / f(z)$):

```python
import numpy as np
from scipy.interpolate import UnivariateSpline

rng = np.random.default_rng(0)
z = np.asarray(data["x1"], float).ravel()
y = np.asarray(data["y"], float).ravel()
ok = np.isfinite(z) & np.isfinite(y)
z, y = z[ok], y[ok]

order = rng.permutation(len(y))
cut = int(0.8 * len(y))
tr, te = order[:cut], order[cut:]
sort = np.argsort(z[tr])
zs, ys = z[tr][sort], y[tr][sort]
zu, inv = np.unique(zs, return_inverse=True)
yu = np.bincount(inv, weights=ys) / np.bincount(inv)

spline = UnivariateSpline(
    zu, yu, k=min(3, len(zu) - 1), s=len(zu) * np.var(yu) * 1e-3, ext=3
)
pred = spline(z[te])
r2 = 1 - np.sum((y[te] - pred) ** 2) / np.sum((y[te] - np.mean(y[tr])) ** 2)

grid = np.linspace(np.quantile(z, 0.01), np.quantile(z, 0.99), 200)
curve = spline(grid)
slope = spline.derivative()(grid)
turns = np.flatnonzero(np.sign(slope[1:]) != np.sign(slope[:-1]))
pos = (grid > 0) & (np.abs(curve) > 0)
elasticity = grid[pos] * slope[pos] / curve[pos]
print(
    "heldout_r2", float(r2),
    "turning_points", np.round(grid[turns[:8]], 6).tolist(),
    "elasticity_q", np.round(np.quantile(elasticity, [0.1, 0.5, 0.9]), 4).tolist(),
)
```

*How to read the output*: A high `heldout_r2`, zero turning points, and constant elasticity near `2.0` point to $y \propto z^2$. An elasticity that grows linearly with $z$ suggests an exponential $\exp(c z)$, while an elasticity approaching a negative integer in the tail suggests a rational denominator.

### 2. Rank Nonlinear Feature Importance

Uses a fast tree ensemble with held-out permutation importance to spot variables that affect `y` nonlinearly or only through interactions:

```python
import numpy as np
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.inspection import permutation_importance
from sklearn.model_selection import train_test_split

names = [k for k in data if k != "y"]
X = np.column_stack([np.asarray(data[k], float).ravel() for k in names])
y = np.asarray(data["y"], float).ravel()
ok = np.isfinite(X).all(1) & np.isfinite(y)
X, y = X[ok], y[ok]
if len(y) > 20000:
    idx = np.random.default_rng(0).choice(len(y), 20000, replace=False)
    X, y = X[idx], y[idx]

Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=0)
model = ExtraTreesRegressor(
    n_estimators=160, min_samples_leaf=3, random_state=0, n_jobs=1
).fit(Xtr, ytr)
imp = permutation_importance(model, Xte, yte, n_repeats=3, random_state=0, n_jobs=1)
ranking = sorted(zip(imp.importances_mean, names), reverse=True)
print(
    "heldout_r2", float(model.score(Xte, yte)),
    "importance", [(n, round(float(v), 4)) for v, n in ranking[:10]],
)
```

*How to read the output*: Focus your symbolic search on the top-ranked variables first. If `heldout_r2` is low on raw `y` because extreme spikes dominate the variance, re-run on `sign(y) * log1p(abs(y))`.

### 3. Check Floating-Point Cancellation vs. Missing Terms

Tests whether small residual errors come from `float32` data generation or catastrophic cancellation (e.g., `exp(x) - 1` near `x = 0`) rather than a missing symbolic term:

```python
import numpy as np

x1 = np.asarray(data["x1"], float)
x2 = np.asarray(data["x2"], float)
y = np.asarray(data["y"], float)
f64 = x1 / (np.exp(x2) - 1)
f32 = (x1.astype(np.float32) / np.expm1(x2.astype(np.float32))).astype(float)

for name, p in [("float64_exp_minus_1", f64), ("float32_expm1", f32)]:
    r = p - y
    finite = np.isfinite(p) & np.isfinite(y)
    print(
        name,
        "finite", round(float(finite.mean()), 5),
        "rmse", float(np.sqrt(np.mean(r[finite] ** 2))),
        "max_abs", float(np.max(np.abs(r[finite]))),
    )
```

### 4. Compare Raw, Trimmed, and Signed-Log Correlations

Reveals dependencies that are masked in raw correlation because 1% of extreme points dominate the sum of squares:

```python
import numpy as np

y = np.asarray(data["y"], float).ravel()
for name, x in data.items():
    if name == "y":
        continue
    x = np.asarray(x, float).ravel()
    ok = np.isfinite(x) & np.isfinite(y)
    xx, yy = x[ok], y[ok]
    lo, hi = np.quantile(yy, [0.01, 0.99])
    keep = (yy >= lo) & (yy <= hi)
    signed = np.sign(yy) * np.log1p(np.abs(yy))
    corr = (
        lambda a, b: float(np.corrcoef(a, b)[0, 1])
        if np.std(a) > 0 and np.std(b) > 0
        else float("nan")
    )
    print(
        name,
        "raw", corr(xx, yy),
        "trimmed", corr(xx[keep], yy[keep]),
        "signed_log", corr(xx, signed),
        "top1pct_y2_share",
        float(np.sort(yy * yy)[-max(1, len(yy) // 100) :].sum() / np.sum(yy * yy)),
    )
```

### 5. Screen for Singular Power Factors ($y \cdot x^p$)

Checks whether multiplying `y` by a power of `x` stabilizes its scale near $x \to 0$:

```python
import numpy as np

y = np.asarray(data["y"], float)
for name, x in data.items():
    if name == "y":
        continue
    x = np.asarray(x, float)
    print("SINGULARITY", name)
    for idx in np.array_split(np.argsort(np.abs(x)), 10)[:4]:
        print(
            "  median_abs_x", float(np.median(np.abs(x[idx]))),
            "median_abs_y", float(np.median(np.abs(y[idx]))),
        )
    for p in [-3, -2, -1, 1, 2, 3]:
        z = y * np.power(x, p)
        good = np.isfinite(z)
        scale = np.median(np.abs(z[good])) + 1e-300
        print(
            "  p", p,
            "relative_mad",
            float(np.median(np.abs(z[good] - np.median(z[good]))) / scale),
        )
```

### 6. Inspect Binned Residuals Across Each Input Feature

```python
import numpy as np

r = y - pred
den = np.maximum(np.abs(y), np.quantile(np.abs(y), 0.01) + 1e-300)
rr = r / den
print(
    "residual_q", np.quantile(r, [0, 0.01, 0.5, 0.99, 1]).tolist(),
    "relative_q", np.quantile(rr, [0, 0.01, 0.5, 0.99, 1]).tolist(),
)
for name, x in data.items():
    if name == "y":
        continue
    edges = np.quantile(x, np.linspace(0, 1, 9))
    bins = np.clip(np.searchsorted(edges[1:-1], x), 0, 7)
    summary = []
    for b in range(8):
        z = r[bins == b]
        summary.append((len(z), float(np.mean(z)), float(np.sqrt(np.mean(z * z)))))
    print(name, "bins(n,mean,rmse)", summary)
```

### 7. Test a Small Hand-Crafted Basis via Least Squares

```python
import numpy as np

y = np.asarray(data["y"], float)
terms = {
    "1": np.ones_like(y),
    "x1": data["x1"],
    "1/x2": 1 / data["x2"],
    "log(x1)": np.log(data["x1"]),
    "cos(x3-x4)": np.cos(data["x3"] - data["x4"]),
}
names = list(terms)
A = np.column_stack([terms[n] for n in names])
ok = np.isfinite(A).all(1) & np.isfinite(y)
b = np.linalg.lstsq(A[ok], y[ok], rcond=None)[0]
print(
    "condition", float(np.linalg.cond(A[ok])),
    "top_terms", sorted(zip(np.abs(b), names, b), reverse=True)[:10],
)
```
