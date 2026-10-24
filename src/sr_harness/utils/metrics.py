# Copyright (c) 2024-present, Yumeow. Licensed under the MIT License.
import numpy as np

__all__ = [
    "R2_score",
    "RMSE_score",
    "sMAPE_score",
    "MAPE_score",
    "MAE_score",
]


def R2_score(true, pred):
    """Compute the coefficient of determination ($R^2$) between ``true`` and ``pred``.

    Args:
        true: Ground-truth target array.
        pred: Predicted value array.

    Returns:
        float: $R^2$ score.
    """
    return 1 - np.mean((true - pred) ** 2) / np.var(true)


def RMSE_score(true, pred):
    """Compute the root mean squared error (RMSE) between ``true`` and ``pred``.

    Args:
        true: Ground-truth target array.
        pred: Predicted value array.

    Returns:
        float: Root mean squared error.
    """
    return np.sqrt(np.mean((true - pred) ** 2))


def sMAPE_score(true, pred):
    """Compute the symmetric mean absolute percentage error (sMAPE) between ``true`` and ``pred``.

    Args:
        true: Ground-truth target array.
        pred: Predicted value array.

    Returns:
        float: sMAPE value in ``[0, 1]``.
    """
    return 2 * np.mean(np.abs(true - pred) / (np.abs(true) + np.abs(pred) + 1e-6))


def MAPE_score(true, pred):
    """Compute the mean absolute percentage error (MAPE) between ``true`` and ``pred``.

    Args:
        true: Ground-truth target array.
        pred: Predicted value array.

    Returns:
        float: MAPE value.
    """
    return np.mean(np.abs(true - pred) / (np.abs(true) + 1e-6))


def MAE_score(true, pred):
    """Compute the mean absolute error (MAE) between ``true`` and ``pred``.

    Args:
        true: Ground-truth target array.
        pred: Predicted value array.

    Returns:
        float: Mean absolute error.
    """
    return np.mean(np.abs(true - pred))
