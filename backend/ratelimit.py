"""A small in-process sliding-window rate limiter.

Enough for one backend instance, which is what this deployment is. If the
backend is ever scaled horizontally, move the window into Postgres or Redis.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            bucket = self._hits[key]
            cutoff = now - self.window
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self.limit:
                retry_after = max(1, int(self.window - (now - bucket[0])))
                raise HTTPException(
                    status_code=429,
                    detail="rate limit exceeded",
                    headers={"Retry-After": str(retry_after)},
                )
            bucket.append(now)
            if len(self._hits) > 5000:  # keep the dict from growing forever
                for stale in [k for k, v in self._hits.items() if not v][:1000]:
                    self._hits.pop(stale, None)
