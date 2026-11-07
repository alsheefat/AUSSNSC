"""Everything a guest can read without signing in."""
import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_or_404
from ..models import (AdmissionApplication, Album, CalendarEvent, ClassRoutineSlot, ExamResult,
                      ExamRoutineSlot, Notice, SchoolClass, SiteContent, TeacherProfile)
from ..schemas import (AdmissionIn, AdmissionOut, AlbumDetail, AlbumOut, ClassOut, EventOut,
                       ExamSlotOut, NoticeOut, ResultOut, RoutineSlotOut, TeacherPublic)
from ..security import client_ip, limiter
from ..utils import today_bd

router = APIRouter(tags=["Public"])


@router.get("/classes", response_model=list[ClassOut])
def list_classes(db: Session = Depends(get_db)):
    return db.scalars(select(SchoolClass).order_by(SchoolClass.name, SchoolClass.section)).all()


# ───────────── notices ─────────────

@router.get("/notices", response_model=list[NoticeOut])
def notices(category: str | None = None, q: str | None = Query(None, max_length=100),
            limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0),
            db: Session = Depends(get_db)):
    stmt = select(Notice).where(Notice.published.is_(True))
    if category:
        stmt = stmt.where(Notice.category == category)
    if q:
        stmt = stmt.where(or_(Notice.title.ilike(f"%{q}%"), Notice.body.ilike(f"%{q}%")))
    stmt = stmt.order_by(Notice.pinned.desc(), Notice.created_at.desc()).limit(limit).offset(offset)
    return db.scalars(stmt).all()


@router.get("/notices/{notice_id}", response_model=NoticeOut)
def notice(notice_id: int, db: Session = Depends(get_db)):
    n = get_or_404(db, Notice, notice_id, "Notice")
    if not n.published:
        raise HTTPException(404, "Notice not found")
    return n


# ───────────── result search ─────────────

@router.get("/results/search", response_model=list[ResultOut])
def search_results(request: Request,
                   roll: int | None = Query(None, ge=1),
                   name: str | None = Query(None, min_length=3, max_length=100),
                   exam: str | None = None, exam_year: int | None = None,
                   class_name: str | None = None, db: Session = Depends(get_db)):
    """Search published results by roll number (class_name strongly recommended because rolls
    repeat across classes) or by student name (min 3 chars, max 10 matches)."""
    if roll is None and not name:
        raise HTTPException(422, "Provide a roll number or a student name")
    limiter.check(f"rs:{client_ip(request)}", 30, 600)
    stmt = select(ExamResult).where(ExamResult.published.is_(True))
    if roll is not None:
        stmt = stmt.where(ExamResult.roll == roll)
    if name:
        stmt = stmt.where(ExamResult.student_name.ilike(f"%{name.strip()}%"))
    if exam:
        stmt = stmt.where(ExamResult.exam == exam)
    if exam_year:
        stmt = stmt.where(ExamResult.exam_year == exam_year)
    if class_name:
        stmt = stmt.where(ExamResult.class_name == class_name)
    rows = db.scalars(stmt.order_by(ExamResult.exam_year.desc(), ExamResult.exam).limit(10 if name else 20)).all()
    return [ResultOut.of(r) for r in rows]


@router.get("/results/exams", response_model=list[dict])
def published_exams(db: Session = Depends(get_db)):
    """Distinct published exams, for the result-search dropdown."""
    rows = db.execute(select(ExamResult.exam, ExamResult.exam_year).where(ExamResult.published.is_(True))
                      .group_by(ExamResult.exam, ExamResult.exam_year)
                      .order_by(ExamResult.exam_year.desc())).all()
    return [{"exam": e, "exam_year": y} for e, y in rows]


# ───────────── routines & calendar ─────────────

@router.get("/routines/class/{class_id}", response_model=list[RoutineSlotOut])
def class_routine(class_id: int, db: Session = Depends(get_db)):
    return db.scalars(select(ClassRoutineSlot).where(ClassRoutineSlot.class_id == class_id)
                      .order_by(ClassRoutineSlot.weekday, ClassRoutineSlot.start_time)).all()


@router.get("/routines/exam", response_model=list[ExamSlotOut])
def exam_routine(class_id: int | None = None, exam: str | None = None, upcoming: bool = True,
                 db: Session = Depends(get_db)):
    stmt = select(ExamRoutineSlot)
    if class_id:
        stmt = stmt.where(ExamRoutineSlot.class_id == class_id)
    if exam:
        stmt = stmt.where(ExamRoutineSlot.exam == exam)
    if upcoming:
        stmt = stmt.where(ExamRoutineSlot.day >= today_bd())
    return db.scalars(stmt.order_by(ExamRoutineSlot.day, ExamRoutineSlot.start_time)).all()


@router.get("/calendar", response_model=list[EventOut])
def calendar(from_: str | None = Query(None, alias="from", description="YYYY-MM-DD"),
             to: str | None = Query(None, description="YYYY-MM-DD"), db: Session = Depends(get_db)):
    stmt = select(CalendarEvent)
    try:
        if from_:
            stmt = stmt.where(CalendarEvent.start_date >= date.fromisoformat(from_))
        if to:
            stmt = stmt.where(CalendarEvent.start_date <= date.fromisoformat(to))
    except ValueError:
        raise HTTPException(422, "Dates must be YYYY-MM-DD")
    return db.scalars(stmt.order_by(CalendarEvent.start_date)).all()


# ───────────── gallery ─────────────

@router.get("/gallery/albums", response_model=list[AlbumOut])
def albums(db: Session = Depends(get_db)):
    return db.scalars(select(Album).order_by(Album.created_at.desc())).unique().all()


@router.get("/gallery/albums/{album_id}", response_model=AlbumDetail)
def album(album_id: int, db: Session = Depends(get_db)):
    return get_or_404(db, Album, album_id, "Album")


# ───────────── teachers, about, admission ─────────────

@router.get("/teachers", response_model=list[TeacherPublic])
def teachers(q: str | None = Query(None, max_length=100), department: str | None = None,
             db: Session = Depends(get_db)):
    stmt = select(TeacherProfile)
    if q:
        stmt = stmt.where(or_(TeacherProfile.full_name.ilike(f"%{q}%"),
                              TeacherProfile.department.ilike(f"%{q}%"),
                              TeacherProfile.designation.ilike(f"%{q}%")))
    if department:
        stmt = stmt.where(TeacherProfile.department == department)
    out = []
    for t in db.scalars(stmt.order_by(TeacherProfile.full_name)):
        item = TeacherPublic.model_validate(t)
        if not t.contact_public:          # contact details need school approval
            item.phone = item.email = None
        out.append(item)
    return out


@router.get("/content/{key}")
def content(key: str, db: Session = Depends(get_db)):
    """Editable pages: 'about', 'admission', 'contact'."""
    row = db.get(SiteContent, key)
    return json.loads(row.data) if row else {}


@router.post("/admission/applications", status_code=201)
def apply(body: AdmissionIn, request: Request, db: Session = Depends(get_db)):
    limiter.check(f"adm:{client_ip(request)}", 5, 3600)
    app = AdmissionApplication(**body.model_dump())
    db.add(app)
    db.commit()
    return {"id": app.id, "detail": "Application received. The school office will contact you."}
