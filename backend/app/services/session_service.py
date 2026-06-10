"""Session history persistence, retrieval and export."""
from __future__ import annotations

import json
from datetime import datetime
from io import BytesIO
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.core.exceptions import ResourceNotFoundError
from app.core.logging import get_logger
from app.db.models import Message, Session
from app.models.schemas import (
    MessageOut,
    MessageRole,
    SessionDetail,
    SessionSummary,
)

logger = get_logger(__name__)


class SessionService:
    """CRUD + export operations for chat/diagnosis sessions."""

    # ----- creation / retrieval ----- #
    def create_session(self, db: OrmSession, title: Optional[str] = None) -> SessionSummary:
        session = Session(title=title or "New Session")
        db.add(session)
        db.flush()
        logger.info("Created session %s", session.id)
        return self._to_summary(session, message_count=0)

    def list_sessions(self, db: OrmSession) -> list[SessionSummary]:
        counts = dict(
            db.execute(
                select(Message.session_id, func.count(Message.id)).group_by(Message.session_id)
            ).all()
        )
        sessions = db.execute(select(Session).order_by(Session.updated_at.desc())).scalars().all()
        return [self._to_summary(s, counts.get(s.id, 0)) for s in sessions]

    def get_session(self, db: OrmSession, session_id: int) -> SessionDetail:
        session = db.get(Session, session_id)
        if session is None:
            raise ResourceNotFoundError(f"Session {session_id} not found")
        messages = [self._to_message_out(m) for m in session.messages]
        return SessionDetail(
            id=session.id,
            title=session.title,
            created_at=session.created_at,
            updated_at=session.updated_at,
            message_count=len(messages),
            messages=messages,
        )

    def delete_session(self, db: OrmSession, session_id: int) -> None:
        session = db.get(Session, session_id)
        if session is None:
            raise ResourceNotFoundError(f"Session {session_id} not found")
        db.delete(session)

    def ensure_session(self, db: OrmSession, session_id: Optional[int]) -> Session:
        """Return an existing session or create a new one."""
        if session_id is not None:
            session = db.get(Session, session_id)
            if session is None:
                raise ResourceNotFoundError(f"Session {session_id} not found")
            return session
        session = Session(title="New Session")
        db.add(session)
        db.flush()
        return session

    # ----- messages ----- #
    def add_message(
        self,
        db: OrmSession,
        session_id: int,
        role: MessageRole,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> MessageOut:
        message = Message(
            session_id=session_id,
            role=role.value if isinstance(role, MessageRole) else str(role),
            content=content,
            meta_json=json.dumps(metadata, default=str) if metadata else None,
        )
        db.add(message)
        db.flush()
        # Update title from the first user message for convenience.
        session = db.get(Session, session_id)
        if session is not None:
            session.updated_at = datetime.utcnow()
            if session.title == "New Session" and role == MessageRole.user:
                session.title = (content[:60] + "…") if len(content) > 60 else content
        return self._to_message_out(message)

    # ----- export ----- #
    def export_json(self, db: OrmSession, session_id: int) -> dict[str, Any]:
        detail = self.get_session(db, session_id)
        return json.loads(detail.model_dump_json())

    def export_pdf(self, db: OrmSession, session_id: int) -> bytes:
        detail = self.get_session(db, session_id)
        return _render_pdf(detail)

    # ----- helpers ----- #
    @staticmethod
    def _to_summary(session: Session, message_count: int) -> SessionSummary:
        return SessionSummary(
            id=session.id,
            title=session.title,
            created_at=session.created_at,
            updated_at=session.updated_at,
            message_count=message_count,
        )

    @staticmethod
    def _to_message_out(message: Message) -> MessageOut:
        metadata: Optional[dict[str, Any]] = None
        if message.meta_json:
            try:
                metadata = json.loads(message.meta_json)
            except json.JSONDecodeError:
                metadata = None
        return MessageOut(
            id=message.id,
            role=MessageRole(message.role) if message.role in MessageRole._value2member_map_ else MessageRole.system,
            content=message.content,
            created_at=message.created_at,
            metadata=metadata,
        )


def _render_pdf(detail: SessionDetail) -> bytes:
    """Render a session to a simple PDF using reportlab."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
    )

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
    )
    styles = getSampleStyleSheet()
    role_style = {
        "user": ParagraphStyle("user", parent=styles["BodyText"], textColor="#1d4ed8", spaceBefore=8),
        "assistant": ParagraphStyle("assistant", parent=styles["BodyText"], textColor="#047857", spaceBefore=8),
        "system": ParagraphStyle("system", parent=styles["BodyText"], textColor="#6b7280", spaceBefore=8),
    }

    story: list[Any] = [
        Paragraph(f"Cache AI Assistant - Session #{detail.id}", styles["Title"]),
        Paragraph(f"<b>{_esc(detail.title)}</b>", styles["Heading2"]),
        Paragraph(f"Created: {detail.created_at:%Y-%m-%d %H:%M} UTC", styles["Normal"]),
        Spacer(1, 8 * mm),
    ]
    for msg in detail.messages:
        style = role_style.get(msg.role.value, styles["BodyText"])
        story.append(Paragraph(f"<b>{msg.role.value.upper()}</b> · {msg.created_at:%H:%M:%S}", styles["Normal"]))
        story.append(Paragraph(_esc(msg.content).replace("\n", "<br/>"), style))
    doc.build(story)
    return buffer.getvalue()


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
