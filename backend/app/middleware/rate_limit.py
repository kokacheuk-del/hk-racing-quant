"""
Simple in-memory rate limiter for Render free tier protection.

- Per-IP sliding window: max N requests per minute
- Health endpoint exempt
- Uses dict (no Redis needed for single-instance Render)
"""
import time
import logging
from collections import defaultdict
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("hkrq.rate_limit")

# ── Configuration ──
MAX_REQUESTS_PER_MINUTE = 30   # generous for normal use, blocks scrapers
MAX_REQUESTS_PER_HOUR = 300    # extra ceiling
WINDOW_SECONDS = 60
HOUR_SECONDS = 3600
CLEANUP_INTERVAL = 100         # clean stale IPs every N requests

# ── State ──
_ip_minute: dict[str, list[float]] = defaultdict(list)
_ip_hour: dict[str, list[float]] = defaultdict(list)
_request_count = 0


def _cleanup_stale(now: float):
    """Remove IPs with no recent activity to prevent memory leak."""
    stale_minute = [ip for ip, times in _ip_minute.items() if not times or now - times[-1] > HOUR_SECONDS]
    stale_hour = [ip for ip, times in _ip_hour.items() if not times or now - times[-1] > HOUR_SECONDS * 2]
    for ip in stale_minute:
        del _ip_minute[ip]
    for ip in stale_hour:
        del _ip_hour[ip]
    if stale_minute or stale_hour:
        logger.debug(f"Cleaned {len(stale_minute)} minute + {len(stale_hour)} hour stale IPs")


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        global _request_count

        # Exempt health checks (cron pings every 14 min)
        if request.url.path == "/health":
            return await call_next(request)

        # Exempt docs
        if request.url.path in ("/docs", "/redoc", "/openapi.json"):
            return await call_next(request)

        # Get client IP
        ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if not ip:
            ip = request.headers.get("x-real-ip", "")
        if not ip:
            ip = request.client.host if request.client else "unknown"

        now = time.time()

        # Periodic cleanup
        _request_count += 1
        if _request_count % CLEANUP_INTERVAL == 0:
            _cleanup_stale(now)

        # Sliding window: minute
        times_min = _ip_minute[ip]
        _ip_minute[ip] = [t for t in times_min if now - t < WINDOW_SECONDS]
        _ip_minute[ip].append(now)

        if len(_ip_minute[ip]) > MAX_REQUESTS_PER_MINUTE:
            logger.warning(f"Rate limited (minute) IP={ip}: {len(_ip_minute[ip])} req/min")
            return Response(
                content='{"detail":"Too many requests. Max 30/min."}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": "60"},
            )

        # Sliding window: hour
        times_hr = _ip_hour[ip]
        _ip_hour[ip] = [t for t in times_hr if now - t < HOUR_SECONDS]
        _ip_hour[ip].append(now)

        if len(_ip_hour[ip]) > MAX_REQUESTS_PER_HOUR:
            logger.warning(f"Rate limited (hour) IP={ip}: {len(_ip_hour[ip])} req/hr")
            return Response(
                content='{"detail":"Too many requests. Max 300/hr."}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": "3600"},
            )

        return await call_next(request)
