from __future__ import annotations

import time

import pytest

from src.reliability.rate_limit import RateLimiter, RuntimeRateLimitConfig


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


class TestRuntimeRateLimitConfig:
    def test_valid_text_and_vision_rpm_are_parsed_separately(self):
        config = RuntimeRateLimitConfig.from_env({
            "CABAI_KMS_TEXT_RPM": "12",
            "CABAI_KMS_VISION_RPM": "3.5",
        })
        assert config.text_rpm == 12.0
        assert config.vision_rpm == 3.5

    def test_missing_or_blank_values_disable_limiters(self):
        config = RuntimeRateLimitConfig.from_env({"CABAI_KMS_TEXT_RPM": "  "})
        assert config.text_rpm is None
        assert config.vision_rpm is None

    @pytest.mark.parametrize("value", ["0", "-1", "not-a-number", "nan", "inf"])
    @pytest.mark.parametrize("name", ["CABAI_KMS_TEXT_RPM", "CABAI_KMS_VISION_RPM"])
    def test_invalid_values_fail_fast(self, name, value):
        with pytest.raises(ValueError, match=name):
            RuntimeRateLimitConfig.from_env({name: value})
