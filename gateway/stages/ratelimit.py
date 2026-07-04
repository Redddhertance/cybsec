# stage 3 - rate limiting, token bucket.
# each user id gets a bucket of `capacity` tokens refilling at `refill_per_sec`. one req
# burns one token, empty bucket -> 429 + a Retry-After hint.
# the real bucket lives in redis, bumped atomically by a lua script so multiple workers
# share the one limit. if redis is down we quietly drop to a process-local bucket so
# dev/tests still run.

from __future__ import annotations

import threading
import time

import redis.asyncio as aioredis
from redis.exceptions import RedisError

from gateway.config import Settings
from gateway.stages import StageError

_STAGE = "ratelimit"

# atomic refill+consume. uses redis server clock (TIME) so all workers agree on "now".
# returns {allowed, retry_after, remaining}.
_LUA = """
local capacity = tonumber(ARGV[1])
local refill = tonumber(ARGV[2])
local requested = tonumber(ARGV[3])
local t = redis.call('TIME')
local now = tonumber(t[1]) + tonumber(t[2]) / 1000000
local data = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil then
  tokens = capacity
  ts = now
end
local elapsed = now - ts
if elapsed < 0 then elapsed = 0 end
tokens = math.min(capacity, tokens + elapsed * refill)
local allowed = 0
local retry_after = 0
if tokens >= requested then
  tokens = tokens - requested
  allowed = 1
else
  retry_after = (requested - tokens) / refill
end
redis.call('HSET', KEYS[1], 'tokens', tokens, 'ts', now)
redis.call('EXPIRE', KEYS[1], math.ceil(capacity / refill) + 1)
return {allowed, tostring(retry_after), tostring(tokens)}
"""


class _LocalBucket:
    # in-mem token bucket fallback, single process

    def __init__(self, capacity: int, refill: float) -> None:
        self.capacity = capacity
        self.refill = refill
        self._state: dict[str, tuple[float, float]] = {}  # user -> (tokens, ts)
        self._lock = threading.Lock()

    def consume(self, user_id: str) -> tuple[bool, float]:
        now = time.monotonic()
        with self._lock:
            tokens, ts = self._state.get(user_id, (float(self.capacity), now))
            tokens = min(self.capacity, tokens + max(0.0, now - ts) * self.refill)
            if tokens >= 1.0:
                self._state[user_id] = (tokens - 1.0, now)
                return True, 0.0
            self._state[user_id] = (tokens, now)
            return False, (1.0 - tokens) / self.refill


class RateLimiter:
    def __init__(self, settings: Settings) -> None:
        self._capacity = settings.rate_capacity
        self._refill = settings.rate_refill_per_sec
        self._redis: aioredis.Redis | None = None
        try:
            self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        except (RedisError, ValueError):
            self._redis = None
        self._local = _LocalBucket(self._capacity, self._refill)
        self.using_fallback = self._redis is None

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()

    async def check(self, user_id: str) -> None:
        # consume one token, raise 429 if the bucket's empty
        allowed, retry_after = await self._consume(user_id)
        if not allowed:
            secs = max(1, round(retry_after))
            raise StageError(
                _STAGE,
                429,
                "Rate limit exceeded.",
                headers={"Retry-After": str(secs)},
            )

    async def _consume(self, user_id: str) -> tuple[bool, float]:
        key = f"ratelimit:{user_id}"
        if self._redis is not None:
            try:
                allowed, retry_after, _remaining = await self._redis.eval(
                    _LUA, 1, key, self._capacity, self._refill, 1
                )
                self.using_fallback = False
                return bool(int(allowed)), float(retry_after)
            except RedisError:
                # redis died mid-flight -> drop to the local bucket
                self.using_fallback = True
        return self._local.consume(user_id)
