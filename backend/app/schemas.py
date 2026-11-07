import json
from datetime import date, datetime, time, timezone
from typing import Annotated, Literal

from pydantic import (BaseModel, ConfigDict, Field, PlainSerializer, field_validator,
                      model_validator)

from .utils import normalize_email, normalize_phone


def _iso(d: datetime) -> str:
    return d.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


UTC = Annotated[datetime, PlainSerializer(_iso, return_type=str)]
Lang = Literal["en", "bn"]
Role = Literal["public", "student", "parent", "teacher", "admin"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ───────────── auth ─────────────

class UserOut(ORM):
    id: int
    full_name: str
    phone: str | None
    email: str | None
    role: str
    is_active: bool
    phone_verified: bool
    email_verified: bool
    language: str
    theme: str
    created_at: UTC


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut


class RegisterIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    phone: str | None = None
    email: str | None = None
    password: str = Field(min_length=8, max_length=128)
    language: Lang = "en"

    @field_validator("phone")
    @classmethod
    def _p(cls, v):
        return normalize_phone(v) if v else None

    @field_validator("email")
    @classmethod
    def _e(cls, v):
        return normalize_email(v) if v else None

    @model_validator(mode="after")
    def _one_contact(self):
        if not self.phone and not self.email:
            raise ValueError("Provide a phone number or an email address")
        return self


class LoginIn(BaseModel):
    identifier: str = Field(description="Phone number or email")
    password: str


class GoogleLoginIn(BaseModel):
    id_token: str = Field(min_length=20, description="Firebase ID token from the app")


class RefreshIn(BaseModel):
    refresh_token: str


class OtpRequestIn(BaseModel):
    target: str
    purpose: Literal["verify", "reset"]


class OtpVerifyIn(BaseModel):
    target: str
    code: str = Field(min_length=6, max_length=6)


class PasswordResetIn(BaseModel):
    target: str
    code: str = Field(min_length=6, max_length=6)
    new_password: str = Field(min_length=8, max_length=128)


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class ProfileUpdateIn(BaseModel):
    full_name: str | None = Field(None, min_length=2, max_length=120)
    language: Lang | None = None
    theme: Literal["light", "dark", "system"] | None = None


class DeviceIn(BaseModel):
    token: str = Field(min_length=10, max_length=300)
    platform: Literal["android", "ios"] = "android"


class Msg(BaseModel):
    detail: str


# ───────────── school structure ─────────────

class ClassOut(ORM):
    id: int
    name: str
    section: str
    label: str


class ClassIn(BaseModel):
    name: str = Field(min_length=1, max_length=20)
    section: str = Field(min_length=1, max_length=10)


class StudentOut(ORM):
    id: int
    user_id: int | None
    full_name: str
    class_id: int
    class_label: str
    roll: int
    student_code: str | None
    guardian_phone: str | None


class StudentIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    class_id: int
    roll: int = Field(ge=1)
    student_code: str | None = None
    guardian_phone: str | None = None
    user_id: int | None = None


class StudentPatch(BaseModel):
    full_name: str | None = None
    class_id: int | None = None
    roll: int | None = Field(None, ge=1)
    student_code: str | None = None
    guardian_phone: str | None = None
    user_id: int | None = None


class TeacherPublic(ORM):
    id: int
    full_name: str
    designation: str | None
    department: str | None
    photo_url: str | None
    phone: str | None = None   # only populated when contact_public
    email: str | None = None


class TeacherAdminOut(TeacherPublic):
    user_id: int | None
    contact_public: bool
    phone: str | None
    email: str | None


class TeacherIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    designation: str | None = None
    department: str | None = None
    phone: str | None = None
    email: str | None = None
    photo_url: str | None = None
    contact_public: bool = False
    user_id: int | None = None


class TeacherClassIn(BaseModel):
    class_id: int
    subject: str = ""


class TeacherClassOut(ORM):
    id: int
    class_id: int
    class_label: str
    subject: str


class ParentLinkIn(BaseModel):
    student_name: str = Field(min_length=2, max_length=120)
    class_name: str = Field(min_length=1, max_length=30)
    roll: int = Field(ge=1)
    relationship: str = Field(min_length=2, max_length=30)


class ParentLinkOut(ORM):
    id: int
    parent_id: int
    parent_name: str
    student_id: int | None
    student_name: str | None
    claimed_name: str
    claimed_class: str
    claimed_roll: int
    relationship_: str = Field(serialization_alias="relationship")
    status: str
    created_at: UTC

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ParentDecisionIn(BaseModel):
    approve: bool
    student_id: int | None = None  # pick the matching student if auto-match failed


# ───────────── content ─────────────

class NoticeIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    body: str = Field(min_length=1)
    category: str = "general"
    pinned: bool = False
    published: bool = True
    attachment_url: str | None = None
    send_push: bool = False


class NoticeOut(ORM):
    id: int
    title: str
    body: str
    category: str
    pinned: bool
    published: bool
    attachment_url: str | None
    created_at: UTC


class EventIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    start_date: date
    end_date: date | None = None
    kind: Literal["event", "exam", "holiday"] = "event"
    description: str | None = None


class EventOut(ORM):
    id: int
    title: str
    start_date: date
    end_date: date | None
    kind: str
    description: str | None


class AlbumIn(BaseModel):
    title: str = Field(min_length=2, max_length=150)
    description: str | None = None


class PhotoIn(BaseModel):
    url: str
    caption: str | None = None


class PhotoOut(ORM):
    id: int
    url: str
    caption: str | None


class AlbumOut(ORM):
    id: int
    title: str
    description: str | None
    cover_url: str | None
    photo_count: int


class AlbumDetail(AlbumOut):
    photos: list[PhotoOut]


class ContentIn(BaseModel):
    data: dict


class AdmissionIn(BaseModel):
    applicant_name: str = Field(min_length=2, max_length=120)
    guardian_name: str = Field(min_length=2, max_length=120)
    phone: str
    email: str | None = None
    class_applying: str = Field(min_length=1, max_length=30)
    previous_school: str | None = None
    message: str | None = Field(None, max_length=2000)

    @field_validator("phone")
    @classmethod
    def _p(cls, v):
        return normalize_phone(v)

    @field_validator("email")
    @classmethod
    def _e(cls, v):
        return normalize_email(v) if v else None


class AdmissionOut(ORM):
    id: int
    applicant_name: str
    guardian_name: str
    phone: str
    email: str | None
    class_applying: str
    previous_school: str | None
    message: str | None
    status: str
    created_at: UTC


class StatusIn(BaseModel):
    status: Literal["new", "contacted", "accepted", "rejected"]


# ───────────── academics ─────────────

class SubjectMark(BaseModel):
    subject: str
    marks: float | None = None
    grade: str | None = None


class ResultIn(BaseModel):
    exam: str = Field(min_length=2, max_length=80)
    exam_year: int = Field(ge=2000, le=2100)
    class_name: str
    section: str | None = None
    roll: int = Field(ge=1)
    student_name: str = Field(min_length=2, max_length=120)
    gpa: float | None = Field(None, ge=0, le=5)
    grade: str | None = None
    total_marks: float | None = None
    status: Literal["passed", "failed", "withheld"] = "passed"
    subjects: list[SubjectMark] = []
    published: bool = False


class ResultOut(BaseModel):
    id: int
    exam: str
    exam_year: int
    class_name: str
    section: str | None
    roll: int
    student_name: str
    gpa: float | None
    grade: str | None
    total_marks: float | None
    status: str
    subjects: list[SubjectMark]
    published: bool

    @classmethod
    def of(cls, r) -> "ResultOut":
        return cls(id=r.id, exam=r.exam, exam_year=r.exam_year, class_name=r.class_name,
                   section=r.section, roll=r.roll, student_name=r.student_name, gpa=r.gpa,
                   grade=r.grade, total_marks=r.total_marks, status=r.status,
                   subjects=json.loads(r.subjects or "[]"), published=r.published)


class PublishIn(BaseModel):
    exam: str
    exam_year: int
    published: bool


AttStatus = Literal["present", "absent", "late"]


class AttendanceRecord(BaseModel):
    student_id: int
    status: AttStatus


class AttendanceIn(BaseModel):
    class_id: int
    day: date
    records: list[AttendanceRecord] = Field(min_length=1, max_length=200)


class AttendanceDay(ORM):
    student_id: int
    day: date
    status: str


class AttendanceSummary(BaseModel):
    present: int
    absent: int
    late: int
    total_days: int
    rate_percent: float
    records: list[AttendanceDay]


class RoutineSlotIn(BaseModel):
    weekday: int = Field(ge=0, le=6, description="0=Sunday … 6=Saturday")
    start_time: time
    end_time: time | None = None
    subject: str
    teacher_name: str | None = None
    room: str | None = None


class RoutineSlotOut(RoutineSlotIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class ExamSlotIn(BaseModel):
    exam: str
    class_id: int
    subject: str
    day: date
    start_time: time
    duration_minutes: int | None = None
    room: str | None = None


class ExamSlotOut(ExamSlotIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class AssignmentIn(BaseModel):
    class_id: int
    title: str = Field(min_length=2, max_length=200)
    instructions: str = ""
    subject: str | None = None
    due_date: date | None = None
    attachment_url: str | None = None


class AssignmentOut(ORM):
    id: int
    class_id: int
    class_label: str
    title: str
    instructions: str
    subject: str | None
    due_date: date | None
    attachment_url: str | None
    created_at: UTC
    my_submission_status: str | None = None


class SubmissionIn(BaseModel):
    text: str | None = Field(None, max_length=10000)
    file_url: str | None = None

    @model_validator(mode="after")
    def _something(self):
        if not (self.text or self.file_url):
            raise ValueError("Add some text or attach a file")
        return self


class SubmissionOut(ORM):
    id: int
    assignment_id: int
    student_id: int
    student_name: str
    text: str | None
    file_url: str | None
    status: str
    feedback: str | None
    grade: str | None
    submitted_at: UTC


class ReviewIn(BaseModel):
    feedback: str | None = Field(None, max_length=3000)
    grade: str | None = Field(None, max_length=20)


class MaterialIn(BaseModel):
    class_id: int | None = None
    title: str = Field(min_length=2, max_length=200)
    kind: Literal["note", "pdf", "practice", "video"] = "note"
    subject: str | None = None
    file_url: str | None = None
    link: str | None = None

    @model_validator(mode="after")
    def _has_content(self):
        if not (self.file_url or self.link):
            raise ValueError("Provide an uploaded file URL or a link")
        return self


class MaterialOut(ORM):
    id: int
    class_id: int | None
    title: str
    kind: str
    subject: str | None
    file_url: str | None
    link: str | None
    created_at: UTC


# ───────────── community ─────────────

class ChannelIn(BaseModel):
    class_id: int | None = None
    name: str = Field(min_length=2, max_length=40, pattern=r"^[a-z0-9][a-z0-9\-]*$")
    description: str | None = None
    announcement_only: bool = False


class ChannelPatch(BaseModel):
    description: str | None = None
    announcement_only: bool | None = None


class ChannelOut(ORM):
    id: int
    class_id: int | None
    class_label: str | None
    name: str
    description: str | None
    announcement_only: bool
    can_post: bool = False


class MessageIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)

    @field_validator("body")
    @classmethod
    def _strip(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Message is empty")
        return v


class MessageOut(ORM):
    id: int
    channel_id: int
    user_id: int | None
    author_name: str
    author_role: str
    body: str
    pinned: bool
    created_at: UTC


class ReportIn(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


class ReportOut(ORM):
    id: int
    message_id: int
    channel_id: int
    message_body: str
    reason: str
    resolved: bool
    created_at: UTC


class RestrictionIn(BaseModel):
    user_id: int
    minutes: int | None = Field(None, ge=1, le=60 * 24 * 365, description="Omit for until lifted")
    reason: str | None = Field(None, max_length=200)


# ───────────── admin ─────────────

class AdminUserPatch(BaseModel):
    full_name: str | None = Field(None, min_length=2, max_length=120)
    role: Role | None = None
    is_active: bool | None = None


class AdminPasswordIn(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


class AuditOut(ORM):
    id: int
    actor_id: int | None
    actor_name: str | None
    action: str
    entity: str
    entity_id: str | None
    detail: str | None
    created_at: UTC
