import re
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo


def utcnow() -> datetime:
    """Naive UTC (SQLite-friendly). Serialised with a Z suffix in schemas."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


_BD_PHONE = re.compile(r"^(?:\+?880|0)(1[3-9]\d{8})$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_phone(raw: str) -> str:
    s = re.sub(r"[\s\-()]", "", raw or "")
    m = _BD_PHONE.match(s)
    if not m:
        raise ValueError("Enter a valid Bangladesh mobile number (e.g. 01712345678)")
    return "+880" + m.group(1)


def normalize_email(raw: str) -> str:
    s = (raw or "").strip().lower()
    if not _EMAIL.match(s) or len(s) > 254:
        raise ValueError("Enter a valid email address")
    return s


def normalize_identifier(raw: str) -> str:
    """Login/OTP target: email if it contains '@', otherwise a phone number."""
    raw = (raw or "").strip()
    return normalize_email(raw) if "@" in raw else normalize_phone(raw)


def today_bd() -> date:
    """School runs on Bangladesh time (UTC+6); servers run on UTC."""
    return datetime.now(ZoneInfo("Asia/Dhaka")).date()
