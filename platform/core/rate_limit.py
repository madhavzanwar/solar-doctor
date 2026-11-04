"""In-process sliding-window limiter for failed login attempts.

Deliberately in-memory: the API runs as a single process (HF Space / one VM),
so a shared store would add a dependency without adding protection. A restart
clears the counters, which is acceptable for throttling online guessing.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable

# Stop the dict growing without bound under a spray of unique keys.
_MAX_TRACKED_KEYS = 10_000


class LoginRateLimiter:
    """Allow at most `max_failures` failures per key inside `window_s` seconds."""

    def __init__(
        self, max_failures: int, window_s: float, clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max = max_failures
        self._window = window_s
        self._clock = clock
        self._failures: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float] | None:
        stamps = self._failures.get(key)
        if stamps is None:
            return None
        while stamps and now - stamps[0] >= self._window:
            stamps.popleft()
        if not stamps:
            del self._failures[key]
            return None
        return stamps

    def retry_after(self, key: str) -> int:
        """Seconds until `key` may try again; 0 when it is not locked out."""
        with self._lock:
            now = self._clock()
            stamps = self._prune(key, now)
            if stamps is None or len(stamps) < self._max:
                return 0
            return max(1, int(self._window - (now - stamps[0])) + 1)

    def record_failure(self, key: str) -> None:
        with self._lock:
            now = self._clock()
            if len(self._failures) >= _MAX_TRACKED_KEYS:
                for stale in list(self._failures):
                    self._prune(stale, now)
            self._failures.setdefault(key, deque()).append(now)

    def clear(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()


class LoginThrottle:
    """Per-account and per-client limits combined.

    Per-account stops guessing one password from many IPs; the looser per-IP
    limit stops one client spraying many accounts. The client IP is the socket
    peer — X-Forwarded-For is not trusted, so behind a shared proxy the per-IP
    limit degrades gracefully to a global cap and per-account remains the guard.
    """

    def __init__(self, per_email: LoginRateLimiter, per_ip: LoginRateLimiter) -> None:
        self._email = per_email
        self._ip = per_ip

    def retry_after(self, email: str, ip: str) -> int:
        return max(self._email.retry_after(email), self._ip.retry_after(ip))

    def record_failure(self, email: str, ip: str) -> None:
        self._email.record_failure(email)
        self._ip.record_failure(ip)

    def record_success(self, email: str) -> None:
        self._email.clear(email)

    def reset(self) -> None:
        self._email.reset()
        self._ip.reset()
