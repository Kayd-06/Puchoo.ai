"""Rate-limit policy behavior independent of HTTP routing."""

from backend.rate_limit import SlidingWindowLimiter


def test_auth_backoff_escalates_without_a_permanent_lockout(monkeypatch):
    now = [100.0]
    monkeypatch.setattr("backend.rate_limit.time.monotonic", lambda: now[0])
    limiter = SlidingWindowLimiter(limit=1, window_seconds=60, backoff_base_seconds=2, backoff_max_seconds=8)

    assert limiter.allow_with_backoff(["login:ip:203.0.113.1", "login:account:person@example.com"]) == (True, 0)
    assert limiter.allow_with_backoff(["login:ip:203.0.113.1", "login:account:person@example.com"]) == (False, 2)

    now[0] += 3
    assert limiter.allow_with_backoff(["login:ip:203.0.113.1", "login:account:person@example.com"]) == (False, 4)

    now[0] += 61
    assert limiter.allow_with_backoff(["login:ip:203.0.113.1", "login:account:person@example.com"])[0] is True


def test_backoff_resets_after_quiet_window(monkeypatch):
    now = [100.0]
    monkeypatch.setattr("backend.rate_limit.time.monotonic", lambda: now[0])
    limiter = SlidingWindowLimiter(limit=1, window_seconds=60, backoff_base_seconds=2, backoff_max_seconds=8)

    # 1. First hit allowed
    assert limiter.allow_with_backoff(["key1"]) == (True, 0)
    # 2. Blocked -> level 0 (2s)
    assert limiter.allow_with_backoff(["key1"]) == (False, 2)

    now[0] += 3
    # 3. Blocked -> level 1 (4s). Block expires at now[0] + 4.
    assert limiter.allow_with_backoff(["key1"]) == (False, 4)

    # Wait for quiet window (60s) beyond the block expiration.
    # Block expiration was at now[0] + 4, so we wait 4 + 61 seconds.
    now[0] += 65

    # This hit is allowed (it's been > 60s since any hit, so limit of 1 is cleared)
    assert limiter.allow_with_backoff(["key1"]) == (True, 0)

    # The next hit should be blocked, but the penalty should reset to level 0 (2s), not level 2 (8s)
    assert limiter.allow_with_backoff(["key1"]) == (False, 2)
