import time
import threading
from typing import Dict, List
from fastapi import Request, HTTPException, status


class InMemoryRateLimiter:
    """
    Thread-safe sliding-window in-memory rate limiter.
    Zero external dependencies (no Redis required for single-node deployment).
    """

    def __init__(self):
        self._history: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, max_requests: int, window_seconds: int = 60) -> None:
        now = time.time()
        with self._lock:
            # Purge expired timestamps
            timestamps = self._history.get(key, [])
            valid_timestamps = [t for t in timestamps if (now - t) < window_seconds]

            if len(valid_timestamps) >= max_requests:
                retry_after = int(window_seconds - (now - valid_timestamps[0])) + 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded ({max_requests} calls per {window_seconds}s). Retry in {retry_after}s.",
                    headers={"Retry-After": str(retry_after)}
                )

            valid_timestamps.append(now)
            self._history[key] = valid_timestamps


rate_limiter = InMemoryRateLimiter()


def rate_limit_auth(request: Request):
    """Rate limit authentication attempts: 30 attempts per minute per IP."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    rate_limiter.check(f"auth:{client_ip}", max_requests=30, window_seconds=60)


def rate_limit_agent(request: Request):
    """Rate limit AI agent command parsing: 60 commands per minute per IP."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    rate_limiter.check(f"agent:{client_ip}", max_requests=60, window_seconds=60)
