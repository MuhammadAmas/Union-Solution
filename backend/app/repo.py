"""Every query against a tenant-scoped table (members, announcements, recipients)
goes through one of these functions, never through a raw db.query()/db.get() in a
router. That's the actual enforcement mechanism for Rule 1: a new endpoint added
next year either imports and uses these (and inherits the scoping automatically)
or it visibly writes its own query -- which stands out in review as the thing to
double-check, instead of silently being "just another endpoint" that forgot a
`.filter(local_id=...)` clause somewhere in its body.
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app import models


def get_announcement_for_account(
    db: Session, account: models.Account, announcement_id: uuid.UUID
) -> models.Announcement:
    stmt = select(models.Announcement).where(
        models.Announcement.id == announcement_id,
        models.Announcement.local_id == account.local_id,
    )
    announcement = db.execute(stmt).scalar_one_or_none()
    if announcement is None:
        # Same 404 whether the row doesn't exist or belongs to another local --
        # a leadership account for Local A gets no signal that Local B's
        # announcement id is even valid.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Announcement not found")
    return announcement


def list_announcements_for_account(db: Session, account: models.Account) -> list[models.Announcement]:
    stmt = (
        select(models.Announcement)
        .where(models.Announcement.local_id == account.local_id)
        .order_by(models.Announcement.created_at.desc())
    )
    return list(db.execute(stmt).scalars().all())


def get_members_for_send(
    db: Session, account: models.Account, classification_filter: str | None
) -> list[models.Member]:
    stmt = select(models.Member).where(
        models.Member.local_id == account.local_id,
        models.Member.status == "active",
    )
    if classification_filter:
        stmt = stmt.where(models.Member.classification == classification_filter)
    return list(db.execute(stmt).scalars().all())


def get_recipient_for_member_account(
    db: Session, account: models.Account, recipient_id: uuid.UUID
) -> models.Recipient:
    """A member account may only ever touch its OWN recipient row -- scoped by
    member_id, not just local_id, since two members share a local."""
    stmt = select(models.Recipient).where(
        models.Recipient.id == recipient_id,
        models.Recipient.member_id == account.member_id,
    )
    recipient = db.execute(stmt).scalar_one_or_none()
    if recipient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recipient not found")
    return recipient


def fan_out_recipients(db: Session, announcement_id: uuid.UUID, member_ids: list[uuid.UUID]) -> None:
    """Insert one recipient row per targeted member, skipping any that already
    exist for this announcement. This is what makes Rule 2 hold structurally: a
    retried send, or a worker resuming after a crash mid-fan-out, re-runs this
    exact call and the DB's unique constraint on (announcement_id, member_id)
    -- not any in-memory flag -- silently no-ops the rows already there."""
    if not member_ids:
        return
    rows = [{"announcement_id": announcement_id, "member_id": mid} for mid in member_ids]
    insert_fn = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    stmt = insert_fn(models.Recipient).values(rows)
    stmt = stmt.on_conflict_do_nothing(index_elements=["announcement_id", "member_id"])
    db.execute(stmt)


def list_inbox_for_member_account(db: Session, account: models.Account) -> list[models.Recipient]:
    stmt = (
        select(models.Recipient)
        .join(models.Announcement)
        .where(models.Recipient.member_id == account.member_id)
        .order_by(models.Announcement.created_at.desc())
    )
    return list(db.execute(stmt).scalars().all())
