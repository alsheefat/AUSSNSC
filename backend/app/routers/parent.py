from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import audit, current_user, require_roles
from ..models import ParentLink, SchoolClass, StudentProfile, User
from ..schemas import ParentLinkIn, ParentLinkOut, StudentOut

router = APIRouter(prefix="/parent", tags=["Parent portal"])


def match_student(db: Session, name: str, class_name: str, roll: int) -> StudentProfile | None:
    """Auto-match a claim to a student: same roll, class name (e.g. '10' or '10-A'), same name."""
    cls = class_name.strip()
    stmt = select(StudentProfile).join(SchoolClass, SchoolClass.id == StudentProfile.class_id).where(
        StudentProfile.roll == roll, func.lower(StudentProfile.full_name) == name.strip().lower())
    for st in db.scalars(stmt).unique():
        c = st.school_class
        if cls.lower() in (c.name.lower(), f"{c.name}-{c.section}".lower(), f"{c.name} {c.section}".lower()):
            return st
    return None


@router.post("/links", response_model=ParentLinkOut, status_code=201)
def request_link(body: ParentLinkIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Any signed-in account may *request* a link; nothing is visible until an admin approves it."""
    if user.role not in ("public", "parent"):
        raise HTTPException(403, "Only parent/guardian accounts can link a child")
    st = match_student(db, body.student_name, body.class_name, body.roll)
    pending = db.scalar(select(func.count(ParentLink.id)).where(ParentLink.parent_id == user.id, ParentLink.status == "pending"))
    if pending >= 5:
        raise HTTPException(429, "You already have several pending requests. Please wait for the school to review them.")
    if st and db.scalar(select(ParentLink.id).where(ParentLink.parent_id == user.id, ParentLink.student_id == st.id,
                                                    ParentLink.status.in_(("pending", "approved")))):
        raise HTTPException(409, "You already requested or have access to this child")
    link = ParentLink(parent_id=user.id, student_id=st.id if st else None, claimed_name=body.student_name.strip(),
                      claimed_class=body.class_name.strip(), claimed_roll=body.roll, relationship_=body.relationship.strip())
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


@router.get("/links", response_model=list[ParentLinkOut])
def my_links(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.scalars(select(ParentLink).where(ParentLink.parent_id == user.id).order_by(ParentLink.id.desc())).unique().all()


@router.get("/children", response_model=list[StudentOut])
def children(user: User = Depends(require_roles("parent")), db: Session = Depends(get_db)):
    ids = select(ParentLink.student_id).where(ParentLink.parent_id == user.id, ParentLink.status == "approved",
                                              ParentLink.student_id.is_not(None))
    return db.scalars(select(StudentProfile).where(StudentProfile.id.in_(ids)).order_by(StudentProfile.full_name)).unique().all()
