"""Fixed-window counters for login and signup. In-memory for the local server."""

import threading
import time
from collections import defaultdict

from backend.config import settings


class SlidingWindowLimiter:
    def __init__(
        self,
        limit: int = 5,
        window_seconds: int = 15 * 60,
        *,
        backoff_base_seconds: int = 0,
        backoff_max_seconds: int = 0,
    ) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.backoff_base_seconds = backoff_base_seconds
        self.backoff_max_seconds = backoff_max_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._blocked_until: dict[str, float] = {}
        self._backoff_levels: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
            self._blocked_until.clear()
            self._backoff_levels.clear()

    def allow(self, keys: list[str]) -> bool:
        """Record one attempt against every key, or reject if any key is already full."""

        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            pruned: dict[str, list[float]] = {}
            for key in keys:
                recent = [stamp for stamp in self._hits[key] if stamp > cutoff]
                pruned[key] = recent
                if len(recent) >= self.limit:
                    self._hits[key] = recent
                    return False
            for key, recent in pruned.items():
                recent.append(now)
                self._hits[key] = recent
            return True

    def allow_with_backoff(self, keys: list[str]) -> tuple[bool, int]:
        """Apply temporary exponential backoff after a configured rate limit.

        The caller supplies both an IP key and an account key, so rotating one
        identifier cannot bypass the other. A key becomes eligible again after
        the returned delay; it is never permanently locked.
        """

        if self.backoff_base_seconds <= 0 or self.backoff_max_seconds <= 0:
            return self.allow(keys), 0
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            retry_after = 0
            for key in keys:
                blocked_until = self._blocked_until.get(key, 0)
                if blocked_until > now:
                    retry_after = max(retry_after, int(blocked_until - now) + 1)
            if retry_after:
                return False, retry_after

            recent_by_key: dict[str, list[float]] = {}
            exceeded: list[str] = []
            for key in keys:
                recent = [stamp for stamp in self._hits[key] if stamp > cutoff]
                recent_by_key[key] = recent
                if len(recent) >= self.limit:
                    exceeded.append(key)
            if exceeded:
                for key in exceeded:
                    level = self._backoff_levels[key]
                    # Start over once the key has stayed quiet for a full window after its last block.
                    if now - self._blocked_until.get(key, now) > self.window_seconds:
                        level = 0
                    delay = min(self.backoff_base_seconds * (2**level), self.backoff_max_seconds)
                    self._backoff_levels[key] = level + 1
                    self._blocked_until[key] = now + delay
                    self._hits[key] = recent_by_key[key]
                    retry_after = max(retry_after, delay)
                return False, retry_after

            for key, recent in recent_by_key.items():
                recent.append(now)
                self._hits[key] = recent
            return True, 0


limiter = SlidingWindowLimiter(
    limit=settings.auth_rate_limit,
    window_seconds=settings.auth_rate_window_seconds,
    backoff_base_seconds=settings.auth_backoff_base_seconds,
    backoff_max_seconds=settings.auth_backoff_max_seconds,
)
# Connection probes are expensive and can be aimed at internal networks.
connection_limiter = SlidingWindowLimiter(
    limit=settings.connection_rate_limit,
    window_seconds=settings.connection_rate_window_seconds,
)
public_limiter = SlidingWindowLimiter(
    limit=settings.public_rate_limit,
    window_seconds=settings.public_rate_window_seconds,
)
authenticated_limiter = SlidingWindowLimiter(
    limit=settings.authenticated_rate_limit,
    window_seconds=settings.authenticated_rate_window_seconds,
)
