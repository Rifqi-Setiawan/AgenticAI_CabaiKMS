"""Retry policy for transient provider failures (timeouts, connection
errors, rate limits) — via tenacity, exponential backoff.

Deliberately NOT for contract/validation failures: a network blip and a
model producing structurally invalid output call for different remedies.
The former is handled here (retry the same call, unchanged); the latter
goes through the Verifier/Critic's revise loop instead
(src/reliability/verifier.py). src/reliability/wrappers.py is where both
get composed for a real agent call.
"""

from __future__ import annotations

from typing import Callable, TypeVar

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.reliability.rate_limit import RateLimiter

T = TypeVar("T")

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BASE_DELAY = 1.0
DEFAULT_MAX_DELAY = 10.0


def with_retry(
    *,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    rate_limiter: RateLimiter | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator factory: @with_retry(exceptions=(LLMCallError,), max_attempts=3).
    If `rate_limiter` is given, capacity is acquired before every attempt
    (including retries), not just the first."""

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @retry(
            retry=retry_if_exception_type(exceptions),
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=base_delay, max=max_delay),
            reraise=True,
        )
        def wrapped(*args, **kwargs):
            if rate_limiter is not None:
                rate_limiter.acquire_sync()
            return func(*args, **kwargs)

        return wrapped

    return decorator


def run_with_retry(
    func: Callable[..., T],
    *args,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    rate_limiter: RateLimiter | None = None,
    **kwargs,
) -> T:
    """Plain-call form of with_retry — call `func(*args, **kwargs)` with
    retry applied, without needing a separate decorated definition. This
    is what src/reliability/wrappers.py uses to retry an existing function
    (e.g. classify_image) at the call site."""
    wrapped = with_retry(
        exceptions=exceptions,
        max_attempts=max_attempts,
        base_delay=base_delay,
        max_delay=max_delay,
        rate_limiter=rate_limiter,
    )(func)
    return wrapped(*args, **kwargs)
