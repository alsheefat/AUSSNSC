"""Class/section channels: REST + WebSocket live chat + teacher moderation."""
import asyncio
import json
from datetime import timedelta

from fastapi import (APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect)
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import SessionLocal, get_db
from ..deps import (audit, current_user, get_or_404, teacher_class_ids, user_from_token,
                    visible_class_ids)
from ..models import (Channel, ChannelRestriction, Message, MessageReport, StudentProfile, User)
from ..schemas import (ChannelOut, MessageIn, MessageOut, Msg, ReportIn, ReportOut, RestrictionIn)
from ..security import limiter
from ..utils import utcnow

router = APIRouter(tags=["Community"])


# ───────────── permissions ─────────────

def _readable(user: User, ch: Channel, visible: set[int] | None) -> bool:
    """`visible` = classes the user may read (None = every class, i.e. admin)."""
    if user.role == "admin":
        return True
    if user.role == "public":
        return False
    if ch.class_id is None:                       # school-wide channel
        return True
    return visible is not None and ch.class_id in visible


def _can_read(db: Session, user: User, ch: Channel) -> bool:
    return _readable(user, ch, visible_class_ids(db, user))


def _is_restricted(r: ChannelRestriction | None) -> bool:
    return bool(r and (r.until is None or r.until >= utcnow()))


def _restricted(db: Session, user: User, ch: Channel) -> bool:
    r = db.scalar(select(ChannelRestriction).where(ChannelRestriction.channel_id == ch.id,
                                                   ChannelRestriction.user_id == user.id))
    return _is_restricted(r)


def _postable(user: User, ch: Channel, readable: bool, restricted: bool) -> bool:
    if not readable or user.role == "parent" or restricted:
        return False
    return not (ch.announcement_only and user.role not in ("teacher", "admin"))


def _can_post(db: Session, user: User, ch: Channel) -> bool:
    readable = _can_read(db, user, ch)
    return _postable(user, ch, readable, readable and _restricted(db, user, ch))


def _can_moderate(db: Session, user: User, ch: Channel) -> bool:
    if user.role == "admin":
        return True
    return user.role == "teacher" and ch.class_id is not None and ch.class_id in teacher_class_ids(db, user)


def _channel_or_403(db: Session, user: User, cid: int) -> Channel:
    ch = get_or_404(db, Channel, cid, "Channel")
    if not _can_read(db, user, ch):
        raise HTTPException(403, "You do not have access to this channel")
    return ch


# ───────────── live connections ─────────────

class Hub:
    def __init__(self):
        self.rooms: dict[int, set[WebSocket]] = {}

    def join(self, cid: int, ws: WebSocket):
        self.rooms.setdefault(cid, set()).add(ws)

    def leave(self, cid: int, ws: WebSocket):
        self.rooms.get(cid, set()).discard(ws)

    async def broadcast(self, cid: int, payload: dict):
        dead = []
        for ws in list(self.rooms.get(cid, ())):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.leave(cid, ws)


hub = Hub()  # single-process; use Redis pub/sub if you ever run several workers


def _post(db: Session, user: User, ch: Channel, body: str) -> Message:
    limiter.check(f"msg:{user.id}", 20, 30)  # flood control: 20 messages / 30 s
    if not _can_post(db, user, ch):
        raise HTTPException(403, "You cannot post in this channel")
    m = Message(channel_id=ch.id, user_id=user.id, body=body)
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


# ───────────── REST ─────────────

@router.get("/channels", response_model=list[ChannelOut])
def my_channels(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role == "public":
        return []
    visible = visible_class_ids(db, user)                       # one query, not one per channel
    restricted = {r.channel_id: r for r in db.scalars(
        select(ChannelRestriction).where(ChannelRestriction.user_id == user.id))}
    out = []
    for ch in db.scalars(select(Channel).order_by(Channel.class_id, Channel.id)).unique():
        if _readable(user, ch, visible):
            item = ChannelOut.model_validate(ch)
            item.can_post = _postable(user, ch, True, _is_restricted(restricted.get(ch.id)))
            out.append(item)
    return out


@router.get("/channels/{cid}/messages", response_model=list[MessageOut])
def messages(cid: int, before_id: int | None = None, limit: int = Query(40, ge=1, le=100),
             user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Newest first. Page backwards with before_id=<oldest id you have>."""
    _channel_or_403(db, user, cid)
    stmt = select(Message).where(Message.channel_id == cid, Message.deleted.is_(False))
    if before_id:
        stmt = stmt.where(Message.id < before_id)
    return db.scalars(stmt.order_by(Message.id.desc()).limit(limit)).unique().all()


@router.get("/channels/{cid}/pinned", response_model=list[MessageOut])
def pinned(cid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _channel_or_403(db, user, cid)
    return db.scalars(select(Message).where(Message.channel_id == cid, Message.pinned.is_(True),
                                            Message.deleted.is_(False)).order_by(Message.id.desc())).unique().all()


@router.post("/channels/{cid}/messages", response_model=MessageOut, status_code=201)
async def send_message(cid: int, body: MessageIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ch = _channel_or_403(db, user, cid)
    m = _post(db, user, ch, body.body)
    out = MessageOut.model_validate(m)
    await hub.broadcast(cid, {"type": "message", "message": json.loads(out.model_dump_json())})
    return out


@router.delete("/messages/{mid}", response_model=Msg)
async def delete_message(mid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = get_or_404(db, Message, mid, "Message")
    ch = db.get(Channel, m.channel_id)
    if m.user_id != user.id and not _can_moderate(db, user, ch):
        raise HTTPException(403, "You cannot delete this message")
    m.deleted, m.pinned = True, False
    if m.user_id != user.id:
        audit(db, user, "message.delete", "message", mid, f"channel {ch.id}")
    db.commit()
    await hub.broadcast(ch.id, {"type": "deleted", "message_id": mid})
    return Msg(detail="Message deleted")


@router.post("/messages/{mid}/report", response_model=Msg, status_code=201)
def report_message(mid: int, body: ReportIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = get_or_404(db, Message, mid, "Message")
    _channel_or_403(db, user, m.channel_id)
    if db.scalar(select(MessageReport.id).where(MessageReport.message_id == mid, MessageReport.reporter_id == user.id)):
        raise HTTPException(409, "You already reported this message")
    db.add(MessageReport(message_id=mid, reporter_id=user.id, reason=body.reason))
    db.commit()
    return Msg(detail="Thanks - a teacher or admin will review this")


# ───────────── moderation (teacher of that class, or admin) ─────────────

def _moderator_channel_ids(db: Session, user: User) -> list[int] | None:
    if user.role == "admin":
        return None
    if user.role != "teacher":
        raise HTTPException(403, "Moderation is for teachers and admins")
    cls = teacher_class_ids(db, user)
    return list(db.scalars(select(Channel.id).where(Channel.class_id.in_(list(cls) or [-1]))))


@router.get("/moderation/reports", response_model=list[ReportOut])
def reports(resolved: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ids = _moderator_channel_ids(db, user)
    stmt = select(MessageReport).join(Message, Message.id == MessageReport.message_id).where(
        MessageReport.resolved.is_(resolved))
    if ids is not None:
        stmt = stmt.where(Message.channel_id.in_(ids or [-1]))
    return db.scalars(stmt.order_by(MessageReport.id.desc()).limit(100)).unique().all()


@router.post("/moderation/reports/{rid}/resolve", response_model=Msg)
def resolve_report(rid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    r = get_or_404(db, MessageReport, rid, "Report")
    if not _can_moderate(db, user, db.get(Channel, r.message.channel_id)):
        raise HTTPException(403, "You cannot moderate this channel")
    r.resolved = True
    db.commit()
    return Msg(detail="Report resolved")


@router.post("/messages/{mid}/pin", response_model=MessageOut)
async def toggle_pin(mid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = get_or_404(db, Message, mid, "Message")
    ch = db.get(Channel, m.channel_id)
    if not _can_moderate(db, user, ch):
        raise HTTPException(403, "Only teachers of this class and admins can pin messages")
    m.pinned = not m.pinned
    db.commit()
    out = MessageOut.model_validate(m)
    await hub.broadcast(ch.id, {"type": "pinned", "message": json.loads(out.model_dump_json())})
    return out


@router.post("/channels/{cid}/restrictions", response_model=Msg, status_code=201)
def restrict_member(cid: int, body: RestrictionIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ch = get_or_404(db, Channel, cid, "Channel")
    if not _can_moderate(db, user, ch):
        raise HTTPException(403, "You cannot moderate this channel")
    target = get_or_404(db, User, body.user_id, "User")
    if target.role in ("teacher", "admin"):
        raise HTTPException(403, "Teachers and admins cannot be restricted")
    until = utcnow() + timedelta(minutes=body.minutes) if body.minutes else None
    r = db.scalar(select(ChannelRestriction).where(ChannelRestriction.channel_id == cid, ChannelRestriction.user_id == target.id))
    if r:
        r.until, r.reason = until, body.reason
    else:
        db.add(ChannelRestriction(channel_id=cid, user_id=target.id, until=until, reason=body.reason))
    audit(db, user, "channel.restrict", "user", target.id, f"channel {cid}: {body.reason or ''}")
    db.commit()
    return Msg(detail="Member restricted from posting")


@router.delete("/channels/{cid}/restrictions/{user_id}", response_model=Msg)
def lift_restriction(cid: int, user_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ch = get_or_404(db, Channel, cid, "Channel")
    if not _can_moderate(db, user, ch):
        raise HTTPException(403, "You cannot moderate this channel")
    r = db.scalar(select(ChannelRestriction).where(ChannelRestriction.channel_id == cid, ChannelRestriction.user_id == user_id))
    if r:
        db.delete(r)
        db.commit()
    return Msg(detail="Restriction lifted")


# ───────────── WebSocket ─────────────
# ws://HOST/api/v1/ws/channels/{id}   - send header "Authorization: Bearer <access>" (OkHttp supports
# this) or append ?token=<access>. Client sends {"body": "hello"}; server pushes
# {"type": "message"|"deleted"|"pinned"|"error", ...}.

@router.websocket("/ws/channels/{cid}")
async def channel_socket(ws: WebSocket, cid: int):
    auth = ws.headers.get("authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else ws.query_params.get("token", "")
    db = SessionLocal()
    try:
        user = user_from_token(token, db) if token else None
        ch = db.get(Channel, cid)
        if not user or not ch or not _can_read(db, user, ch):
            await ws.close(code=4401 if not user else 4403)
            return
        await ws.accept()
        hub.join(cid, ws)
        try:
            while True:
                data = await ws.receive_json()
                try:
                    body = MessageIn(body=str(data.get("body", ""))).body
                    m = _post(db, user, ch, body)
                    out = MessageOut.model_validate(m)
                    await hub.broadcast(cid, {"type": "message", "message": json.loads(out.model_dump_json())})
                except HTTPException as e:
                    await ws.send_json({"type": "error", "detail": e.detail})
                except ValueError:
                    await ws.send_json({"type": "error", "detail": "Message is empty or too long"})
        except WebSocketDisconnect:
            pass
        finally:
            hub.leave(cid, ws)
    finally:
        db.close()
