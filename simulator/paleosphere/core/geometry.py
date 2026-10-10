from __future__ import annotations

import math

import numpy as np


def distance(a: np.ndarray, b: np.ndarray) -> float:
    return math.hypot(float(a[0] - b[0]), float(a[1] - b[1]))


def unit(v: np.ndarray) -> np.ndarray:
    n = math.hypot(float(v[0]), float(v[1]))
    if n < 1e-9:
        return np.zeros(2)
    return v / n
