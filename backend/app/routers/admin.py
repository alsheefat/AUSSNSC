"""Admin dashboard API. Every route here requires role=admin."""
import csv
import io
import json
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import audit, get_or_404, require_roles
from ..models import (AdmissionApplication, Album, Attendance, AuditLog, CalendarEvent, Channel,
                      ClassRoutineSlot, ExamResult, ExamRoutineSlot, MessageReport, Notice,
                      ParentLink, Photo, SchoolClass, SiteContent, StudentProfile, TeacherClass,
                      TeacherProfile, User)
from ..notifications import push_to_users
from ..routers.parent import match_student
from ..schemas import (AdminPasswordIn, AdminUserPatch, AdmissionOut, AlbumDetail, AlbumIn,
                       AuditOut, ChannelIn, ChannelOut, ChannelPatch, ClassIn, ClassOut, ContentIn,
                       EventIn, EventOut, ExamSlotIn, ExamSlotOut, Msg, NoticeIn, NoticeOut,
                       ParentDecisionIn, ParentLinkOut, PhotoIn, PhotoOut, PublishIn, ResultIn,
                       ResultOut, RoutineSlotIn, RoutineSlotOut, StatusIn, StudentIn, StudentOut,
                       StudentPatch, TeacherAdminOut, TeacherClassIn, TeacherClassOut, TeacherIn,
                       UserOut)
from ..security import hash_password
from ..utils import today_bd

router = APIRouter(prefix="/admin", tags=["Admin"])
Admin = Depends(require_roles())  # admin only (require_roles always allows admin)

DEFAULT_CHANNELS = [("general", "General class discussion", False),
                    ("announcements", "Teacher announcements", True),
                    ("study-discussion", "Lessons and revision", False),
                    ("questions", "Ask your teachers", False),
                    ("resources", "Shared resources", False)]


def _commit(db: Session, msg: str = "That conflicts with existing data"):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, msg)


# ───────────── dashboard ─────────────

@router.get("/stats")
def stats(admin: User = Admin, db: Session = Depends(get_db)):
    count = lambda stmt: db.scalar(stmt) or 0  # noqa: E731
    today = today_bd()
    marked = count(select(func.count(Attendance.id)).where(Attendance.day == today))
    here = count(select(func.count(Attendance.id)).where(Attendance.day == today, Attendance.status != "absent"))
    return {
        "users_by_role": dict(db.execute(select(User.role, func.count(User.id)).group_by(User.role)).all()),
        "students": count(select(func.count(StudentProfile.id))),
        "teachers": count(select(func.count(TeacherProfile.id))),
        "classes": count(select(func.count(SchoolClass.id))),
        "notices_published": count(select(func.count(Notice.id)).where(Notice.published.is_(True))),
        "pending_parent_links": count(select(func.count(ParentLink.id)).where(ParentLink.status == "pending")),
        "new_admission_applications": count(select(func.count(AdmissionApplication.id)).where(AdmissionApplication.status == "new")),
        "open_message_reports": count(select(func.count(MessageReport.id)).where(MessageReport.resolved.is_(False))),
        "today_attendance_marked": marked,
        "today_attendance_rate": round(here * 100 / marked, 1) if marked else None,
    }


@router.get("/reports/attendance")
def attendance_report(class_id: int, start: date, end: date, admin: User = Admin, db: Session = Depends(get_db)):
    rows = db.execute(
        select(StudentProfile.id, StudentProfile.roll, StudentProfile.full_name, Attendance.status, func.count(Attendance.id))
        .join(Attendance, Attendance.student_id == StudentProfile.id)
        .where(StudentProfile.class_id == class_id, Attendance.day >= start, Attendance.day <= end)
        .group_by(StudentProfile.id, StudentProfile.roll, StudentProfile.full_name, Attendance.status)
        .order_by(StudentProfile.roll)).all()
    out: dict[int, dict] = {}
    for sid, roll, name, status, n in rows:
        d = out.setdefault(sid, {"student_id": sid, "roll": roll, "name": name, "present": 0, "absent": 0, "late": 0})
        d[status] = n
    for d in out.values():
        total = d["present"] + d["absent"] + d["late"]
        d["rate_percent"] = round((d["present"] + d["late"]) * 100 / total, 1) if total else 0
    return list(out.values())


@router.get("/audit", response_model=list[AuditOut])
def audit_logs(action: str | None = None, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
               admin: User = Admin, db: Session = Depends(get_db)):
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action.like(f"{action}%"))
    return db.scalars(stmt.order_by(AuditLog.id.desc()).limit(limit).offset(offset)).unique().all()


# ───────────── users ─────────────

@router.get("/users", response_model=list[UserOut])
def users(role: str | None = None, q: str | None = Query(None, max_length=100),
          limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
          admin: User = Admin, db: Session = Depends(get_db)):
    stmt = select(User)
    if role:
        stmt = stmt.where(User.role == role)
    if q:
        stmt = stmt.where(or_(User.full_name.ilike(f"%{q}%"), User.phone.ilike(f"%{q}%"), User.email.ilike(f"%{q}%")))
    return db.scalars(stmt.order_by(User.id.desc()).limit(limit).offset(offset)).all()


@router.patch("/users/{uid}", response_model=UserOut)
def patch_user(uid: int, body: AdminUserPatch, admin: User = Admin, db: Session = Depends(get_db)):
    u = get_or_404(db, User, uid, "User")
    data = body.model_dump(exclude_unset=True, exclude_none=True)
    if u.id == admin.id and (data.get("role", "admin") != "admin" or data.get("is_active") is False):
        raise HTTPException(400, "You cannot demote or disable your own admin account")
    if data:
        if "role" in data or "is_active" in data:
            u.token_version += 1  # force re-login so new permissions apply immediately
        for k, v in data.items():
            setattr(u, k, v)
        audit(db, admin, "user.update", "user", uid, json.dumps(data))
        db.commit()
    return u


@router.post("/users/{uid}/reset-password", response_model=Msg)
def reset_password(uid: int, body: AdminPasswordIn, admin: User = Admin, db: Session = Depends(get_db)):
    u = get_or_404(db, User, uid, "User")
    u.password_hash = hash_password(body.new_password)
    u.token_version += 1
    audit(db, admin, "user.reset_password", "user", uid)
    db.commit()
    return Msg(detail="Password reset. Share the new password with the user securely.")


# ───────────── classes / students / teachers ─────────────

@router.post("/classes", response_model=ClassOut, status_code=201)
def create_class(body: ClassIn, admin: User = Admin, db: Session = Depends(get_db)):
    c = SchoolClass(name=body.name.strip(), section=body.section.strip().upper())
    db.add(c)
    _commit(db, "That class and section already exist")
    return c


@router.delete("/classes/{cid}", response_model=Msg)
def delete_class(cid: int, admin: User = Admin, db: Session = Depends(get_db)):
    c = get_or_404(db, SchoolClass, cid, "Class")
    if db.scalar(select(func.count(StudentProfile.id)).where(StudentProfile.class_id == cid)):
        raise HTTPException(409, "Move or remove the students in this class first")
    audit(db, admin, "class.delete", "class", cid, c.label)
    db.delete(c)
    db.commit()
    return Msg(detail="Class deleted")


@router.get("/students", response_model=list[StudentOut])
def list_students(class_id: int | None = None, q: str | None = Query(None, max_length=100),
                  limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
                  admin: User = Admin, db: Session = Depends(get_db)):
    stmt = select(StudentProfile)
    if class_id:
        stmt = stmt.where(StudentProfile.class_id == class_id)
    if q:
        stmt = stmt.where(StudentProfile.full_name.ilike(f"%{q}%"))
    return db.scalars(stmt.order_by(StudentProfile.class_id, StudentProfile.roll).limit(limit).offset(offset)).unique().all()


@router.post("/students", response_model=StudentOut, status_code=201)
def create_student(body: StudentIn, admin: User = Admin, db: Session = Depends(get_db)):
    get_or_404(db, SchoolClass, body.class_id, "Class")
    s = StudentProfile(**body.model_dump())
    db.add(s)
    _commit(db, "That roll number is taken in this class, or the user is already linked to a student")
    audit(db, admin, "student.create", "student", s.id, s.full_name)
    db.commit()
    db.refresh(s)
    if s.user_id:
        _promote(db, s.user_id, "student")
    return s


@router.patch("/students/{sid}", response_model=StudentOut)
def patch_student(sid: int, body: StudentPatch, admin: User = Admin, db: Session = Depends(get_db)):
    s = get_or_404(db, StudentProfile, sid, "Student")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    _commit(db, "That roll number is taken in this class, or the user is already linked to a student")
    db.refresh(s)
    if body.user_id:
        _promote(db, body.user_id, "student")
    return s


@router.delete("/students/{sid}", response_model=Msg)
def delete_student(sid: int, admin: User = Admin, db: Session = Depends(get_db)):
    s = get_or_404(db, StudentProfile, sid, "Student")
    audit(db, admin, "student.delete", "student", sid, s.full_name)
    db.delete(s)
    db.commit()
    return Msg(detail="Student removed (their attendance and submissions were removed too)")


@router.post("/students/import")
async def import_students(file: UploadFile = File(...), admin: User = Admin, db: Session = Depends(get_db)):
    """CSV columns: full_name,class,section,roll[,student_code,guardian_phone]. Missing classes are created."""
    rows = list(csv.DictReader(io.StringIO((await file.read()).decode("utf-8-sig"))))
    made, errors = 0, []
    for i, r in enumerate(rows, start=2):
        try:
            name, cls, sec, roll = r["full_name"].strip(), r["class"].strip(), r["section"].strip().upper(), int(r["roll"])
            c = db.scalar(select(SchoolClass).where(SchoolClass.name == cls, SchoolClass.section == sec))
            if not c:
                c = SchoolClass(name=cls, section=sec)
                db.add(c)
                db.flush()
            with db.begin_nested():
                db.add(StudentProfile(full_name=name, class_id=c.id, roll=roll,
                                      student_code=(r.get("student_code") or "").strip() or None,
                                      guardian_phone=(r.get("guardian_phone") or "").strip() or None))
                db.flush()
            made += 1
        except (KeyError, ValueError):
            errors.append(f"line {i}: missing/invalid column")
        except IntegrityError:
            errors.append(f"line {i}: duplicate roll in that class")
    audit(db, admin, "student.import", "student", None, f"{made} created, {len(errors)} errors")
    db.commit()
    return {"created": made, "errors": errors[:50]}


def _promote(db: Session, user_id: int, role: str):
    u = db.get(User, user_id)
    if u and u.role in ("public", role):
        if u.role != role:
            u.role = role
            u.token_version += 1
        db.commit()


@router.get("/teachers", response_model=list[TeacherAdminOut])
def list_teachers(admin: User = Admin, db: Session = Depends(get_db)):
    return db.scalars(select(TeacherProfile).order_by(TeacherProfile.full_name)).all()


@router.post("/teachers", response_model=TeacherAdminOut, status_code=201)
def create_teacher(body: TeacherIn, admin: User = Admin, db: Session = Depends(get_db)):
    t = TeacherProfile(**body.model_dump())
    db.add(t)
    _commit(db, "That user is already linked to a teacher profile")
    if t.user_id:
        _promote(db, t.user_id, "teacher")
    audit(db, admin, "teacher.create", "teacher", t.id, t.full_name)
    db.commit()
    return t


@router.patch("/teachers/{tid}", response_model=TeacherAdminOut)
def patch_teacher(tid: int, body: TeacherIn, admin: User = Admin, db: Session = Depends(get_db)):
    t = get_or_404(db, TeacherProfile, tid, "Teacher")
    for k, v in body.model_dump().items():
        setattr(t, k, v)
    _commit(db, "That user is already linked to a teacher profile")
    if t.user_id:
        _promote(db, t.user_id, "teacher")
    return t


@router.delete("/teachers/{tid}", response_model=Msg)
def delete_teacher(tid: int, admin: User = Admin, db: Session = Depends(get_db)):
    t = get_or_404(db, TeacherProfile, tid, "Teacher")
    audit(db, admin, "teacher.delete", "teacher", tid, t.full_name)
    db.delete(t)
    db.commit()
    return Msg(detail="Teacher removed")


@router.get("/teachers/{tid}/classes", response_model=list[TeacherClassOut])
def teacher_classes(tid: int, admin: User = Admin, db: Session = Depends(get_db)):
    return db.scalars(select(TeacherClass).where(TeacherClass.teacher_id == tid)).unique().all()


@router.post("/teachers/{tid}/classes", response_model=TeacherClassOut, status_code=201)
def assign_class(tid: int, body: TeacherClassIn, admin: User = Admin, db: Session = Depends(get_db)):
    get_or_404(db, TeacherProfile, tid, "Teacher")
    get_or_404(db, SchoolClass, body.class_id, "Class")
    tc = TeacherClass(teacher_id=tid, class_id=body.class_id, subject=body.subject.strip())
    db.add(tc)
    _commit(db, "Teacher is already assigned to this class/subject")
    audit(db, admin, "teacher.assign", "teacher", tid, f"class {body.class_id} {body.subject}")
    db.commit()
    db.refresh(tc)
    return tc


@router.delete("/teachers/{tid}/classes/{tc_id}", response_model=Msg)
def unassign_class(tid: int, tc_id: int, admin: User = Admin, db: Session = Depends(get_db)):
    db.execute(delete(TeacherClass).where(TeacherClass.id == tc_id, TeacherClass.teacher_id == tid))
    db.commit()
    return Msg(detail="Assignment removed")


# ───────────── parent links ─────────────

@router.get("/parent-links", response_model=list[ParentLinkOut])
def parent_links(status: str = "pending", admin: User = Admin, db: Session = Depends(get_db)):
    return db.scalars(select(ParentLink).where(ParentLink.status == status).order_by(ParentLink.id)).unique().all()


@router.post("/parent-links/{lid}/decision", response_model=ParentLinkOut)
def decide_link(lid: int, body: ParentDecisionIn, admin: User = Admin, db: Session = Depends(get_db)):
    link = get_or_404(db, ParentLink, lid, "Request")
    if body.approve:
        sid = body.student_id or link.student_id
        if not sid:
            m = match_student(db, link.claimed_name, link.claimed_class, link.claimed_roll)
            sid = m.id if m else None
        if not sid:
            raise HTTPException(422, "No matching student - pick one with student_id")
        get_or_404(db, StudentProfile, sid, "Student")
        link.student_id, link.status = sid, "approved"
        _promote(db, link.parent_id, "parent")
    else:
        link.status = "rejected"
    audit(db, admin, "parent_link.decide", "parent_link", lid, link.status)
    db.commit()
    db.refresh(link)
    push_to_users(db, [link.parent_id], "Child link request", f"Your request was {link.status}")
    return link


# ───────────── notices / calendar / content ─────────────

@router.get("/notices", response_model=list[NoticeOut])
def all_notices(admin: User = Admin, db: Session = Depends(get_db)):
    return db.scalars(select(Notice).order_by(Notice.created_at.desc()).limit(200)).all()


@router.post("/notices", response_model=NoticeOut, status_code=201)
def create_notice(body: NoticeIn, admin: User = Admin, db: Session = Depends(get_db)):
    n = Notice(**body.model_dump(exclude={"send_push"}), created_by=admin.id)
    db.add(n)
    db.flush()
    audit(db, admin, "notice.create", "notice", n.id, n.title)
    db.commit()
    if body.send_push and n.published:
        push_to_users(db, None, n.title, n.body[:120])
    return n


@router.put("/notices/{nid}", response_model=NoticeOut)
def update_notice(nid: int, body: NoticeIn, admin: User = Admin, db: Session = Depends(get_db)):
    n = get_or_404(db, Notice, nid, "Notice")
    for k, v in body.model_dump(exclude={"send_push"}).items():
        setattr(n, k, v)
    audit(db, admin, "notice.update", "notice", nid, n.title)
    db.commit()
    return n


@router.delete("/notices/{nid}", response_model=Msg)
def delete_notice(nid: int, admin: User = Admin, db: Session = Depends(get_db)):
    n = get_or_404(db, Notice, nid, "Notice")
    audit(db, admin, "notice.delete", "notice", nid, n.title)
    db.delete(n)
    db.commit()
    return Msg(detail="Notice deleted")


@router.post("/calendar", response_model=EventOut, status_code=201)
def create_event(body: EventIn, admin: User = Admin, db: Session = Depends(get_db)):
    e = CalendarEvent(**body.model_dump())
    db.add(e)
    db.commit()
    return e


@router.put("/calendar/{eid}", response_model=EventOut)
def update_event(eid: int, body: EventIn, admin: User = Admin, db: Session = Depends(get_db)):
    e = get_or_404(db, CalendarEvent, eid, "Event")
    for k, v in body.model_dump().items():
        setattr(e, k, v)
    db.commit()
    return e


@router.delete("/calendar/{eid}", response_model=Msg)
def delete_event(eid: int, admin: User = Admin, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, CalendarEvent, eid, "Event"))
    db.commit()
    return Msg(detail="Event deleted")


@router.put("/content/{key}", response_model=Msg)
def put_content(key: str, body: ContentIn, admin: User = Admin, db: Session = Depends(get_db)):
    if key not in ("about", "admission", "contact"):
        raise HTTPException(404, "Unknown content key (use about, admission or contact)")
    row = db.get(SiteContent, key) or SiteContent(key=key)
    row.data = json.dumps(body.data, ensure_ascii=False)
    db.add(row)
    audit(db, admin, "content.update", "content", key)
    db.commit()
    return Msg(detail="Saved")


# ───────────── gallery ─────────────

@router.post("/gallery/albums", response_model=AlbumDetail, status_code=201)
def create_album(body: AlbumIn, admin: User = Admin, db: Session = Depends(get_db)):
    a = Album(**body.model_dump())
    db.add(a)
    db.commit()
    return a


@router.post("/gallery/albums/{aid}/photos", response_model=PhotoOut, status_code=201)
def add_photo(aid: int, body: PhotoIn, admin: User = Admin, db: Session = Depends(get_db)):
    get_or_404(db, Album, aid, "Album")
    if not body.url.startswith("/uploads/"):
        raise HTTPException(422, "url must come from /uploads")
    p = Photo(album_id=aid, url=body.url, caption=body.caption)
    db.add(p)
    db.commit()
    return p


@router.delete("/gallery/albums/{aid}", response_model=Msg)
def delete_album(aid: int, admin: User = Admin, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, Album, aid, "Album"))
    db.commit()
    return Msg(detail="Album deleted")


@router.delete("/gallery/photos/{pid}", response_model=Msg)
def delete_photo(pid: int, admin: User = Admin, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, Photo, pid, "Photo"))
    db.commit()
    return Msg(detail="Photo deleted")


# ───────────── admission applications ─────────────

@router.get("/admission/applications", response_model=list[AdmissionOut])
def applications(status: str | None = None, admin: User = Admin, db: Session = Depends(get_db)):
    stmt = select(AdmissionApplication)
    if status:
        stmt = stmt.where(AdmissionApplication.status == status)
    return db.scalars(stmt.order_by(AdmissionApplication.id.desc()).limit(200)).all()


@router.patch("/admission/applications/{aid}", response_model=AdmissionOut)
def set_application_status(aid: int, body: StatusIn, admin: User = Admin, db: Session = Depends(get_db)):
    a = get_or_404(db, AdmissionApplication, aid, "Application")
    a.status = body.status
    db.commit()
    return a


# ───────────── results ─────────────

def _link_student(db: Session, r: ExamResult) -> None:
    """Attach a result to a student record (so students/parents see it under 'my results')."""
    q = select(StudentProfile).join(SchoolClass, SchoolClass.id == StudentProfile.class_id).where(
        StudentProfile.roll == r.roll, SchoolClass.name == r.class_name)
    if r.section:
        q = q.where(SchoolClass.section == r.section)
    found = db.scalars(q).unique().all()
    named = [s for s in found if s.full_name.strip().lower() == r.student_name.strip().lower()]
    r.student_id = named[0].id if len(named) == 1 else None


@router.get("/results", response_model=list[ResultOut])
def list_results(exam: str | None = None, exam_year: int | None = None, class_name: str | None = None,
                 published: bool | None = None, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
                 admin: User = Admin, db: Session = Depends(get_db)):
    stmt = select(ExamResult)
    for col, val in ((ExamResult.exam, exam), (ExamResult.exam_year, exam_year),
                     (ExamResult.class_name, class_name), (ExamResult.published, published)):
        if val is not None:
            stmt = stmt.where(col == val)
    return [ResultOut.of(r) for r in db.scalars(stmt.order_by(ExamResult.class_name, ExamResult.roll).limit(limit).offset(offset))]


@router.post("/results", response_model=ResultOut, status_code=201)
def create_result(body: ResultIn, admin: User = Admin, db: Session = Depends(get_db)):
    data = body.model_dump()
    data["subjects"] = json.dumps(data["subjects"], ensure_ascii=False)
    r = ExamResult(**data)
    _link_student(db, r)
    db.add(r)
    audit(db, admin, "result.create", "result", None, f"{r.exam} {r.exam_year} {r.class_name}/{r.roll}")
    db.commit()
    return ResultOut.of(r)


def _parse_subjects(raw: str) -> list[dict]:
    """'Bangla:85;English:78' or '[{"subject":"Bangla","marks":85}]'."""
    raw = (raw or "").strip()
    if not raw:
        return []
    if raw.startswith("["):
        return json.loads(raw)
    out = []
    for part in raw.split(";"):
        if ":" in part:
            s, m = part.rsplit(":", 1)
            out.append({"subject": s.strip(), "marks": float(m)})
    return out


@router.post("/results/import")
async def import_results(published: bool = False, file: UploadFile = File(...), admin: User = Admin,
                         db: Session = Depends(get_db)):
    """CSV columns: exam,exam_year,class_name,section,roll,student_name,gpa,grade,total_marks,status,subjects
    (subjects like 'Bangla:85;English:78'). Imported unpublished unless ?published=true."""
    rows = list(csv.DictReader(io.StringIO((await file.read()).decode("utf-8-sig"))))
    made, errors = 0, []
    for i, r in enumerate(rows, start=2):
        try:
            item = ResultIn(exam=r["exam"].strip(), exam_year=int(r["exam_year"]), class_name=r["class_name"].strip(),
                            section=(r.get("section") or "").strip() or None, roll=int(r["roll"]),
                            student_name=r["student_name"].strip(),
                            gpa=float(r["gpa"]) if r.get("gpa") else None, grade=(r.get("grade") or "").strip() or None,
                            total_marks=float(r["total_marks"]) if r.get("total_marks") else None,
                            status=(r.get("status") or "passed").strip().lower(),
                            subjects=_parse_subjects(r.get("subjects", "")), published=published)
        except Exception as e:  # noqa: BLE001 - report any bad row, keep going
            errors.append(f"line {i}: {str(e)[:80]}")
            continue
        data = item.model_dump()
        data["subjects"] = json.dumps(data["subjects"], ensure_ascii=False)
        res = ExamResult(**data)
        _link_student(db, res)
        db.add(res)
        made += 1
    audit(db, admin, "result.import", "result", None, f"{made} rows, {len(errors)} errors, published={published}")
    db.commit()
    return {"created": made, "errors": errors[:50]}


@router.post("/results/publish", response_model=Msg)
def publish_results(body: PublishIn, admin: User = Admin, db: Session = Depends(get_db)):
    rows = db.scalars(select(ExamResult).where(ExamResult.exam == body.exam, ExamResult.exam_year == body.exam_year)).all()
    for r in rows:
        r.published = body.published
    audit(db, admin, "result.publish" if body.published else "result.unpublish", "result", None,
          f"{body.exam} {body.exam_year}: {len(rows)} rows")
    db.commit()
    if body.published:
        push_to_users(db, None, "Results published", f"{body.exam} {body.exam_year}")
    return Msg(detail=f"{len(rows)} results {'published' if body.published else 'hidden'}")


@router.delete("/results/{rid}", response_model=Msg)
def delete_result(rid: int, admin: User = Admin, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, ExamResult, rid, "Result"))
    db.commit()
    return Msg(detail="Result deleted")


# ───────────── routines ─────────────

@router.put("/routines/class/{class_id}", response_model=list[RoutineSlotOut])
def replace_class_routine(class_id: int, slots: list[RoutineSlotIn], admin: User = Admin, db: Session = Depends(get_db)):
    """Replaces the whole weekly timetable of a class in one call."""
    get_or_404(db, SchoolClass, class_id, "Class")
    db.execute(delete(ClassRoutineSlot).where(ClassRoutineSlot.class_id == class_id))
    new = [ClassRoutineSlot(class_id=class_id, **s.model_dump()) for s in slots]
    db.add_all(new)
    audit(db, admin, "routine.replace", "class", class_id, f"{len(new)} slots")
    db.commit()
    return new


@router.post("/routines/exam", response_model=list[ExamSlotOut], status_code=201)
def add_exam_slots(slots: list[ExamSlotIn], admin: User = Admin, db: Session = Depends(get_db)):
    new = [ExamRoutineSlot(**s.model_dump()) for s in slots]
    db.add_all(new)
    audit(db, admin, "exam_routine.add", "exam_routine", None, f"{len(new)} slots")
    db.commit()
    return new


@router.delete("/routines/exam/{sid}", response_model=Msg)
def delete_exam_slot(sid: int, admin: User = Admin, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, ExamRoutineSlot, sid, "Exam slot"))
    db.commit()
    return Msg(detail="Deleted")


# ───────────── community channels ─────────────

@router.post("/channels", response_model=ChannelOut, status_code=201)
def create_channel(body: ChannelIn, admin: User = Admin, db: Session = Depends(get_db)):
    if body.class_id:
        get_or_404(db, SchoolClass, body.class_id, "Class")
    ch = Channel(**body.model_dump())
    db.add(ch)
    _commit(db, "A channel with that name already exists here")
    db.refresh(ch)
    return ch


@router.patch("/channels/{cid}", response_model=ChannelOut)
def patch_channel(cid: int, body: ChannelPatch, admin: User = Admin, db: Session = Depends(get_db)):
    ch = get_or_404(db, Channel, cid, "Channel")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(ch, k, v)
    db.commit()
    return ch


@router.delete("/channels/{cid}", response_model=Msg)
def delete_channel(cid: int, admin: User = Admin, db: Session = Depends(get_db)):
    ch = get_or_404(db, Channel, cid, "Channel")
    audit(db, admin, "channel.delete", "channel", cid, ch.name)
    db.delete(ch)
    db.commit()
    return Msg(detail="Channel deleted")


@router.post("/channels/seed", response_model=Msg)
def seed_channels(admin: User = Admin, db: Session = Depends(get_db)):
    """Creates the default five channels for every class that lacks them."""
    made = 0
    for c in db.scalars(select(SchoolClass)):
        have = set(db.scalars(select(Channel.name).where(Channel.class_id == c.id)))
        for name, desc, ann in DEFAULT_CHANNELS:
            if name not in have:
                db.add(Channel(class_id=c.id, name=name, description=desc, announcement_only=ann))
                made += 1
    db.commit()
    return Msg(detail=f"{made} channels created")
