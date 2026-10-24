"""Small reusable loss functions; no prescribed astrophysical function family.

Copy the needed function into a workspace evaluator. Coefficients must be fit
with the same objective, using train only. These helpers do not install an
evaluator, select a split, choose binning or infer completeness.
"""
import numpy as np


def weighted_squared_error(observed, predicted, sigma, extra_scatter=0.0):
    """Mean squared standardized residual; scatter must be fixed or fit on train.

    When estimating scatter jointly, use a Gaussian likelihood including its
    log-variance term instead: minimizing this score alone inflates scatter.
    """
    y, p, s = np.broadcast_arrays(observed, predicted, sigma)
    if not y.size or not all(np.isfinite(x).all() for x in (y, p, s)) or np.any(s <= 0):
        raise ValueError('finite observations/predictions and positive errors required')
    if not np.isfinite(extra_scatter) or extra_scatter < 0:
        raise ValueError('extra_scatter must be finite and nonnegative')
    return float(np.mean((y-p)**2 / (s*s + extra_scatter**2)))


def poisson_deviance(counts, expected_counts):
    """Mean Poisson deviance; expected counts must already include bin integrals.

    Do not substitute density-at-center without widths and selection/exposure.
    Exact zero expected counts with positive observed counts has infinite loss.
    """
    n, mu = np.broadcast_arrays(np.asarray(counts, float), np.asarray(expected_counts, float))
    if not n.size or not np.isfinite(n).all() or not np.isfinite(mu).all() or np.any(n < 0) or np.any(mu < 0):
        raise ValueError('finite nonnegative counts and expectations required')
    if np.any((n > 0) & (mu == 0)):
        return float('inf')
    terms = mu - n
    positive = n > 0
    terms = terms.copy()
    terms[positive] += n[positive]*np.log(n[positive]/mu[positive])
    return float(2*np.mean(terms))


def selected_density_nll(event_density, grid_density, grid, event_selection, grid_selection):
    """Conditional unbinned NLL under explicitly supplied detection selection.

    All densities and quadrature coordinates must use the SAME measure. With
    log-coordinate densities, transform the density with its Jacobian. Supply
    a sufficiently resolved increasing grid spanning the declared support, and
    check integration convergence. Selection is a probability, not 1/Vmax.
    """
    f, q = np.broadcast_arrays(np.asarray(event_density, float), np.asarray(event_selection, float))
    g, w, x = map(lambda a: np.asarray(a, float), (grid_density, grid_selection, grid))
    if x.ndim != 1 or len(x) < 2 or g.shape != x.shape or w.shape != x.shape or np.any(np.diff(x) <= 0):
        raise ValueError('aligned densities and selection on an increasing support grid required')
    if not f.size or not all(np.isfinite(a).all() for a in (f,q,g,w,x)):
        raise ValueError('nonempty finite values required')
    if np.any(f < 0) or np.any(g < 0) or np.any((q < 0) | (q > 1)) or np.any((w < 0) | (w > 1)):
        raise ValueError('nonnegative density and selection probabilities in [0,1] required')
    norm = np.trapezoid(g*w, x)
    if norm <= 0 or np.any(f*q <= 0):
        return float('inf')
    return float(-np.mean(np.log(f*q)) + np.log(norm))
