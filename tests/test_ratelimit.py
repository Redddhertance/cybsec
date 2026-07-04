# stage 3 - rate limit tests (hits the in-mem fallback bucket)

import pytest

from gateway.config import Settings
from gateway.stages import StageError
from gateway.stages.ratelimit import RateLimiter


@pytest.fixture
def limiter():
    # point redis at a dead port so the limiter uses its in-mem fallback
    settings = Settings(
        redis_url="redis://localhost:1/0",
        rate_capacity=3,
        rate_refill_per_sec=0.0001,  # basically no refill during the test
    )
    rl = RateLimiter(settings)
    # force fallback path regardless of whether a local redis is up
    rl._redis = None
    rl.using_fallback = True
    return rl


async def test_allows_up_to_capacity_then_429(limiter):
    for _ in range(3):
        await limiter.check("user-a")  # shouldnt raise
    with pytest.raises(StageError) as exc:
        await limiter.check("user-a")
    assert exc.value.status_code == 429
    assert "Retry-After" in exc.value.headers


async def test_buckets_are_per_user(limiter):
    for _ in range(3):
        await limiter.check("user-a")
    # diff user = fresh bucket
    await limiter.check("user-b")
