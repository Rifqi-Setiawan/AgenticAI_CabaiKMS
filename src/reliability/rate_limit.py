"""Token-bucket rate limiting via aiolimiter, so LLM/LVM calls never
exceed a provider's request quota.

aiolimiter is asyncio-only; every agent/provider call site in this project
is currently synchronous. RateLimiter.acquire_sync() bridges the two with
ONE persistent event loop per instance, created once and reused for every
acquire — never asyncio.run() per call, which would create/destroy a
fresh loop each time and hit aiolimiter's cross-loop-reuse recovery path
(it's handled gracefully there, but there's no reason to trigger it when
avoiding it entirely is this cheap).
"""

from __future__ import annotations

import asyncio
import functools
import math
import os
import threading
from dataclasses import dataclass
from collections.abc import Mapping
from typing import Callable, TypeVar

from aiolimiter import AsyncLimiter

T = TypeVar("T")
TEXT_RPM_ENV = "CABAI_KMS_TEXT_RPM"
VISION_RPM_ENV = "CABAI_KMS_VISION_RPM"


def _optional_positive_rpm(name: str, environ: Mapping[str, str]) -> float | None:
    raw = environ.get(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive numeric requests-per-minute value") from exc
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive numeric requests-per-minute value")
    return value


@dataclass(frozen=True)
class RuntimeRateLimitConfig:
    """Optional per-provider attempt limits loaded once for a pipeline run."""

    text_rpm: float | None = None
    vision_rpm: float | None = None

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "RuntimeRateLimitConfig":
        source = os.environ if environ is None else environ
        return cls(
            text_rpm=_optional_positive_rpm(TEXT_RPM_ENV, source),
            vision_rpm=_optional_positive_rpm(VISION_RPM_ENV, source),
        )


def describe_rate_limiter(limiter: "RateLimiter | None") -> str:
    if limiter is None:
        return "disabled"
    rate = f"{limiter.max_rate:g}"
    period = f"{limiter.time_period:g}"
    return f"enabled, {rate} requests / {period}s"


class RateLimiter:
    """`max_rate` acquisitions per `time_period` seconds, leaky-bucket
    style (bursts up to `max_rate` are allowed immediately; beyond that,
    acquire_sync() blocks until capacity frees up)."""

    def __init__(self, max_rate: float, time_period: float = 60.0):
        self._limiter = AsyncLimiter(max_rate, time_period)
        self._loop = asyncio.new_event_loop()
        self._lock = threading.Lock()

    @property
    def max_rate(self) -> float:
        return self._limiter.max_rate

    @property
    def time_period(self) -> float:
        return self._limiter.time_period

    def has_capacity(self, amount: float = 1) -> bool:
        # has_capacity() is a plain sync method on AsyncLimiter, but it
        # still touches an internal event-loop reference for timing. If
        # acquire_sync() was never called yet, that reference isn't bound
        # to anything and resolving it requires a genuinely running loop
        # — so route through the same persistent loop as acquire_sync,
        # rather than calling it bare (which breaks on a fresh instance).
        async def _check() -> bool:
            return self._limiter.has_capacity(amount)

        with self._lock:
            return self._loop.run_until_complete(_check())

    def acquire_sync(self, amount: float = 1) -> None:
        """Blocks (synchronously) until `amount` capacity is available."""
        with self._lock:
            self._loop.run_until_complete(self._limiter.acquire(amount))

    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        """Use as a decorator: acquires capacity before every call."""

        @functools.wraps(func)
        def wrapped(*args, **kwargs):
            self.acquire_sync()
            return func(*args, **kwargs)

        return wrapped

    def close(self) -> None:
        if not self._loop.is_closed():
            self._loop.close()

    def __del__(self) -> None:  # pragma: no cover — best-effort cleanup
        try:
            self.close()
        except Exception:
            pass
