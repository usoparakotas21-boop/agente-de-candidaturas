"""Optional atomic rate limiting through an Upstash-compatible REST endpoint.

The application keeps its in-process limiter as a fast first layer.  When the
two ``UPSTASH_REDIS_REST_*`` variables are present, this module increments the
same fixed-window counters in a shared Redis instance so separate Render
instances enforce one common budget.
"""

from __future__ import annotations

import os
from typing import Iterable
from uuid import uuid4

import requests


_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
""".strip()


def _settings() -> tuple[str, str]:
    return (
        os.getenv("UPSTASH_REDIS_REST_URL", "").strip().rstrip("/"),
        os.getenv("UPSTASH_REDIS_REST_TOKEN", "").strip(),
    )


def is_configured() -> bool:
    url, token = _settings()
    return bool(url and token)


def increment(key: str, window_seconds: int, *, timeout: float = 1.5) -> int:
    """Atomically increment a fixed-window counter and return its value."""
    url, token = _settings()
    if not url or not token:
        raise RuntimeError("Rate limiting distribuído não está configurado.")
    response = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}"},
        json=["EVAL", _SCRIPT, 1, key, str(max(1, int(window_seconds)))],
        timeout=timeout,
    )
    response.raise_for_status()
    try:
        payload = response.json()
        value = payload.get("result") if isinstance(payload, dict) else payload
        return int(value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise RuntimeError("Resposta inválida do rate limiter distribuído.") from exc



def acquire_lease(key: str, ttl_seconds: int, *, timeout: float = 1.5) -> str | None:
    """Acquire one conservative distributed source slot using an expiring lease."""
    url, token = _settings()
    if not url or not token:
        raise RuntimeError("Rate limiting distribuído não está configurado.")
    lease_token = uuid4().hex
    response = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}"},
        json=["SET", key, lease_token, "NX", "EX", str(max(1, int(ttl_seconds)))],
        timeout=timeout,
    )
    response.raise_for_status()
    try:
        payload = response.json()
        value = payload.get("result") if isinstance(payload, dict) else payload
    except (ValueError, AttributeError) as exc:
        raise RuntimeError("Resposta inválida do rate limiter distribuído.") from exc
    return lease_token if value == "OK" else None


def release_lease(key: str, lease_token: str, *, timeout: float = 1.5) -> bool:
    """Release a distributed slot only when its lease token still matches."""
    url, token = _settings()
    if not url or not token:
        raise RuntimeError("Rate limiting distribuído não está configurado.")
    script = "if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) else return 0 end"
    response = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}"},
        json=["EVAL", script, 1, key, lease_token],
        timeout=timeout,
    )
    response.raise_for_status()
    try:
        payload = response.json()
        value = payload.get("result") if isinstance(payload, dict) else payload
        return int(value) == 1
    except (TypeError, ValueError, AttributeError) as exc:
        raise RuntimeError("Resposta inválida do rate limiter distribuído.") from exc

def check(
    keys: Iterable[str],
    limit: int,
    window_seconds: int,
    *,
    timeout: float = 1.5,
) -> tuple[bool, int]:
    """Increment all keys and return ``(blocked, retry_after_seconds)``."""
    blocked = False
    retry_after = 0
    for key in keys:
        count = increment(key, window_seconds, timeout=timeout)
        if count > int(limit):
            blocked = True
            retry_after = max(retry_after, int(window_seconds))
    return blocked, retry_after
