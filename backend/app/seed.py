"""Re-runnable seed script: `python -m app.seed` (or `docker compose exec backend
python -m app.seed`). Wipes and recreates the demo data every time it runs, so
it's safe to run again after schema changes or a fresh volume.
"""

import random
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app import models
from app.database import Base, SessionLocal, engine
from app.security import hash_password

# Fixed (not random) so the README's Test Accounts section stays valid across
# every re-run of this script -- a reviewer never has to re-read ids from stdout.
LOCAL_27_ID = uuid.UUID("00000000-0000-0000-0000-000000000027")
LOCAL_9_ID = uuid.UUID("00000000-0000-0000-0000-000000000009")
MEMBER_27_ID = uuid.UUID("10000000-0000-0000-0000-000000000027")
MEMBER_9_ID = uuid.UUID("10000000-0000-0000-0000-000000000009")
SENT_ANNOUNCEMENT_ID = uuid.UUID("20000000-0000-0000-0000-000000000001")

CLASSIFICATIONS = [
    "Journeyman Wireman",
    "Apprentice 3rd Year",
    "Apprentice 1st Year",
    "Foreman",
]

FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
    "David", "Elizabeth", "William", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Charles", "Karen", "Carlos", "Maria", "Luis", "Angela",
]
LAST_NAMES = [
    "Okafor", "Nguyen", "Smith", "Johnson", "Garcia", "Martinez", "Brown", "Davis",
    "Rodriguez", "Wilson", "Anderson", "Taylor", "Thomas", "Moore", "Jackson", "Martin",
]


def _random_name(rng: random.Random) -> str:
    return f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"


def _make_members(rng: random.Random, local: models.Local, count: int) -> list[models.Member]:
    members = []
    for i in range(count):
        name = _random_name(rng)
        members.append(
            models.Member(
                local_id=local.id,
                full_name=name,
                email=f"{name.lower().replace(' ', '.')}.{i}@example.org",
                classification=rng.choice(CLASSIFICATIONS),
                status="active" if rng.random() > 0.03 else "retired",
            )
        )
    return members


def wipe(db: Session) -> None:
    for model in [
        models.Recipient,
        models.SendJob,
        models.Announcement,
        models.AuthToken,
        models.Account,
        models.Member,
        models.Local,
    ]:
        db.execute(delete(model))
    db.commit()


def seed() -> dict:
    Base.metadata.create_all(bind=engine)
    rng = random.Random(42)
    db = SessionLocal()
    try:
        wipe(db)

        local_27 = models.Local(id=LOCAL_27_ID, name="Local 27")
        local_9 = models.Local(id=LOCAL_9_ID, name="Local 9")
        db.add_all([local_27, local_9])
        db.flush()

        members_27 = _make_members(rng, local_27, 2000)
        members_9 = _make_members(rng, local_9, 200)
        members_27[0].id = MEMBER_27_ID
        members_9[0].id = MEMBER_9_ID
        db.add_all(members_27 + members_9)
        db.flush()

        leadership_27 = models.Account(
            local_id=local_27.id,
            role="leadership",
            email="denise@local27.example.org",
            password_hash=hash_password("password123"),
        )
        member_account_27 = models.Account(
            local_id=local_27.id,
            member_id=members_27[0].id,
            role="member",
            email=members_27[0].email,
            password_hash=hash_password("password123"),
        )
        leadership_9 = models.Account(
            local_id=local_9.id,
            role="leadership",
            email="leadership@local9.example.org",
            password_hash=hash_password("password123"),
        )
        member_account_9 = models.Account(
            local_id=local_9.id,
            member_id=members_9[0].id,
            role="member",
            email=members_9[0].email,
            password_hash=hash_password("password123"),
        )
        db.add_all([leadership_27, member_account_27, leadership_9, member_account_9])
        db.flush()

        # One already-sent announcement in the larger local, with recipient rows,
        # per the brief -- its id goes in the README Test Accounts section.
        sent_at = datetime.now(timezone.utc) - timedelta(days=1)
        announcement = models.Announcement(
            id=SENT_ANNOUNCEMENT_ID,
            local_id=local_27.id,
            created_by_id=leadership_27.id,
            title="Emergency meeting Thursday 6pm",
            body=(
                "Contractor is pulling crews off the westside job. Emergency meeting "
                "Thursday 6pm at the hall. Everyone needs to be there."
            ),
            needs_ack=True,
            idempotency_key=str(uuid.uuid4()),
            sent_at=sent_at,
            created_at=sent_at,
        )
        db.add(announcement)
        db.flush()

        send_job = models.SendJob(
            announcement_id=announcement.id,
            status="completed",
            started_at=sent_at,
            finished_at=sent_at,
        )
        db.add(send_job)

        recipients = []
        for i, member in enumerate(members_27):
            if member.status != "active":
                continue
            status = "sent"
            read_at = acknowledged_at = None
            if i % 3 == 0:
                status = "read"
                read_at = sent_at + timedelta(hours=1)
            if i % 7 == 0:
                status = "acknowledged"
                read_at = read_at or sent_at + timedelta(hours=1)
                acknowledged_at = sent_at + timedelta(hours=2)
            recipients.append(
                models.Recipient(
                    announcement_id=announcement.id,
                    member_id=member.id,
                    status=status,
                    sent_at=sent_at,
                    read_at=read_at,
                    acknowledged_at=acknowledged_at,
                )
            )
        db.add_all(recipients)
        db.commit()

        return {
            "local_27_id": str(local_27.id),
            "local_9_id": str(local_9.id),
            "leadership_27_email": leadership_27.email,
            "member_27_email": member_account_27.email,
            "member_27_id": str(members_27[0].id),
            "leadership_9_email": leadership_9.email,
            "member_9_email": member_account_9.email,
            "member_9_id": str(members_9[0].id),
            "sent_announcement_id": str(announcement.id),
            "password_for_all": "password123",
        }
    finally:
        db.close()


if __name__ == "__main__":
    import json

    print(json.dumps(seed(), indent=2))
