"""Fixed-window counters for login and signup. In-memory for the local server."""

import threading
import time
from collections import defaultdict


class SlidingWindowLimiter:
    def __init__(self, limit: int = 5, window_seconds: int = 15 * 60) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

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


limiter = SlidingWindowLimiter()
