import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models, repo
from app.database import get_db
from app.deps import require_leadership
from app.schemas import AnnouncementCounts, AnnouncementCreate, AnnouncementSummary

router = APIRouter(prefix="/announcements", tags=["announcements"])


def _counts(db: Session, announcement: models.Announcement) -> AnnouncementCounts:
    row = db.execute(
        select(
            func.count(models.Recipient.id),
            func.count().filter(models.Recipient.status.in_(["sent", "read", "acknowledged"])),
            func.count().filter(models.Recipient.status.in_(["read", "acknowledged"])),
            func.count().filter(models.Recipient.status == "acknowledged"),
        ).where(models.Recipient.announcement_id == announcement.id)
    ).one()
    total, sent, read, acked = row
    return AnnouncementCounts(
        id=announcement.id,
        title=announcement.title,
        body=announcement.body,
        classification_filter=announcement.classification_filter,
        needs_ack=announcement.needs_ack,
        sent_at=announcement.sent_at,
        created_at=announcement.created_at,
        total_recipients=total,
        sent_count=sent,
        read_count=read,
        acknowledged_count=acked,
    )


def _run_send(db: Session, announcement: models.Announcement, account: models.Account) -> None:
    """Fan out + dispatch. Safe to call again on an announcement that's already
    partway sent (or fully sent) -- see fan_out_recipients and the status-scoped
    update below. This is synchronous for the exercise's seed-data scale; Part A
    describes the async worker version for 22,400-member locals."""
    send_job = announcement.send_job
    if send_job.status == "completed":
        return  # nothing to do: already fully sent, this is an idempotent no-op

    send_job.status = "running"
    send_job.started_at = send_job.started_at or datetime.now(timezone.utc)

    members = repo.get_members_for_send(db, account, announcement.classification_filter)
    repo.fan_out_recipients(db, announcement.id, [m.id for m in members])
    db.flush()

    now = datetime.now(timezone.utc)
    pending = db.execute(
        select(models.Recipient).where(
            models.Recipient.announcement_id == announcement.id,
            models.Recipient.status == "pending",
        )
    ).scalars()
    sent_count = 0
    for recipient in pending:
        # "Push" is logged, not actually delivered -- see README/DESIGN "what I cut".
        recipient.status = "sent"
        recipient.sent_at = now
        sent_count += 1
    print(f"[push] announcement={announcement.id} dispatched to {sent_count} recipients")

    announcement.sent_at = announcement.sent_at or now
    send_job.status = "completed"
    send_job.finished_at = now


@router.post("", response_model=AnnouncementCounts)
def create_and_send(
    payload: AnnouncementCreate,
    db: Session = Depends(get_db),
    account: models.Account = Depends(require_leadership),
) -> AnnouncementCounts:
    existing = db.execute(
        select(models.Announcement).where(
            models.Announcement.created_by_id == account.id,
            models.Announcement.idempotency_key == payload.idempotency_key,
        )
    ).scalar_one_or_none()

    if existing is None:
        announcement = models.Announcement(
            local_id=account.local_id,
            created_by_id=account.id,
            title=payload.title,
            body=payload.body,
            classification_filter=payload.classification_filter,
            needs_ack=payload.needs_ack,
            idempotency_key=payload.idempotency_key,
        )
        db.add(announcement)
        try:
            db.flush()  # obtain announcement.id; also surfaces a concurrent-retry race as IntegrityError
        except IntegrityError:
            # Another request with the same idempotency_key committed first --
            # this is that same retry, so fetch and treat it as the winner.
            db.rollback()
            announcement = db.execute(
                select(models.Announcement).where(
                    models.Announcement.created_by_id == account.id,
                    models.Announcement.idempotency_key == payload.idempotency_key,
                )
            ).scalar_one()
        else:
            db.add(models.SendJob(announcement_id=announcement.id))
            db.flush()
    else:
        announcement = existing

    _run_send(db, announcement, account)
    db.commit()
    db.refresh(announcement)
    return _counts(db, announcement)


@router.get("", response_model=list[AnnouncementSummary])
def list_announcements(
    db: Session = Depends(get_db),
    account: models.Account = Depends(require_leadership),
) -> list[AnnouncementSummary]:
    return [
        AnnouncementSummary(id=a.id, title=a.title, sent_at=a.sent_at, created_at=a.created_at)
        for a in repo.list_announcements_for_account(db, account)
    ]


@router.get("/{announcement_id}", response_model=AnnouncementCounts)
def get_announcement(
    announcement_id: uuid.UUID,
    db: Session = Depends(get_db),
    account: models.Account = Depends(require_leadership),
) -> AnnouncementCounts:
    announcement = repo.get_announcement_for_account(db, account, announcement_id)
    return _counts(db, announcement)
