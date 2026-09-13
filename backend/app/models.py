import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Local(Base):
    __tablename__ = "locals"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    name: Mapped[str]

    members: Mapped[list["Member"]] = relationship(back_populates="local")


class Member(Base):
    """The union roster. Not a login identity -- see Account."""

    __tablename__ = "members"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    local_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locals.id"), index=True)
    full_name: Mapped[str]
    email: Mapped[str]
    classification: Mapped[str]
    status: Mapped[str] = mapped_column(default="active")  # active | retired | suspended

    local: Mapped["Local"] = relationship(back_populates="members")


class Account(Base):
    """Login identity. Separate from Member because a business manager isn't
    necessarily on the roster. `local_id` lives here directly (not derived via
    member_id) so every authorization check has one non-nullable field to filter on."""

    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    local_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locals.id"), index=True)
    member_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("members.id"), nullable=True)
    role: Mapped[str]  # leadership | member
    email: Mapped[str] = mapped_column(unique=True, index=True)
    password_hash: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=_now)

    local: Mapped["Local"] = relationship()
    member: Mapped["Member | None"] = relationship()


class AuthToken(Base):
    """Opaque bearer token, deliberately simple (no JWT) -- a token row we can
    revoke by deleting, which is all this exercise needs."""

    __tablename__ = "auth_tokens"

    token: Mapped[str] = mapped_column(primary_key=True, default=lambda: uuid.uuid4().hex)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)

    account: Mapped["Account"] = relationship()


class Announcement(Base):
    __tablename__ = "announcements"
    __table_args__ = (
        UniqueConstraint("created_by_id", "idempotency_key", name="uq_announcement_idempotency"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    local_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("locals.id"), index=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"))
    title: Mapped[str]
    body: Mapped[str]
    classification_filter: Mapped[str | None] = mapped_column(nullable=True)
    needs_ack: Mapped[bool] = mapped_column(default=False)
    # Client-generated, carried through retries of the same "Send" action so a
    # double-click or a retried request never creates a second announcement.
    idempotency_key: Mapped[str]
    sent_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=_now)

    local: Mapped["Local"] = relationship()
    send_job: Mapped["SendJob"] = relationship(back_populates="announcement", uselist=False)
    recipients: Mapped[list["Recipient"]] = relationship(back_populates="announcement")


class SendJob(Base):
    """One row per announcement, ever (unique on announcement_id). This is what
    makes retrying a stuck send, or a worker restarting mid-fan-out, a no-op at
    the job level instead of relying on any process's in-memory state."""

    __tablename__ = "send_jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    announcement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("announcements.id"), unique=True, index=True
    )
    status: Mapped[str] = mapped_column(default="pending")  # pending | running | completed | failed
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)

    announcement: Mapped["Announcement"] = relationship(back_populates="send_job")


class Recipient(Base):
    """One row per targeted member, created once at fan-out time and only ever
    updated after that (never re-inserted) -- the audience list and the status
    ledger are the same table."""

    __tablename__ = "recipients"
    __table_args__ = (
        UniqueConstraint("announcement_id", "member_id", name="uq_recipient_once_per_member"),
        Index("ix_recipients_announcement_status", "announcement_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid)
    announcement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("announcements.id"), index=True)
    member_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("members.id"), index=True)
    status: Mapped[str] = mapped_column(default="pending")  # pending | sent | read | acknowledged
    sent_at: Mapped[datetime | None] = mapped_column(nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(nullable=True)

    announcement: Mapped["Announcement"] = relationship(back_populates="recipients")
    member: Mapped["Member"] = relationship()
