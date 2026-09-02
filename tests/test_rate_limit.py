from __future__ import annotations

import time

from src.reliability.rate_limit import RateLimiter


class TestRateLimiter:
    def test_burst_up_to_max_rate_is_immediate(self):
        limiter = RateLimiter(max_rate=3, time_period=1.0)
        start = time.monotonic()
        for _ in range(3):
            limiter.acquire_sync()
        elapsed = time.monotonic() - start
        assert elapsed < 0.05
        limiter.close()

    def test_exceeding_burst_capacity_actually_blocks(self):
        limiter = RateLimiter(max_rate=2, time_period=0.4)
        limiter.acquire_sync()
        limiter.acquire_sync()

        start = time.monotonic()
        limiter.acquire_sync()  # capacity exhausted — must wait
        elapsed = time.monotonic() - start

        assert elapsed >= 0.15  # genuinely held, not a no-op
        limiter.close()

    def test_has_capacity_reflects_current_state(self):
        limiter = RateLimiter(max_rate=1, time_period=1.0)
        assert limiter.has_capacity() is True
        limiter.acquire_sync()
        assert limiter.has_capacity() is False
        limiter.close()

    def test_capacity_replenishes_after_time_period(self):
        limiter = RateLimiter(max_rate=1, time_period=0.2)
        limiter.acquire_sync()
        assert limiter.has_capacity() is False
        time.sleep(0.25)
        assert limiter.has_capacity() is True
        limiter.close()

    def test_usable_as_a_decorator(self):
        limiter = RateLimiter(max_rate=5, time_period=1.0)
        calls = []

        @limiter
        def do_thing(x):
            calls.append(x)
            return x * 2

        assert do_thing(3) == 6
        assert calls == [3]
        limiter.close()

    def test_max_rate_and_time_period_are_exposed(self):
        limiter = RateLimiter(max_rate=7, time_period=42.0)
        assert limiter.max_rate == 7
        assert limiter.time_period == 42.0
        limiter.close()
