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
