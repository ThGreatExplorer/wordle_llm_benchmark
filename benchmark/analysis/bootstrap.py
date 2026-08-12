from __future__ import annotations

import random
from collections.abc import Callable, Sequence


def confidence_interval(
    items: Sequence, statistic: Callable[[Sequence], float | None], *,
    resamples: int = 10_000, seed: int = 0,
) -> tuple[float | None, float | None]:
    if not items or resamples < 1:
        return None, None
    rng = random.Random(seed)
    values = sorted(
        value for _ in range(resamples)
        if (value := statistic([items[rng.randrange(len(items))] for _ in items])) is not None
    )
    if not values:
        return None, None
    return values[int(0.025 * (len(values) - 1))], values[int(0.975 * (len(values) - 1))]
