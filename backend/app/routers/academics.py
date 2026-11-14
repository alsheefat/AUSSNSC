"""Attendance, results (own), assignments, submissions, materials, uploads - role aware."""
import secrets
from datetime import date, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import (approved_child_ids, audit, can_manage_class, can_view_student, current_user,
                    get_or_404, require_roles, student_profile_of, teacher_class_ids,
                    teacher_profile_of, visible_class_ids)
from ..models import (Assignment, Attendance, ExamResult, Material, SchoolClass, StudentProfile,
                      Submission, TeacherClass, User)
from ..notifications import push_to_users
from ..schemas import (AssignmentIn, AssignmentOut, AttendanceDay, AttendanceIn, AttendanceSummary,
                       MaterialIn, MaterialOut, Msg, ResultOut, ReviewIn, StudentOut, SubmissionIn,
                       SubmissionOut, TeacherClassOut)
from ..utils import today_bd, utcnow

router = APIRouter(tags=["Academics"])
academic = require_roles("student", "parent", "teacher")
staff = require_roles("teacher")


# ───────────── uploads ─────────────

@router.post("/uploads", tags=["Uploads"])
async def upload(file: UploadFile = File(...), user: User = Depends(require_roles("student", "teacher"))):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in settings.allowed_ext:
        raise HTTPException(400, f"File type not allowed. Allowed: {', '.join(sorted(settings.allowed_ext))}")
    name = f"{secrets.token_hex(16)}{ext}"
    dest = settings.upload_dir / name
    limit, size = settings.max_upload_mb * 1024 * 1024, 0
    too_big = False
    with dest.open("wb") as f:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                too_big = True
                break
            f.write(chunk)
    if too_big:
        dest.unlink(missing_ok=True)
        raise HTTPException(413, f"File is larger than {settings.max_upload_mb} MB")
    return {"url": f"/uploads/{name}", "filename": file.filename, "size": size}


# ───────────── teacher helpers ─────────────

@router.get("/teacher/classes", response_model=list[TeacherClassOut])
def my_classes(user: User = Depends(staff), db: Session = Depends(get_db)):
    tp = teacher_profile_of(db, user)
    if not tp:
        return []
    return db.scalars(select(TeacherClass).where(TeacherClass.teacher_id == tp.id)).unique().all()


@router.get("/classes/{class_id}/students", response_model=list[StudentOut])
def roster(class_id: int, user: User = Depends(staff), db: Session = Depends(get_db)):
    if not can_manage_class(db, user, class_id):
        raise HTTPException(403, "You are not assigned to this class")
    return db.scalars(select(StudentProfile).where(StudentProfile.class_id == class_id)
                      .order_by(StudentProfile.roll)).unique().all()


# ───────────── attendance ─────────────

@router.post("/attendance", response_model=Msg)
def mark_attendance(body: AttendanceIn, user: User = Depends(staff), db: Session = Depends(get_db)):
    if not can_manage_class(db, user, body.class_id):
        raise HTTPException(403, "You are not assigned to this class")
    if body.day > today_bd():
        raise HTTPException(422, "Cannot mark attendance for a future date")
    roster_ids = set(db.scalars(select(StudentProfile.id).where(StudentProfile.class_id == body.class_id)))
    ids = [r.student_id for r in body.records]
    if len(set(ids)) != len(ids):
        raise HTTPException(422, "Duplicate students in the list")
    if not set(ids) <= roster_ids:
        raise HTTPException(422, "Some students do not belong to this class")
    existing = {a.student_id: a for a in db.scalars(
        select(Attendance).where(Attendance.day == body.day, Attendance.student_id.in_(ids)))}
    for r in body.records:
        if r.student_id in existing:
            existing[r.student_id].status = r.status
            existing[r.student_id].marked_by = user.id
        else:
            db.add(Attendance(student_id=r.student_id, day=body.day, status=r.status, marked_by=user.id))
    audit(db, user, "attendance.mark", "class", body.class_id, f"{body.day} · {len(ids)} students")
    db.commit()
    return Msg(detail=f"Attendance saved for {len(ids)} students")


@router.get("/classes/{class_id}/attendance", response_model=list[AttendanceDay])
def class_attendance(class_id: int, day: date, user: User = Depends(staff), db: Session = Depends(get_db)):
    """Existing records for a date (used to pre-fill the roster screen)."""
    if not can_manage_class(db, user, class_id):
        raise HTTPException(403, "You are not assigned to this class")
    return db.scalars(select(Attendance).join(StudentProfile, StudentProfile.id == Attendance.student_id)
                      .where(StudentProfile.class_id == class_id, Attendance.day == day)).all()


def _summary(db: Session, student_id: int, start: date | None, end: date | None) -> AttendanceSummary:
    stmt = select(Attendance).where(Attendance.student_id == student_id)
    if start:
        stmt = stmt.where(Attendance.day >= start)
    if end:
        stmt = stmt.where(Attendance.day <= end)
    rows = db.scalars(stmt.order_by(Attendance.day.desc())).all()
    p = sum(r.status == "present" for r in rows)
    a = sum(r.status == "absent" for r in rows)
    l = sum(r.status == "late" for r in rows)
    total = len(rows)
    # attendance rate counts "late" as attended
    rate = round((p + l) * 100 / total, 1) if total else 0.0
    return AttendanceSummary(present=p, absent=a, late=l, total_days=total, rate_percent=rate,
                             records=[AttendanceDay.model_validate(r) for r in rows])


def _range(month: str | None, start: date | None, end: date | None):
    if month:
        try:
            y, m = map(int, month.split("-"))
            first = date(y, m, 1)
        except ValueError:
            raise HTTPException(422, "month must be YYYY-MM")
        nxt = date(y + (m == 12), (m % 12) + 1, 1)
        return first, nxt - timedelta(days=1)
    return start, end


def _own_student(db: Session, user: User) -> StudentProfile:
    sp = student_profile_of(db, user)
    if not sp:
        raise HTTPException(404, "No student record is linked to your account yet. Please contact the school office.")
    return sp


@router.get("/me/student", response_model=StudentOut)
def my_student(user: User = Depends(require_roles("student")), db: Session = Depends(get_db)):
    return _own_student(db, user)


@router.get("/me/attendance", response_model=AttendanceSummary)
def my_attendance(month: str | None = None, start: date | None = None, end: date | None = None,
                  user: User = Depends(require_roles("student")), db: Session = Depends(get_db)):
    s, e = _range(month, start, end)
    return _summary(db, _own_student(db, user).id, s, e)


@router.get("/students/{student_id}/attendance", response_model=AttendanceSummary)
def student_attendance(student_id: int, month: str | None = None, start: date | None = None,
                       end: date | None = None, user: User = Depends(academic), db: Session = Depends(get_db)):
    st = get_or_404(db, StudentProfile, student_id, "Student")
    if not can_view_student(db, user, st):
        raise HTTPException(403, "You cannot view this student's records")
    s, e = _range(month, start, end)
    return _summary(db, st.id, s, e)


# ───────────── own results (published only) ─────────────

@router.get("/students/{student_id}/results", response_model=list[ResultOut])
def student_results(student_id: int, user: User = Depends(academic), db: Session = Depends(get_db)):
    st = get_or_404(db, StudentProfile, student_id, "Student")
    if not can_view_student(db, user, st):
        raise HTTPException(403, "You cannot view this student's records")
    rows = db.scalars(select(ExamResult).where(ExamResult.student_id == st.id, ExamResult.published.is_(True))
                      .order_by(ExamResult.exam_year.desc())).all()
    return [ResultOut.of(r) for r in rows]


@router.get("/me/results", response_model=list[ResultOut])
def my_results(user: User = Depends(require_roles("student")), db: Session = Depends(get_db)):
    return student_results(_own_student(db, user).id, user, db)


# ───────────── assignments ─────────────

def _decorate(db: Session, rows: list[Assignment], student_id: int | None) -> list[AssignmentOut]:
    status = {}
    if student_id and rows:
        for s in db.scalars(select(Submission).where(Submission.student_id == student_id,
                                                     Submission.assignment_id.in_([a.id for a in rows]))):
            status[s.assignment_id] = s.status
    out = []
    for a in rows:
        item = AssignmentOut.model_validate(a)
        item.my_submission_status = status.get(a.id)
        out.append(item)
    return out


@router.get("/assignments", response_model=list[AssignmentOut])
def list_assignments(class_id: int | None = None, student_id: int | None = Query(None, description="Parents: pick a linked child"),
                     limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                     user: User = Depends(academic), db: Session = Depends(get_db)):
    stmt = select(Assignment)
    sid = None
    if user.role == "parent":
        kids = approved_child_ids(db, user)
        if student_id and student_id not in kids:
            raise HTTPException(403, "That child is not linked to your account")
        pick = student_id or (next(iter(kids)) if len(kids) == 1 else None)
        if not pick:
            if not kids:
                return []
            raise HTTPException(422, "Specify student_id")
        st = db.get(StudentProfile, pick)
        stmt, sid = stmt.where(Assignment.class_id == st.class_id), st.id
    else:
        allowed = visible_class_ids(db, user)
        if allowed is not None:
            stmt = stmt.where(Assignment.class_id.in_(list(allowed) or [-1]))
        if user.role == "student":
            sid = _own_student(db, user).id
    if class_id:
        stmt = stmt.where(Assignment.class_id == class_id)
    rows = db.scalars(stmt.order_by(Assignment.created_at.desc()).limit(limit).offset(offset)).unique().all()
    return _decorate(db, rows, sid)


@router.post("/assignments", response_model=AssignmentOut, status_code=201)
def create_assignment(body: AssignmentIn, user: User = Depends(staff), db: Session = Depends(get_db)):
    if not can_manage_class(db, user, body.class_id):
        raise HTTPException(403, "You are not assigned to this class")
    a = Assignment(**body.model_dump(), created_by=user.id)
    db.add(a)
    db.flush()
    student_user_ids = list(db.scalars(select(StudentProfile.user_id).where(
        StudentProfile.class_id == a.class_id, StudentProfile.user_id.is_not(None))))
    audit(db, user, "assignment.create", "assignment", a.id, a.title)
    db.commit()
    db.refresh(a)
    push_to_users(db, student_user_ids, "New assignment", a.title)
    return a


def _own_assignment(db: Session, user: User, aid: int) -> Assignment:
    a = get_or_404(db, Assignment, aid, "Assignment")
    if user.role != "admin" and a.created_by != user.id and not can_manage_class(db, user, a.class_id):
        raise HTTPException(403, "You cannot change this assignment")
    return a


@router.put("/assignments/{aid}", response_model=AssignmentOut)
def update_assignment(aid: int, body: AssignmentIn, user: User = Depends(staff), db: Session = Depends(get_db)):
    a = _own_assignment(db, user, aid)
    if not can_manage_class(db, user, body.class_id):
        raise HTTPException(403, "You are not assigned to that class")
    for k, v in body.model_dump().items():
        setattr(a, k, v)
    db.commit()
    db.refresh(a)
    return a


@router.delete("/assignments/{aid}", response_model=Msg)
def delete_assignment(aid: int, user: User = Depends(staff), db: Session = Depends(get_db)):
    a = _own_assignment(db, user, aid)
    audit(db, user, "assignment.delete", "assignment", aid, a.title)
    db.delete(a)
    db.commit()
    return Msg(detail="Assignment deleted")


# ───────────── submissions ─────────────

@router.post("/assignments/{aid}/submissions", response_model=SubmissionOut)
def submit(aid: int, body: SubmissionIn, user: User = Depends(require_roles("student")), db: Session = Depends(get_db)):
    a = get_or_404(db, Assignment, aid, "Assignment")
    st = _own_student(db, user)
    if st.class_id != a.class_id:
        raise HTTPException(403, "This assignment is for a different class")
    if body.file_url and not body.file_url.startswith("/uploads/"):
        raise HTTPException(422, "file_url must come from /uploads")
    sub = db.scalar(select(Submission).where(Submission.assignment_id == aid, Submission.student_id == st.id))
    if sub:
        if sub.status == "reviewed":
            raise HTTPException(409, "This submission has already been reviewed")
        sub.text, sub.file_url, sub.submitted_at = body.text, body.file_url, utcnow()
    else:
        sub = Submission(assignment_id=aid, student_id=st.id, text=body.text, file_url=body.file_url)
        db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


@router.get("/assignments/{aid}/submissions", response_model=list[SubmissionOut])
def list_submissions(aid: int, status: str | None = None, user: User = Depends(staff), db: Session = Depends(get_db)):
    a = get_or_404(db, Assignment, aid, "Assignment")
    if not can_manage_class(db, user, a.class_id):
        raise HTTPException(403, "You are not assigned to this class")
    stmt = select(Submission).where(Submission.assignment_id == aid)
    if status:
        stmt = stmt.where(Submission.status == status)
    return db.scalars(stmt.order_by(Submission.submitted_at.desc())).unique().all()


@router.get("/me/submissions", response_model=list[SubmissionOut])
def my_submissions(user: User = Depends(require_roles("student")), db: Session = Depends(get_db)):
    st = _own_student(db, user)
    return db.scalars(select(Submission).where(Submission.student_id == st.id)
                      .order_by(Submission.submitted_at.desc())).unique().all()


@router.patch("/submissions/{sid}/review", response_model=SubmissionOut)
def review(sid: int, body: ReviewIn, user: User = Depends(staff), db: Session = Depends(get_db)):
    sub = get_or_404(db, Submission, sid, "Submission")
    a = db.get(Assignment, sub.assignment_id)
    if not can_manage_class(db, user, a.class_id):
        raise HTTPException(403, "You are not assigned to this class")
    sub.feedback, sub.grade, sub.status = body.feedback, body.grade, "reviewed"
    uid = sub.student.user_id
    db.commit()
    if uid:
        push_to_users(db, [uid], "Assignment reviewed", a.title)
    return sub


# ───────────── study materials ─────────────

@router.get("/materials", response_model=list[MaterialOut])
def materials(class_id: int | None = None, kind: str | None = None,
              limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
              user: User = Depends(academic), db: Session = Depends(get_db)):
    stmt = select(Material)
    allowed = visible_class_ids(db, user)
    if allowed is not None:  # school-wide (class_id NULL) + own classes
        stmt = stmt.where((Material.class_id.is_(None)) | (Material.class_id.in_(list(allowed) or [-1])))
    if class_id:
        stmt = stmt.where(Material.class_id == class_id)
    if kind:
        stmt = stmt.where(Material.kind == kind)
    return db.scalars(stmt.order_by(Material.created_at.desc()).limit(limit).offset(offset)).all()


@router.post("/materials", response_model=MaterialOut, status_code=201)
def add_material(body: MaterialIn, user: User = Depends(staff), db: Session = Depends(get_db)):
    if body.class_id is None and user.role != "admin":
        raise HTTPException(403, "Only admins can post school-wide materials")
    if body.class_id is not None and not can_manage_class(db, user, body.class_id):
        raise HTTPException(403, "You are not assigned to this class")
    if body.file_url and not body.file_url.startswith("/uploads/"):
        raise HTTPException(422, "file_url must come from /uploads")
    m = Material(**body.model_dump(), uploaded_by=user.id)
    db.add(m)
    db.commit()
    return m


@router.delete("/materials/{mid}", response_model=Msg)
def delete_material(mid: int, user: User = Depends(staff), db: Session = Depends(get_db)):
    m = get_or_404(db, Material, mid, "Material")
    if user.role != "admin" and m.uploaded_by != user.id:
        raise HTTPException(403, "You can only delete your own materials")
    db.delete(m)
    db.commit()
    return Msg(detail="Material deleted")
