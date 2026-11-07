import secrets
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import current_user, user_from_token
from ..models import OTP, DeviceToken, User
from ..notifications import send_code
from ..schemas import (DeviceIn, GoogleLoginIn, LoginIn, Msg, OtpRequestIn, OtpVerifyIn, PasswordChangeIn,
                       PasswordResetIn, ProfileUpdateIn, RefreshIn, RegisterIn, TokenOut, UserOut)
from ..security import (DUMMY_HASH, client_ip, create_token, hash_otp, hash_password, limiter,
                        verify_password)
from ..utils import normalize_identifier, utcnow

router = APIRouter(tags=["Auth & account"])


def _tokens(user: User) -> TokenOut:
    return TokenOut(access_token=create_token(user.id, "access", user.token_version),
                    refresh_token=create_token(user.id, "refresh", user.token_version),
                    user=UserOut.model_validate(user))


def _norm(target: str) -> str:
    try:
        return normalize_identifier(target)
    except ValueError as e:
        raise HTTPException(422, str(e))


def _find_user(db: Session, ident: str) -> User | None:
    col = User.email if "@" in ident else User.phone
    return db.scalar(select(User).where(col == ident))


def _issue_otp(db: Session, target: str, purpose: str, bg: BackgroundTasks) -> None:
    code = f"{secrets.randbelow(10**6):06d}"
    db.add(OTP(target=target, purpose=purpose, code_hash=hash_otp(target, code),
               expires_at=utcnow() + timedelta(minutes=settings.otp_minutes)))
    db.commit()
    bg.add_task(send_code, target, code, purpose)


def _check_otp(db: Session, target: str, purpose: str, code: str) -> None:
    otp = db.scalar(select(OTP).where(OTP.target == target, OTP.purpose == purpose, OTP.used.is_(False),
                                      OTP.expires_at > utcnow()).order_by(OTP.id.desc()))
    bad = HTTPException(400, "Invalid or expired code")
    if not otp or otp.attempts >= 5:
        raise bad
    otp.attempts += 1
    if otp.code_hash != hash_otp(target, code):
        db.commit()
        raise bad
    otp.used = True
    db.commit()


@router.post("/auth/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn, request: Request, bg: BackgroundTasks, db: Session = Depends(get_db)):
    """Anyone can create a basic ('public') account. The school admin later upgrades the role
    (student/parent/teacher) after verifying the person - that is what unlocks academic data."""
    limiter.check(f"reg:{client_ip(request)}", 10, 3600)
    clauses = []
    if body.phone:
        clauses.append(User.phone == body.phone)
    if body.email:
        clauses.append(User.email == body.email)
    if db.scalar(select(User.id).where(or_(*clauses))):
        raise HTTPException(409, "An account with this phone number or email already exists")
    user = User(full_name=body.full_name.strip(), phone=body.phone, email=body.email,
                password_hash=hash_password(body.password), language=body.language)
    db.add(user)
    db.commit()
    for target in (body.phone, body.email):
        if target:
            _issue_otp(db, target, "verify", bg)
    return _tokens(user)


@router.post("/auth/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    ident = _norm(body.identifier)
    limiter.check(f"login:{client_ip(request)}:{ident}", 8, 600)
    user = _find_user(db, ident)
    ok = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
    if not user or not ok:
        raise HTTPException(401, "Incorrect phone/email or password")
    if not user.is_active:
        raise HTTPException(403, "This account has been disabled. Please contact the school office.")
    return _tokens(user)


@router.post("/auth/google", response_model=TokenOut)
def google_login(body: GoogleLoginIn, request: Request, db: Session = Depends(get_db)):
    """Sign in / sign up with Google through Firebase. The app sends the Firebase ID token;
    we verify it against Google's public keys and our Firebase project id."""
    limiter.check(f"google:{client_ip(request)}", 20, 600)
    if not settings.firebase_project_id:
        raise HTTPException(503, "Google sign-in is not configured on the server (FIREBASE_PROJECT_ID)")
    try:
        from google.auth.transport import requests as g_requests
        from google.oauth2 import id_token as g_id_token
        claims = g_id_token.verify_firebase_token(body.id_token, g_requests.Request(),
                                                  audience=settings.firebase_project_id)
    except Exception:
        raise HTTPException(401, "Google sign-in could not be verified. Please try again.")
    if not claims or not claims.get("sub"):
        raise HTTPException(401, "Google sign-in could not be verified. Please try again.")
    email = (claims.get("email") or "").lower() or None
    if not email or not claims.get("email_verified"):
        raise HTTPException(403, "Your Google email is not verified")
    uid = claims["sub"]
    user = db.scalar(select(User).where(User.google_uid == uid)) or db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(full_name=(claims.get("name") or email.split("@")[0])[:120], email=email, email_verified=True,
                    password_hash=hash_password(secrets.token_urlsafe(32)), google_uid=uid)
        db.add(user)
    else:
        if not user.is_active:
            raise HTTPException(403, "This account has been disabled. Please contact the school office.")
        user.google_uid = user.google_uid or uid
        user.email_verified = True
    db.commit()
    return _tokens(user)


@router.post("/auth/refresh", response_model=TokenOut)
def refresh(body: RefreshIn, db: Session = Depends(get_db)):
    user = user_from_token(body.refresh_token, db, "refresh")
    if not user:
        raise HTTPException(401, "Session expired. Please sign in again.")
    return _tokens(user)


@router.post("/auth/logout-all", response_model=Msg)
def logout_all(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Invalidates every access/refresh token issued so far for this account."""
    user.token_version += 1
    db.commit()
    return Msg(detail="Signed out everywhere")


@router.post("/auth/otp/request", response_model=Msg)
def otp_request(body: OtpRequestIn, request: Request, bg: BackgroundTasks, db: Session = Depends(get_db)):
    target = _norm(body.target)
    limiter.check(f"otp:{client_ip(request)}", 10, 3600)
    limiter.check(f"otp:{target}", 3, 600)
    user = _find_user(db, target)
    if user:  # same response either way - don't reveal which numbers/emails have accounts
        _issue_otp(db, target, body.purpose, bg)
    return Msg(detail="If the account exists, a code has been sent")


@router.post("/auth/otp/verify", response_model=Msg)
def otp_verify(body: OtpVerifyIn, request: Request, db: Session = Depends(get_db)):
    target = _norm(body.target)
    limiter.check(f"otpv:{client_ip(request)}", 20, 600)
    _check_otp(db, target, "verify", body.code)
    user = _find_user(db, target)
    if not user:
        raise HTTPException(400, "Invalid or expired code")
    if "@" in target:
        user.email_verified = True
    else:
        user.phone_verified = True
    db.commit()
    return Msg(detail="Verified")


@router.post("/auth/password/reset", response_model=Msg)
def password_reset(body: PasswordResetIn, request: Request, db: Session = Depends(get_db)):
    target = _norm(body.target)
    limiter.check(f"pwr:{client_ip(request)}", 10, 600)
    _check_otp(db, target, "reset", body.code)
    user = _find_user(db, target)
    if not user:
        raise HTTPException(400, "Invalid or expired code")
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1
    db.commit()
    return Msg(detail="Password updated. Please sign in.")


# ───────────── current user ─────────────

@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.patch("/me", response_model=UserOut)
def update_me(body: ProfileUpdateIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    for k, v in body.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(user, k, v.strip() if isinstance(v, str) else v)
    db.commit()
    return user


@router.post("/me/password", response_model=TokenOut)
def change_password(body: PasswordChangeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1  # signs out other devices; returns fresh tokens for this one
    db.commit()
    return _tokens(user)


@router.post("/me/devices", response_model=Msg, status_code=201)
def register_device(body: DeviceIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    existing = db.scalar(select(DeviceToken).where(DeviceToken.token == body.token))
    if existing:
        existing.user_id, existing.platform = user.id, body.platform
    else:
        db.add(DeviceToken(user_id=user.id, token=body.token, platform=body.platform))
    db.commit()
    return Msg(detail="Device registered for notifications")


@router.delete("/me/devices/{token}", response_model=Msg)
def unregister_device(token: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = db.scalar(select(DeviceToken).where(DeviceToken.token == token, DeviceToken.user_id == user.id))
    if d:
        db.delete(d)
        db.commit()
    return Msg(detail="Device removed")
