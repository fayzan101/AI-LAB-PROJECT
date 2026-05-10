import time
from collections import defaultdict, deque

from redis import Redis


class RateLimiter:
    def __init__(self, window_seconds: int, max_requests: int, redis_url: str | None = None) -> None:
        self.window_seconds = window_seconds
        self.max_requests = max_requests
        self.redis = Redis.from_url(redis_url, decode_responses=True) if redis_url else None
        self.in_memory_hits: dict[str, deque[int]] = defaultdict(deque)

    def is_limited(self, client_id: str) -> bool:
        now = int(time.time())
        if self.redis:
            key = f"rate_limit:{client_id}:{now // self.window_seconds}"
            count = self.redis.incr(key)
            if count == 1:
                self.redis.expire(key, self.window_seconds)
            return count > self.max_requests

        request_times = self.in_memory_hits[client_id]
        while request_times and request_times[0] <= now - self.window_seconds:
            request_times.popleft()
        if len(request_times) >= self.max_requests:
            return True
        request_times.append(now)
        return False
