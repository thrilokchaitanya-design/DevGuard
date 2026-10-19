from collections import defaultdict, deque
from datetime import datetime, timezone
import secrets
from typing import Any
import uuid
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from app.config import settings

SESSION_COOKIE = "devguard_session"
CSRF_COOKIE = "devguard_csrf"
_serializer = URLSafeTimedSerializer(settings.session_secret or "local-development-session-secret-not-for-production", salt="devguard-demo-session-v1")


def issue_session() -> tuple[str, str]:
    csrf = secrets.token_urlsafe(32)
    now = int(datetime.now(timezone.utc).timestamp())
    token = _serializer.dumps({"sub": "shared-demo", "csrf": csrf, "iat": now, "jti": str(uuid.uuid4())})
    return token, csrf


def read_session(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    try:
        return _serializer.loads(token, max_age=settings.session_ttl_seconds)
    except (BadSignature, SignatureExpired):
        return None


class LoginRateLimit:
    """Small per-process login throttle. Production should also rate-limit at the edge."""
    def __init__(self, max_attempts: int = 8, window_seconds: int = 300):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.attempts: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, now: float) -> bool:
        bucket = self.attempts[key]
        while bucket and bucket[0] <= now - self.window_seconds:
            bucket.popleft()
        return len(bucket) < self.max_attempts

    def record(self, key: str, now: float) -> None:
        self.attempts[key].append(now)

login_limiter = LoginRateLimit()


def session_cookie_samesite() -> str:
    return settings.session_cookie_samesite.lower()


