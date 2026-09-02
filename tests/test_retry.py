from __future__ import annotations

import time

import pytest

from src.reliability.rate_limit import RateLimiter
from src.reliability.retry import run_with_retry, with_retry


class _Boom(Exception):
    pass


class _OtherError(Exception):
    pass


class TestRunWithRetry:
    def test_succeeds_without_retry_when_no_exception(self):
        calls = []

        def f():
            calls.append(1)
            return "ok"

        result = run_with_retry(f, exceptions=(_Boom,), max_attempts=3, base_delay=0.001)
        assert result == "ok"
        assert len(calls) == 1

    def test_retries_active_and_eventually_succeeds(self):
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise _Boom("transient")
            return "ok"

        result = run_with_retry(flaky, exceptions=(_Boom,), max_attempts=5, base_delay=0.001, max_delay=0.01)
        assert result == "ok"
        assert len(calls) == 3  # two failures + the successful 3rd attempt

    def test_gives_up_after_max_attempts_and_reraises(self):
        calls = []

        def always_fails():
            calls.append(1)
            raise _Boom("still broken")

        with pytest.raises(_Boom):
            run_with_retry(always_fails, exceptions=(_Boom,), max_attempts=3, base_delay=0.001, max_delay=0.01)
        assert len(calls) == 3

    def test_non_matching_exception_is_not_retried(self):
        calls = []

        def raises_other():
            calls.append(1)
            raise _OtherError("not our concern")

        with pytest.raises(_OtherError):
            run_with_retry(raises_other, exceptions=(_Boom,), max_attempts=5, base_delay=0.001)
        assert len(calls) == 1  # no retry — wrong exception type

    def test_backoff_actually_delays_between_attempts(self):
        calls = []
        timestamps = []

        def flaky():
            timestamps.append(time.monotonic())
            calls.append(1)
            if len(calls) < 3:
                raise _Boom("transient")
            return "ok"

        run_with_retry(flaky, exceptions=(_Boom,), max_attempts=5, base_delay=0.05, max_delay=1.0)
        gaps = [b - a for a, b in zip(timestamps, timestamps[1:])]
        assert all(gap >= 0.04 for gap in gaps)  # real exponential wait happened, not a no-op

    def test_passes_args_and_kwargs_through(self):
        def f(a, b, *, c):
            return a + b + c

        assert run_with_retry(f, 1, 2, c=3, exceptions=(_Boom,)) == 6

    def test_rate_limiter_is_acquired_before_every_attempt(self):
        limiter = RateLimiter(max_rate=100, time_period=60)
        acquire_calls = []
        original_acquire = limiter.acquire_sync

        def spy_acquire(*a, **k):
            acquire_calls.append(1)
            return original_acquire(*a, **k)

        limiter.acquire_sync = spy_acquire

        calls = []

        def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise _Boom("transient")
            return "ok"

        run_with_retry(
            flaky, exceptions=(_Boom,), max_attempts=5, base_delay=0.001, max_delay=0.01,
            rate_limiter=limiter,
        )
        assert len(acquire_calls) == 3  # once per attempt, including retries
        limiter.close()


class TestWithRetryDecorator:
    def test_decorator_form_behaves_like_run_with_retry(self):
        calls = []

        @with_retry(exceptions=(_Boom,), max_attempts=3, base_delay=0.001, max_delay=0.01)
        def flaky():
            calls.append(1)
            if len(calls) < 2:
                raise _Boom("transient")
            return "ok"

        assert flaky() == "ok"
        assert len(calls) == 2
