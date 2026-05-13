"""
timezone_utils.py — Dynamic timezone detection via IP
Falls back gracefully when offline or API is unreachable.

Priority:
  1. Cached value (in-memory, then ~/.taskflow_tz file)
  2. ipinfo.io API (same one used for weather city)
  3. System local timezone (via datetime.astimezone())
  4. Hard fallback: UTC

Usage anywhere in the app:
    from timezone_utils import get_tz, now_local, today_local
    tz   = get_tz()                          # ZoneInfo object
    now  = now_local()                       # timezone-aware datetime (local tz)
    today = today_local()                    # date object in local tz
    label = tz_label()                       # e.g. "Asia/Kolkata (IST, UTC+5:30)"
"""

import os
import threading
from datetime import datetime, date, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# ── Cache paths ───────────────────────────────────────────────────────────────
_TZ_CACHE_FILE = os.path.join(os.path.expanduser("~"), ".taskflow_tz")
_IPINFO_URL    = "https://ipinfo.io/json"
_TIMEOUT       = 3          # seconds — fast, non-blocking feel
_REFRESH_DAYS  = 7          # re-detect after this many days (travel etc.)

# ── In-process singleton ──────────────────────────────────────────────────────
_cached_tz: ZoneInfo | None = None
_lock = threading.Lock()


# ── Public API ────────────────────────────────────────────────────────────────

def get_tz() -> ZoneInfo:
    """Return the best available ZoneInfo for this user. Never raises."""
    global _cached_tz
    if _cached_tz is not None:
        return _cached_tz
    with _lock:
        if _cached_tz is not None:   # double-check after acquiring lock
            return _cached_tz
        _cached_tz = _resolve_tz()
        return _cached_tz


def now_local() -> datetime:
    """Current datetime in user's local timezone (timezone-aware)."""
    return datetime.now(tz=get_tz())


def today_local() -> date:
    """Current date in user's local timezone."""
    return now_local().date()


def tz_label() -> str:
    """Human-readable label, e.g. 'Asia/Kolkata (IST, UTC+5:30)'"""
    tz  = get_tz()
    now = datetime.now(tz=tz)
    abbr   = now.strftime("%Z")                        # IST, EST, etc.
    offset = now.strftime("%z")                        # +0530
    sign   = offset[0]
    h, m   = offset[1:3], offset[3:5]
    utc    = f"UTC{sign}{int(h)}:{m}" if m != "00" else f"UTC{sign}{int(h)}"
    return f"{tz.key} ({abbr}, {utc})"


def refresh_tz():
    """Force a fresh IP lookup (e.g. after user changes network). Runs in background."""
    global _cached_tz
    _cached_tz = None
    _delete_cache_file()
    threading.Thread(target=get_tz, daemon=True).start()


# ── Resolution chain ──────────────────────────────────────────────────────────

def _resolve_tz() -> ZoneInfo:
    # Step 1 — file cache (skip if stale)
    tz = _load_from_file()
    if tz:
        return tz

    # Step 2 — IP API
    tz = _detect_from_ip()
    if tz:
        _save_to_file(tz.key)
        return tz

    # Step 3 — system local timezone
    tz = _system_tz()
    if tz:
        return tz

    # Step 4 — absolute fallback.
    # ZoneInfo("UTC") requires the tzdata package on Windows; if it's missing
    # we fall back to stdlib timezone.utc which needs no external package and
    # is accepted by datetime.now(tz=...) just as well.
    try:
        return ZoneInfo("UTC")
    except Exception:
        return timezone.utc  # type: ignore[return-value]


# ── IP detection ──────────────────────────────────────────────────────────────

def _detect_from_ip() -> ZoneInfo | None:
    """
    Calls ipinfo.io/json — same endpoint used for weather city.
    Returns a ZoneInfo or None if offline / unreachable.
    """
    try:
        import requests
        resp = requests.get(_IPINFO_URL, timeout=_TIMEOUT)
        if resp.status_code != 200:
            return None
        data    = resp.json()
        tz_name = data.get("timezone", "").strip()
        if not tz_name:
            return None
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        return None
    except Exception:
        # Offline, DNS failure, timeout, JSON error — all silently handled
        return None


# ── System timezone fallback ──────────────────────────────────────────────────

def _system_tz() -> ZoneInfo | None:
    """
    Use Python's datetime to figure out the OS-configured UTC offset,
    then find a matching ZoneInfo key.
    Not perfect (same offset = same zone assumed) but fine as a fallback.
    """
    try:
        local_dt = datetime.now().astimezone()
        offset   = local_dt.utcoffset()
        if offset is None:
            return None

        # Try to get IANA name directly (works on Linux/macOS, sometimes Windows)
        tz_name = local_dt.tzname()
        if tz_name and "/" in tz_name:   # looks like an IANA name (e.g. Asia/Kolkata)
            try:
                return ZoneInfo(tz_name)
            except ZoneInfoNotFoundError:
                pass

        # Fallback: map UTC offset → a canonical IANA zone
        # Covers the most common zones; good enough for productivity app
        offset_hours = offset.total_seconds() / 3600
        _OFFSET_MAP = {
            5.5:  "Asia/Kolkata",
            5.75: "Asia/Kathmandu",
            6.0:  "Asia/Dhaka",
            6.5:  "Asia/Yangon",
            7.0:  "Asia/Bangkok",
            8.0:  "Asia/Singapore",
            9.0:  "Asia/Tokyo",
            9.5:  "Australia/Darwin",
            10.0: "Australia/Sydney",
            3.5:  "Asia/Tehran",
            4.0:  "Asia/Dubai",
            4.5:  "Asia/Kabul",
            3.0:  "Europe/Moscow",
            2.0:  "Europe/Athens",
            1.0:  "Europe/Paris",
            0.0:  "Europe/London",
            -5.0: "America/New_York",
            -6.0: "America/Chicago",
            -7.0: "America/Denver",
            -8.0: "America/Los_Angeles",
        }
        iana = _OFFSET_MAP.get(offset_hours)
        if iana:
            try:
                return ZoneInfo(iana)
            except Exception:
                pass  # tzdata not installed — continue to fixed-offset fallback

        # Build a fixed-offset zone as last resort
        fixed = timezone(offset)
        total_min = int(offset.total_seconds() / 60)
        sign  = "+" if total_min >= 0 else "-"
        h, m  = divmod(abs(total_min), 60)
        name  = f"Etc/GMT{sign}{h}" if m == 0 else None
        if name:
            try:
                return ZoneInfo(name)
            except ZoneInfoNotFoundError:
                pass

        return None
    except Exception:
        return None


# ── File cache ────────────────────────────────────────────────────────────────

def _load_from_file() -> ZoneInfo | None:
    try:
        if not os.path.exists(_TZ_CACHE_FILE):
            return None
        # Check age — refresh after _REFRESH_DAYS
        age_days = (datetime.now().timestamp() - os.path.getmtime(_TZ_CACHE_FILE)) / 86400
        if age_days > _REFRESH_DAYS:
            return None
        with open(_TZ_CACHE_FILE) as f:
            tz_name = f.read().strip()
        return ZoneInfo(tz_name) if tz_name else None
    except Exception:
        return None


def _save_to_file(tz_name: str):
    try:
        with open(_TZ_CACHE_FILE, "w") as f:
            f.write(tz_name)
    except Exception:
        pass


def _delete_cache_file():
    try:
        if os.path.exists(_TZ_CACHE_FILE):
            os.remove(_TZ_CACHE_FILE)
    except Exception:
        pass
