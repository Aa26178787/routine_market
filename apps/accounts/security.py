import hashlib
import time

from django.conf import settings
from django.core.cache import cache


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _keys(request, identifier):
    ip_address = request.META.get("REMOTE_ADDR") or "unknown"
    normalized_identifier = (identifier or "").strip().lower()
    return (
        f"login-fail:ip:{_digest(ip_address)}",
        f"login-fail:account:{_digest(normalized_identifier)}",
    )


def _limits():
    return (
        int(getattr(settings, "LOGIN_FAILURE_LIMIT", 5)),
        int(getattr(settings, "LOGIN_FAILURE_WINDOW_SECONDS", 300)),
        int(getattr(settings, "LOGIN_LOCKOUT_SECONDS", 300)),
    )


def login_block_seconds(request, identifier):
    now = time.time()
    remaining = 0
    for key in _keys(request, identifier):
        state = cache.get(key) or {}
        blocked_until = float(state.get("blocked_until", 0))
        remaining = max(remaining, int(blocked_until - now + 0.999))
    return max(0, remaining)


def record_login_failure(request, identifier):
    limit, window_seconds, lockout_seconds = _limits()
    now = time.time()
    blocked_for = 0
    for key in _keys(request, identifier):
        state = cache.get(key) or {"count": 0, "first_at": now}
        if now - float(state.get("first_at", now)) > window_seconds:
            state = {"count": 0, "first_at": now}
        state["count"] = int(state.get("count", 0)) + 1
        if state["count"] >= limit:
            state["blocked_until"] = now + lockout_seconds
            blocked_for = lockout_seconds
        cache.set(key, state, max(window_seconds, lockout_seconds))
    return blocked_for


def clear_login_failures(request, identifier):
    cache.delete_many(_keys(request, identifier))
