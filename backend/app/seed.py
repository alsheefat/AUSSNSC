"""First-run data: bootstrap admin, default classes/channels and site pages (+ demo data in dev)."""
import json
import logging
from datetime import date, time, timedelta

from sqlalchemy import select

from .config import settings
from .db import SessionLocal
from .models import (Channel, CalendarEvent, ClassRoutineSlot, ExamRoutineSlot, Notice, SchoolClass,
                     SiteContent, StudentProfile, TeacherClass, TeacherProfile, User, ParentLink)
from .routers.admin import DEFAULT_CHANNELS
from .security import hash_password
from .utils import normalize_email, normalize_phone

log = logging.getLogger("aussnsc.seed")


def _user(db, name, phone, role, password):
    u = User(full_name=name, phone=normalize_phone(phone), password_hash=hash_password(password),
             role=role, phone_verified=True)
    db.add(u)
    db.flush()
    return u


def run() -> None:
    db = SessionLocal()
    try:
        # 1) bootstrap admin
        existing_admin = db.scalar(select(User).where(User.role == "admin").order_by(User.id))
        if existing_admin and settings.reset_admin and settings.admin_password:
            existing_admin.password_hash = hash_password(settings.admin_password)
            existing_admin.token_version += 1
            log.warning("Admin password reset from ADMIN_PASSWORD. Remove RESET_ADMIN now.")
        if not existing_admin:
            if settings.admin_password and (settings.admin_phone or settings.admin_email):
                u = User(full_name=settings.admin_name, role="admin",
                         password_hash=hash_password(settings.admin_password),
                         phone=normalize_phone(settings.admin_phone) if settings.admin_phone else None,
                         email=normalize_email(settings.admin_email) if settings.admin_email else None,
                         phone_verified=bool(settings.admin_phone), email_verified=bool(settings.admin_email))
                db.add(u)
                log.info("Created bootstrap admin account")
            else:
                log.warning("No admin exists. Set ADMIN_PHONE/ADMIN_EMAIL and ADMIN_PASSWORD, then restart.")

        # 2) classes 6-10, sections A/B, default channels, school-wide channel
        if not db.scalar(select(SchoolClass.id)):
            for n in ("6", "7", "8", "9", "10"):
                for s in ("A", "B"):
                    db.add(SchoolClass(name=n, section=s))
            db.flush()
        for c in db.scalars(select(SchoolClass)).all():
            have = set(db.scalars(select(Channel.name).where(Channel.class_id == c.id)))
            for name, desc, ann in DEFAULT_CHANNELS:
                if name not in have:
                    db.add(Channel(class_id=c.id, name=name, description=desc, announcement_only=ann))
        if not db.scalar(select(Channel.id).where(Channel.class_id.is_(None))):
            db.add(Channel(class_id=None, name="school-news", description="School-wide announcements", announcement_only=True))

        # 3) editable pages
        defaults = {
            "about": {"name": "Ahammad Uddin Shah Shishu Niketan School & College",
                      "summary": "Edit this text from the admin dashboard.", "programmes": [], "contact": {}},
            "admission": {"eligibility": [], "documents": [], "procedure": [], "important_dates": []},
        }
        for k, v in defaults.items():
            if not db.get(SiteContent, k):
                db.add(SiteContent(key=k, data=json.dumps(v, ensure_ascii=False)))
        db.commit()

        # 4) demo data (development only)
        if settings.seed_demo and not db.scalar(select(User.id).where(User.phone == "+8801700000001")):
            _demo(db)
            db.commit()
            log.warning("Demo data created. Demo logins (password 'Demo12345'): "
                        "student 01700000001, teacher 01700000002, parent 01700000003. DISABLE in production (SEED_DEMO=0).")
    finally:
        db.close()


def _demo(db) -> None:
    c10a = db.scalar(select(SchoolClass).where(SchoolClass.name == "10", SchoolClass.section == "A"))
    stu = _user(db, "Demo Student", "01700000001", "student", "Demo12345")
    tea = _user(db, "Demo Teacher", "01700000002", "teacher", "Demo12345")
    par = _user(db, "Demo Parent", "01700000003", "parent", "Demo12345")
    sp = StudentProfile(user_id=stu.id, full_name="Demo Student", class_id=c10a.id, roll=1)
    db.add(sp)
    db.add(StudentProfile(full_name="Rahim Uddin", class_id=c10a.id, roll=2))
    tp = TeacherProfile(user_id=tea.id, full_name="Demo Teacher", designation="Assistant Teacher", department="Mathematics")
    db.add(tp)
    db.flush()
    db.add(TeacherClass(teacher_id=tp.id, class_id=c10a.id, subject="Mathematics"))
    db.add(ParentLink(parent_id=par.id, student_id=sp.id, claimed_name=sp.full_name, claimed_class="10",
                      claimed_roll=1, relationship_="Father", status="approved"))
    for title, cat in (("Admission notice 2026", "admission"), ("Class routine update", "routine"),
                       ("Annual sports day", "event"), ("Holiday announcement", "holiday")):
        db.add(Notice(title=title, body=f"Sample notice: {title}. Edit or delete from the admin dashboard.", category=cat))
    today = date.today()
    db.add(CalendarEvent(title="Victory Day", start_date=date(today.year, 12, 16), kind="holiday"))
    db.add(CalendarEvent(title="New academic year", start_date=date(today.year + 1, 1, 1), kind="event"))
    for i, subj in enumerate(("Bangla", "English", "Mathematics", "ICT")):
        db.add(ClassRoutineSlot(class_id=c10a.id, weekday=i, start_time=time(9 + (i % 3), 0),
                                end_time=time(9 + (i % 3), 45), subject=subj))
        db.add(ExamRoutineSlot(exam="Annual Examination", class_id=c10a.id, subject=subj,
                               day=today + timedelta(days=7 + 2 * i), start_time=time(10, 0), duration_minutes=180))
