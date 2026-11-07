"""SMS / email / push senders. Every sender degrades to logging so dev works with no providers."""
import json
import logging
import urllib.request

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import DeviceToken

log = logging.getLogger("aussnsc.notify")


def send_sms(phone: str, text: str) -> None:
    """Generic webhook: POST {"to","text"} to SMS_WEBHOOK_URL. Adapt the payload to your
    Bangladeshi SMS gateway (e.g. BulkSMSBD, SSL Wireless, Alpha SMS) here."""
    if not settings.sms_webhook_url:
        log.warning("[DEV SMS] to=%s text=%s", phone, text)
        return
    try:
        headers = {"Content-Type": "application/json"}
        if settings.sms_webhook_token:
            headers["Authorization"] = f"Bearer {settings.sms_webhook_token}"
        req = urllib.request.Request(settings.sms_webhook_url,
                                     data=json.dumps({"to": phone, "text": text}).encode(),
                                     headers=headers)
        urllib.request.urlopen(req, timeout=10).read()
    except Exception:
        log.exception("SMS delivery failed")


def send_email(to: str, subject: str, text: str) -> None:
    # TODO: plug in SMTP / SendGrid / Resend. Logged only for now.
    log.warning("[DEV EMAIL] to=%s subject=%s text=%s", to, subject, text)


def send_code(target: str, code: str, purpose: str) -> None:
    kind = "verification" if purpose == "verify" else "password reset"
    msg = f"Your AUSSNSC {kind} code is {code}. It expires in {settings.otp_minutes} minutes."
    if "@" in target:
        send_email(target, "AUSSNSC verification code", msg)
    else:
        send_sms(target, msg)


def push_to_users(db: Session, user_ids: list[int] | None, title: str, body: str) -> None:
    """Push via Firebase Admin if configured. user_ids=None -> all registered devices."""
    q = select(DeviceToken.token)
    if user_ids is not None:
        q = q.where(DeviceToken.user_id.in_(user_ids))
    tokens = list(db.scalars(q))
    if not tokens:
        return
    if not settings.firebase_credentials:
        log.info("[DEV PUSH] %s - %s (%d devices)", title, body, len(tokens))
        return
    try:
        import firebase_admin
        from firebase_admin import credentials, messaging
        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.Certificate(settings.firebase_credentials))
        for i in range(0, len(tokens), 500):
            messaging.send_each_for_multicast(messaging.MulticastMessage(
                tokens=tokens[i:i + 500], notification=messaging.Notification(title=title, body=body)))
    except Exception:
        log.exception("Push delivery failed (pip install firebase-admin to enable)")
