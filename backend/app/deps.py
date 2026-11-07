from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import (AuditLog, ParentLink, StudentProfile, TeacherClass, TeacherProfile, User)
from .security import decode_token

bearer = HTTPBearer(auto_error=False)


def user_from_token(token: str, db: Session, kind: str = "access") -> User | None:
    try:
        payload = decode_token(token, kind)
        user = db.get(User, int(payload["sub"]))
    except (ValueError, KeyError):
        return None
    if not user or not user.is_active or user.token_version != payload.get("ver"):
        return None
    return user


def current_user_optional(creds: HTTPAuthorizationCredentials | None = Depends(bearer),
                          db: Session = Depends(get_db)) -> User | None:
    return user_from_token(creds.credentials, db) if creds else None


def current_user(user: User | None = Depends(current_user_optional)) -> User:
    if not user:
        raise HTTPException(401, "Please sign in", headers={"WWW-Authenticate": "Bearer"})
    return user


def require_roles(*roles: str):
    """Dependency factory. Admin passes every check. 'public' accounts are never academic."""
    allowed = set(roles) | {"admin"}

    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(403, "Your account does not have access to this. "
                                     "Academic access requires verification by the school.")
        return user
    return dep


def get_or_404(db: Session, model, ident, what: str = "Item"):
    obj = db.get(model, ident)
    if obj is None:
        raise HTTPException(404, f"{what} not found")
    return obj


def audit(db: Session, actor: User | None, action: str, entity: str,
          entity_id=None, detail: str | None = None) -> None:
    db.add(AuditLog(actor_id=actor.id if actor else None, action=action, entity=entity,
                    entity_id=str(entity_id) if entity_id is not None else None, detail=detail))


# ───────────── who-can-see-what helpers ─────────────

def student_profile_of(db: Session, user: User) -> StudentProfile | None:
    return db.scalar(select(StudentProfile).where(StudentProfile.user_id == user.id))


def teacher_profile_of(db: Session, user: User) -> TeacherProfile | None:
    return db.scalar(select(TeacherProfile).where(TeacherProfile.user_id == user.id))


def teacher_class_ids(db: Session, user: User) -> set[int]:
    tp = teacher_profile_of(db, user)
    if not tp:
        return set()
    return set(db.scalars(select(TeacherClass.class_id).where(TeacherClass.teacher_id == tp.id)))


def approved_child_ids(db: Session, user: User) -> set[int]:
    return set(db.scalars(select(ParentLink.student_id).where(
        ParentLink.parent_id == user.id, ParentLink.status == "approved",
        ParentLink.student_id.is_not(None))))


def can_manage_class(db: Session, user: User, class_id: int) -> bool:
    if user.role == "admin":
        return True
    return user.role == "teacher" and class_id in teacher_class_ids(db, user)


def can_view_student(db: Session, user: User, student: StudentProfile) -> bool:
    if user.role == "admin":
        return True
    if user.role == "student":
        return student.user_id == user.id
    if user.role == "parent":
        return student.id in approved_child_ids(db, user)
    if user.role == "teacher":
        return student.class_id in teacher_class_ids(db, user)
    return False


def visible_class_ids(db: Session, user: User) -> set[int] | None:
    """Classes whose content the user may read. None means 'all' (admin)."""
    if user.role == "admin":
        return None
    if user.role == "teacher":
        return teacher_class_ids(db, user)
    if user.role == "student":
        sp = student_profile_of(db, user)
        return {sp.class_id} if sp else set()
    if user.role == "parent":
        ids = approved_child_ids(db, user)
        if not ids:
            return set()
        return set(db.scalars(select(StudentProfile.class_id).where(StudentProfile.id.in_(ids))))
    return set()
