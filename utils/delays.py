"""Small asynchronous delay helpers for respectful public-source collection."""

from __future__ import annotations

import asyncio
import random


_RANDOM = random.SystemRandom()


def backoff_seconds(attempt: int, *, base: float = 0.5, cap: float = 30.0, jitter: float = 0.25) -> float:
    """Return capped exponential backoff with bounded random jitter."""

    safe_attempt = max(0, attempt)
    value = min(cap, base * (2**safe_attempt))
    return max(0.0, value + _RANDOM.uniform(0.0, max(0.0, jitter)))


async def sleep_with_jitter(base_seconds: float, jitter_seconds: float = 0.5) -> None:
    """Sleep for a small randomized interval; never blocks the event loop."""

    delay = max(0.0, base_seconds) + _RANDOM.uniform(0.0, max(0.0, jitter_seconds))
    if delay:
        await asyncio.sleep(delay)


async def espera_aleatoria(min_seg: float = 1.5, max_seg: float = 4.0) -> None:
    """Compatibility helper for a bounded, non-blocking randomized pause."""

    if min_seg < 0 or max_seg < min_seg:
        raise ValueError("O intervalo de espera é inválido.")
    await asyncio.sleep(random.uniform(min_seg, max_seg))


async def aplicar_delay_jitter(min_s: float = 3.0, max_s: float = 6.0) -> None:
    """Compatibility helper for the collector's jitter delay contract."""
    await espera_aleatoria(min_s, max_s)
