from datetime import date, datetime, time

from sqlalchemy import (Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, Time,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .utils import utcnow

ROLES = ("public", "student", "parent", "teacher", "admin")


# ───────────── accounts ─────────────

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="public", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    phone_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    language: Mapped[str] = mapped_column(String(5), default="en")      # en | bn
    theme: Mapped[str] = mapped_column(String(10), default="system")    # light | dark | system
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    google_uid: Mapped[str | None] = mapped_column(String(128), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class OTP(Base):
    __tablename__ = "otps"
    id: Mapped[int] = mapped_column(primary_key=True)
    target: Mapped[str] = mapped_column(String(254), index=True)
    purpose: Mapped[str] = mapped_column(String(10))  # verify | reset
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    used: Mapped[bool] = mapped_column(Boolean, default=False)


class DeviceToken(Base):
    __tablename__ = "device_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token: Mapped[str] = mapped_column(String(300), unique=True)
    platform: Mapped[str] = mapped_column(String(10), default="android")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ───────────── school structure ─────────────

class SchoolClass(Base):
    __tablename__ = "classes"
    __table_args__ = (UniqueConstraint("name", "section"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(20))      # "10"
    section: Mapped[str] = mapped_column(String(10))   # "A"

    @property
    def label(self) -> str:
        return f"Class {self.name} · Section {self.section}"


class StudentProfile(Base):
    __tablename__ = "students"
    __table_args__ = (UniqueConstraint("class_id", "roll"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), unique=True)
    full_name: Mapped[str] = mapped_column(String(120), index=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"), index=True)
    roll: Mapped[int] = mapped_column(Integer)
    student_code: Mapped[str | None] = mapped_column(String(30))
    guardian_phone: Mapped[str | None] = mapped_column(String(20))
    school_class: Mapped[SchoolClass] = relationship(lazy="joined")

    @property
    def class_label(self) -> str:
        return self.school_class.label


class TeacherProfile(Base):
    __tablename__ = "teachers"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), unique=True)
    full_name: Mapped[str] = mapped_column(String(120), index=True)
    designation: Mapped[str | None] = mapped_column(String(80))
    department: Mapped[str | None] = mapped_column(String(80))
    phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(254))
    photo_url: Mapped[str | None] = mapped_column(String(300))
    contact_public: Mapped[bool] = mapped_column(Boolean, default=False)  # school approval to show contact


class TeacherClass(Base):
    __tablename__ = "teacher_classes"
    __table_args__ = (UniqueConstraint("teacher_id", "class_id", "subject"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.id", ondelete="CASCADE"), index=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), index=True)
    subject: Mapped[str] = mapped_column(String(60), default="")
    school_class: Mapped[SchoolClass] = relationship(lazy="joined")

    @property
    def class_label(self) -> str:
        return self.school_class.label


class ParentLink(Base):
    __tablename__ = "parent_links"
    id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[int | None] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"))
    claimed_name: Mapped[str] = mapped_column(String(120))
    claimed_class: Mapped[str] = mapped_column(String(30))
    claimed_roll: Mapped[int] = mapped_column(Integer)
    relationship_: Mapped[str] = mapped_column("relationship", String(30))
    status: Mapped[str] = mapped_column(String(10), default="pending", index=True)  # pending|approved|rejected
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    parent: Mapped[User] = relationship(lazy="joined")
    student: Mapped[StudentProfile | None] = relationship(lazy="joined")

    @property
    def parent_name(self) -> str:
        return self.parent.full_name

    @property
    def student_name(self) -> str | None:
        return self.student.full_name if self.student else None


# ───────────── public content ─────────────

class Notice(Base):
    __tablename__ = "notices"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(30), default="general", index=True)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    published: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    attachment_url: Mapped[str | None] = mapped_column(String(300))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class CalendarEvent(Base):
    __tablename__ = "calendar_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    start_date: Mapped[date] = mapped_column(Date, index=True)
    end_date: Mapped[date | None] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(20), default="event")  # event|exam|holiday
    description: Mapped[str | None] = mapped_column(Text)


class Album(Base):
    __tablename__ = "albums"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    photos: Mapped[list["Photo"]] = relationship(cascade="all, delete-orphan", order_by="Photo.id")

    @property
    def cover_url(self) -> str | None:
        return self.photos[0].url if self.photos else None

    @property
    def photo_count(self) -> int:
        return len(self.photos)


class Photo(Base):
    __tablename__ = "photos"
    id: Mapped[int] = mapped_column(primary_key=True)
    album_id: Mapped[int] = mapped_column(ForeignKey("albums.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(String(300))
    caption: Mapped[str | None] = mapped_column(String(200))


class SiteContent(Base):
    """Editable pages: about, admission (eligibility/documents/procedure/dates), contact."""
    __tablename__ = "site_content"
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    data: Mapped[str] = mapped_column(Text, default="{}")  # JSON string
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class AdmissionApplication(Base):
    __tablename__ = "admission_applications"
    id: Mapped[int] = mapped_column(primary_key=True)
    applicant_name: Mapped[str] = mapped_column(String(120))
    guardian_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(254))
    class_applying: Mapped[str] = mapped_column(String(30))
    previous_school: Mapped[str | None] = mapped_column(String(150))
    message: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(15), default="new", index=True)  # new|contacted|accepted|rejected
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ───────────── academics ─────────────

class ExamResult(Base):
    __tablename__ = "exam_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    exam: Mapped[str] = mapped_column(String(80), index=True)   # "Annual Examination"
    exam_year: Mapped[int] = mapped_column(Integer, index=True)
    class_name: Mapped[str] = mapped_column(String(20), index=True)
    section: Mapped[str | None] = mapped_column(String(10))
    roll: Mapped[int] = mapped_column(Integer, index=True)
    student_name: Mapped[str] = mapped_column(String(120), index=True)
    student_id: Mapped[int | None] = mapped_column(ForeignKey("students.id", ondelete="SET NULL"), index=True)
    gpa: Mapped[float | None] = mapped_column(Float)
    grade: Mapped[str | None] = mapped_column(String(5))
    total_marks: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(10), default="passed")
    subjects: Mapped[str] = mapped_column(Text, default="[]")  # JSON [{"subject","marks","grade"}]
    published: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("student_id", "day"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(10))  # present|absent|late
    marked_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class ClassRoutineSlot(Base):
    __tablename__ = "class_routine"
    id: Mapped[int] = mapped_column(primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), index=True)
    weekday: Mapped[int] = mapped_column(Integer)  # 0=Sunday … 6=Saturday
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time | None] = mapped_column(Time)
    subject: Mapped[str] = mapped_column(String(60))
    teacher_name: Mapped[str | None] = mapped_column(String(120))
    room: Mapped[str | None] = mapped_column(String(30))


class ExamRoutineSlot(Base):
    __tablename__ = "exam_routine"
    id: Mapped[int] = mapped_column(primary_key=True)
    exam: Mapped[str] = mapped_column(String(80), index=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), index=True)
    subject: Mapped[str] = mapped_column(String(60))
    day: Mapped[date] = mapped_column(Date, index=True)
    start_time: Mapped[time] = mapped_column(Time)
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    room: Mapped[str | None] = mapped_column(String(30))


class Assignment(Base):
    __tablename__ = "assignments"
    id: Mapped[int] = mapped_column(primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    instructions: Mapped[str] = mapped_column(Text, default="")
    subject: Mapped[str | None] = mapped_column(String(60))
    due_date: Mapped[date | None] = mapped_column(Date)
    attachment_url: Mapped[str | None] = mapped_column(String(300))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    school_class: Mapped[SchoolClass] = relationship(lazy="joined")

    @property
    def class_label(self) -> str:
        return self.school_class.label


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("assignment_id", "student_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id", ondelete="CASCADE"), index=True)
    text: Mapped[str | None] = mapped_column(Text)
    file_url: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(10), default="submitted")  # submitted|reviewed
    feedback: Mapped[str | None] = mapped_column(Text)
    grade: Mapped[str | None] = mapped_column(String(20))
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    student: Mapped[StudentProfile] = relationship(lazy="joined")

    @property
    def student_name(self) -> str:
        return self.student.full_name


class Material(Base):
    __tablename__ = "materials"
    id: Mapped[int] = mapped_column(primary_key=True)
    class_id: Mapped[int | None] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(15), default="note")  # note|pdf|practice|video
    subject: Mapped[str | None] = mapped_column(String(60))
    file_url: Mapped[str | None] = mapped_column(String(300))
    link: Mapped[str | None] = mapped_column(String(400))
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


# ───────────── community ─────────────

class Channel(Base):
    __tablename__ = "channels"
    __table_args__ = (UniqueConstraint("class_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    class_id: Mapped[int | None] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), index=True)  # None = school-wide
    name: Mapped[str] = mapped_column(String(40))
    description: Mapped[str | None] = mapped_column(String(200))
    announcement_only: Mapped[bool] = mapped_column(Boolean, default=False)
    school_class: Mapped[SchoolClass | None] = relationship(lazy="joined")

    @property
    def class_label(self) -> str | None:
        return self.school_class.label if self.school_class else None


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_channel_id_id", "channel_id", "id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    body: Mapped[str] = mapped_column(Text)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    user: Mapped[User | None] = relationship(lazy="joined")

    @property
    def author_name(self) -> str:
        return self.user.full_name if self.user else "Deleted user"

    @property
    def author_role(self) -> str:
        return self.user.role if self.user else "public"


class MessageReport(Base):
    __tablename__ = "message_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    reporter_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reason: Mapped[str] = mapped_column(String(300))
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    message: Mapped[Message] = relationship(lazy="joined")

    @property
    def message_body(self) -> str:
        return self.message.body

    @property
    def channel_id(self) -> int:
        return self.message.channel_id


class ChannelRestriction(Base):
    __tablename__ = "channel_restrictions"
    __table_args__ = (UniqueConstraint("channel_id", "user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    until: Mapped[datetime | None] = mapped_column(DateTime)  # None = until lifted
    reason: Mapped[str | None] = mapped_column(String(200))


# ───────────── audit ─────────────

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(60), index=True)
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(40))
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    actor: Mapped[User | None] = relationship(lazy="joined")

    @property
    def actor_name(self) -> str | None:
        return self.actor.full_name if self.actor else None
