import logging
import os
import secrets
from pathlib import Path

log = logging.getLogger("aussnsc")


def _flag(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


class Settings:
    env = os.getenv("ENV", "development")
    is_prod = env == "production"

    database_url = os.getenv("DATABASE_URL", "sqlite:///./aussnsc.db")
    if database_url.startswith("postgres://"):  # Heroku/Render style
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    secret_key = os.getenv("SECRET_KEY", "")
    if not secret_key:
        if is_prod:
            raise RuntimeError("SECRET_KEY must be set when ENV=production")
        secret_key = secrets.token_urlsafe(48)
        log.warning("SECRET_KEY not set - using a temporary key; logins reset on restart")

    access_minutes = int(os.getenv("ACCESS_TOKEN_MINUTES", "60"))
    refresh_days = int(os.getenv("REFRESH_TOKEN_DAYS", "30"))
    otp_minutes = 10

    cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
    trust_proxy = _flag("TRUST_PROXY")

    upload_dir = Path(os.getenv("UPLOAD_DIR", "./uploads"))
    max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "10"))
    allowed_ext = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".doc", ".docx",
                   ".ppt", ".pptx", ".xls", ".xlsx", ".txt", ".mp4"}

    admin_name = os.getenv("ADMIN_NAME", "School Admin")
    admin_phone = os.getenv("ADMIN_PHONE", "")
    admin_email = os.getenv("ADMIN_EMAIL", "")
    admin_password = os.getenv("ADMIN_PASSWORD", "")
    seed_demo = _flag("SEED_DEMO", not is_prod)
    reset_admin = _flag("RESET_ADMIN")   # set to 1 for one deploy to reset the admin password to ADMIN_PASSWORD

    sms_webhook_url = os.getenv("SMS_WEBHOOK_URL", "")
    sms_webhook_token = os.getenv("SMS_WEBHOOK_TOKEN", "")
    firebase_credentials = os.getenv("FIREBASE_CREDENTIALS", "")
    firebase_project_id = os.getenv("FIREBASE_PROJECT_ID", "")
    enable_docs = _flag("ENABLE_DOCS", not is_prod)


settings = Settings()
settings.upload_dir.mkdir(parents=True, exist_ok=True)
