"""Training-only calibration of a fixed additional regression residual scale."""
from __future__ import annotations

import hashlib
import numpy as np
from scipy.optimize import minimize_scalar

from ..evaluator.observational_contract import audit_contract


def estimate_affine_scatter(data, contract) -> dict:
    """Profile Gaussian residual scale using a predeclared affine training baseline.

    The baseline uses every permitted predictor, standardized using training
    rows only, plus an intercept. Its coefficients are nuisance parameters for
    this calibration, not a proposed discovery formula. The fitted residual
    scale includes baseline misspecification; it is not a physical intrinsic
    scatter measurement. Validation target values never enter the calculation.
    """
    report = audit_contract(contract, data)
    if not report['valid']:
        raise ValueError('; '.join(report['errors']))
    if contract.get('task_type') != 'regression':
        raise ValueError('Scatter calibration supports regression only')
    if contract.get('covariance') or contract.get('uncertainty_lower') or contract.get('uncertainty_upper'):
        raise ValueError('Scatter calibration requires independent symmetric uncertainty, not covariance/asymmetric errors')
    uncertainty = contract.get('uncertainty')
    if not uncertainty or not contract.get('split'):
        raise ValueError('Declare independent uncertainty and a frozen train/validation split')
    mask = np.asarray(data[contract['split']]) == 'train'
    y = np.asarray(data[contract['target']])[mask].astype(float)
    sigma = np.asarray(data[uncertainty])[mask].astype(float)
    features = list(contract.get('features', []))
    columns = [np.ones(len(y))]
    for name in features:
        column = np.asarray(data[name])[mask].astype(float)
        if column.shape != y.shape or not np.isfinite(column).all():
            raise ValueError('Training predictors must be finite one-dimensional arrays')
        centered = column - np.mean(column)
        scale = np.std(column)
        columns.append(centered / scale if scale > 0 else centered)
    design = np.column_stack(columns)
    rank = int(np.linalg.matrix_rank(design))
    if len(y) <= rank + 1:
        raise ValueError('Too few training observations for a residual-scale calibration')
    upper = 5 * max(float(np.std(y)), float(np.max(sigma)), np.finfo(float).eps)
    evaluations = 0

    def profile(scatter):
        nonlocal evaluations
        evaluations += 1
        variance = sigma ** 2 + scatter ** 2
        standard_deviation = np.sqrt(variance)
        beta = np.linalg.lstsq(design / standard_deviation[:, None], y / standard_deviation, rcond=None)[0]
        residual = y - design @ beta
        value = 0.5 * np.mean(residual ** 2 / variance + np.log(2 * np.pi * variance))
        if not np.isfinite(value):
            raise ValueError('Nonfinite training likelihood during scatter calibration')
        return float(value)

    result = minimize_scalar(profile, bounds=(0.0, upper), method='bounded',
                             options={'xatol': max(upper * 1e-9, np.finfo(float).eps), 'maxiter': 256})
    if not result.success or not np.isfinite(result.fun):
        raise ValueError('Scatter calibration did not converge')
    zero_loss, upper_loss = profile(0.0), profile(upper)
    scatter, loss = (0.0, zero_loss) if zero_loss <= result.fun else (float(result.x), float(result.fun))
    if scatter >= upper * (1 - 1e-6) or upper_loss < loss:
        raise ValueError('Scatter calibration reached its upper bound; review the observation model')
    old_weights = 1 / sigma ** 2
    new_weights = 1 / (sigma ** 2 + scatter ** 2)
    effective_size = lambda weights: float(weights.sum() ** 2 / np.dot(weights, weights))
    fingerprint = hashlib.sha256()
    for name in (contract['target'], uncertainty, *features):
        fingerprint.update(name.encode('utf-8'))
        fingerprint.update(np.asarray(data[name])[mask].astype('<f8').tobytes())
    fingerprint.update(np.flatnonzero(mask).astype('<i8').tobytes())
    return {
        'method': 'training_only_affine_profile_gaussian_nll',
        'extra_scatter': scatter,
        'training_samples': int(len(y)),
        'baseline_features': features,
        'baseline_rank': rank,
        'baseline_columns': len(columns),
        'effective_sample_size_before': effective_size(old_weights),
        'effective_sample_size_after': effective_size(new_weights),
        'training_nll': loss,
        'training_nll_zero_scatter': zero_loss,
        'profile_evaluations': evaluations,
        'upper_search_bound': upper,
        'training_data_sha256': fingerprint.hexdigest(),
        'validation_used': False,
        'warning': 'This residual scale includes affine-baseline misspecification and is not a measurement of physical intrinsic scatter. Freeze it before formula search; changing it invalidates earlier score comparisons.',
    }
