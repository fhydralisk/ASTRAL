# Copyright (c) 2024-present, Yumeow. Licensed under the MIT License.
import os
import random
import builtins

__all__ = [
    "softmax",
    "seed_all",
    "bounded_value",
]


def bounded_value(value, min, max, default, converter=None):
    """Convert ``value`` (when ``converter`` is given) and clamp it to the inclusive range ``[min, max]``.

    Args:
        value: Raw input value (returns ``default`` if ``value is None``).
        min: Lower inclusive bound (or ``None`` for no lower bound).
        max: Upper inclusive bound (or ``None`` for no upper bound).
        default: Fallback value returned when ``value is None``.
        converter: Optional callable (such as ``int`` or ``float``) applied before clamping.

    Returns:
        Any: Clamped value within ``[min, max]``.
    """
    try:
        parsed = converter(value) if converter is not None else value
    except (TypeError, ValueError):
        parsed = default
    return builtins.max(min, builtins.min(max, parsed))


def softmax(x):
    """Compute the numerically stable softmax probability distribution over array ``x``.

    Args:
        x: Input 1D or N-D numeric array.

    Returns:
        np.ndarray: Softmax probabilities summing to 1.
    """
    import numpy as np
    x = np.exp(x - x.max())
    return x / x.sum()


def seed_all(seed):
    """Seed Python's ``random``, NumPy, and PyTorch (when installed) for reproducible experiments.

    Args:
        seed: Integer random seed.
    """
    os.environ["PL_GLOBAL_SEED"] = str(seed)
    random.seed(seed)
    try:
        import numpy as np
        np.random.seed(seed)
    except ImportError:
        pass
    try:
        import torch
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        torch.cuda.manual_seed(seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    except ImportError:
        pass
