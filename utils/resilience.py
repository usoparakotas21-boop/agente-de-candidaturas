"""Retry primitives shared by the isolated collectors."""

from __future__ import annotations

import asyncio
import functools
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from .delays import backoff_seconds


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    attempts: int = 3
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 20.0


class RetryExhaustedError(RuntimeError):
    """Raised after a bounded retry policy is exhausted."""


async def run_with_retries(
    operation: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy,
    retry_if: Callable[[Exception], bool] | None = None,
) -> T:
    """Run an async operation with bounded exponential backoff."""

    attempts = max(1, policy.attempts)
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return await operation()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - the policy decides what is retryable
            last_error = exc
            if attempt == attempts - 1 or (retry_if is not None and not retry_if(exc)):
                raise
            await asyncio.sleep(
                backoff_seconds(
                    attempt,
                    base=policy.base_delay_seconds,
                    cap=policy.max_delay_seconds,
                )
            )
    raise RetryExhaustedError("A operação não foi concluída após as tentativas configuradas.") from last_error


def com_tentativas(tentativas_max: int = 3, espera_base: float = 2.0):
    """Decorator kept for simple collector functions using the legacy API."""

    if tentativas_max < 1 or espera_base < 0:
        raise ValueError("A política de tentativas é inválida.")

    def decorador(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            tentativa = 0
            while tentativa < tentativas_max:
                try:
                    return await func(*args, **kwargs)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    tentativa += 1
                    if tentativa >= tentativas_max:
                        raise
                    await asyncio.sleep(espera_base * tentativa)

        return wrapper

    return decorador

class CircuitOpenError(RuntimeError):
    """Raised when a source is temporarily failing and the circuit is open."""


class CircuitBreaker:
    """Small async circuit breaker for unreliable external job sources."""

    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 30.0):
        if failure_threshold < 1 or recovery_timeout < 0:
            raise ValueError("A configuração do Circuit Breaker é inválida.")
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failure_count = 0
        self._opened_at: float | None = None
        self._half_open_probe = False
        self._lock = asyncio.Lock()

    @property
    def state(self) -> str:
        if self._opened_at is None:
            return "closed"
        if time.monotonic() - self._opened_at >= self.recovery_timeout:
            return "half_open"
        return "open"

    async def before_call(self) -> None:
        async with self._lock:
            if self._opened_at is None:
                return
            if time.monotonic() - self._opened_at < self.recovery_timeout:
                raise CircuitOpenError("Circuit Breaker aberto temporariamente.")
            if self._half_open_probe:
                raise CircuitOpenError("Circuit Breaker aguardando o teste de recuperação.")
            self._half_open_probe = True

    async def record_success(self) -> None:
        async with self._lock:
            self._failure_count = 0
            self._opened_at = None
            self._half_open_probe = False

    async def record_failure(self) -> None:
        async with self._lock:
            self._failure_count += 1
            self._half_open_probe = False
            if self._failure_count >= self.failure_threshold:
                self._opened_at = time.monotonic()

    async def execute(self, operation: Callable[[], Awaitable[T]]) -> T:
        await self.before_call()
        try:
            result = await operation()
        except asyncio.CancelledError:
            raise
        except Exception:
            await self.record_failure()
            raise
        await self.record_success()
        return result


async def executar_com_resiliencia(
    operacao: Callable[[], Awaitable[T]],
    *,
    tentativas: int = 3,
    espera_base: float = 1.0,
    espera_maxima: float = 30.0,
    circuit_breaker: CircuitBreaker | None = None,
    retry_if: Callable[[Exception], bool] | None = None,
) -> T:
    """Execute an async operation with circuit protection and exponential backoff."""

    if tentativas < 1 or espera_base < 0 or espera_maxima < espera_base:
        raise ValueError("A política de resiliência é inválida.")

    for tentativa in range(tentativas):
        try:
            if circuit_breaker is not None:
                return await circuit_breaker.execute(operacao)
            return await operacao()
        except asyncio.CancelledError:
            raise
        except CircuitOpenError:
            raise
        except Exception as exc:
            ultima_tentativa = tentativa >= tentativas - 1
            if ultima_tentativa or (retry_if is not None and not retry_if(exc)):
                raise
            await asyncio.sleep(
                backoff_seconds(
                    tentativa,
                    base=espera_base,
                    cap=espera_maxima,
                )
            )

    raise RetryExhaustedError("A operação não foi concluída.")
