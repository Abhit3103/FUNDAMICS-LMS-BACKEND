import time
from collections import defaultdict
from typing import Dict, List, Optional
from fastapi import Request
from src.core.exceptions import RateLimitError


class InMemoryRateLimiter:
    """
    Sliding window in-memory rate limiter for sensitive endpoints.
    Protects against credential stuffing, brute force, and rapid duplicate POST attempts.
    """

    def __init__(self, max_requests: int = 5, window_seconds: int = 60, min_interval_seconds: float = 1.0):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.min_interval_seconds = min_interval_seconds
        # Stores list of timestamps per key: key -> [timestamp, ...]
        self._history: Dict[str, List[float]] = defaultdict(list)
        # Stores last request timestamp for rapid debounce: key -> timestamp
        self._last_request_time: Dict[str, float] = {}

    def _clean_old_entries(self, key: str, now: float) -> None:
        cutoff = now - self.window_seconds
        self._history[key] = [t for t in self._history[key] if t > cutoff]

    def check(self, key: str) -> None:
        now = time.time()

        # 1. Anti-spam / Debounce check: block rapid bursts (< min_interval_seconds apart)
        last_time = self._last_request_time.get(key)
        if last_time and (now - last_time) < self.min_interval_seconds:
            raise RateLimitError(
                "A login request is already being processed. Please avoid multiple rapid submissions."
            )

        # 2. Window limit check: clean history and verify max_requests limit
        self._clean_old_entries(key, now)
        if len(self._history[key]) >= self.max_requests:
            remaining_seconds = int(self.window_seconds - (now - self._history[key][0]))
            wait_time = max(1, remaining_seconds)
            raise RateLimitError(
                f"Too many login attempts. Please wait {wait_time} seconds before trying again."
            )

        # Record this attempt
        self._history[key].append(now)
        self._last_request_time[key] = now


# Shared rate limiter instances
login_rate_limiter = InMemoryRateLimiter(
    max_requests=5,           # Maximum 5 attempts per window
    window_seconds=60,         # 1-minute window
    min_interval_seconds=1.5,  # Must be at least 1.5s between POSTs to stop duplicate clicks
)


async def rate_limit_login(request: Request) -> None:
    """
    FastAPI dependency to rate-limit login attempts by client IP address and X-Forwarded-For.
    """
    client_ip = (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )
    key = f"login:{client_ip}"
    login_rate_limiter.check(key)
