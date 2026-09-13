import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models, repo
from app.database import get_db
from app.deps import require_member
from app.schemas import InboxItem

router = APIRouter(tags=["recipients"])


def _to_inbox_item(recipient: models.Recipient) -> InboxItem:
    announcement = recipient.announcement
    return InboxItem(
        recipient_id=recipient.id,
        announcement_id=announcement.id,
        title=announcement.title,
        body=announcement.body,
        status=recipient.status,
        sent_at=recipient.sent_at,
        read_at=recipient.read_at,
        acknowledged_at=recipient.acknowledged_at,
    )


@router.get("/me/inbox", response_model=list[InboxItem])
def my_inbox(
    db: Session = Depends(get_db),
    account: models.Account = Depends(require_member),
) -> list[InboxItem]:
    return [_to_inbox_item(r) for r in repo.list_inbox_for_member_account(db, account)]


@router.post("/recipients/{recipient_id}/read", response_model=InboxItem)
def mark_read(
    recipient_id: uuid.UUID,
    db: Session = Depends(get_db),
    account: models.Account = Depends(require_member),
) -> InboxItem:
    recipient = repo.get_recipient_for_member_account(db, account, recipient_id)
    if recipient.read_at is None:
        recipient.read_at = datetime.now(timezone.utc)
        if recipient.status in ("pending", "sent"):
            recipient.status = "read"
    db.commit()
    db.refresh(recipient)
    return _to_inbox_item(recipient)


@router.post("/recipients/{recipient_id}/ack", response_model=InboxItem)
def mark_acknowledged(
    recipient_id: uuid.UUID,
    db: Session = Depends(get_db),
    account: models.Account = Depends(require_member),
) -> InboxItem:
    recipient = repo.get_recipient_for_member_account(db, account, recipient_id)
    now = datetime.now(timezone.utc)
    if recipient.read_at is None:
        recipient.read_at = now  # acknowledging implies having read it
    if recipient.acknowledged_at is None:
        recipient.acknowledged_at = now
        recipient.status = "acknowledged"
    db.commit()
    db.refresh(recipient)
    return _to_inbox_item(recipient)
