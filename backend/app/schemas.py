import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    token: str
    role: str
    local_id: uuid.UUID
    member_id: uuid.UUID | None = None


class AnnouncementCreate(BaseModel):
    title: str
    body: str
    classification_filter: str | None = None
    needs_ack: bool = False
    # Generated client-side once per compose action; resending the same key
    # (network retry, double-click) returns the original result instead of
    # sending again. See Rule 2 in DESIGN.md.
    idempotency_key: str = Field(min_length=1, max_length=100)


class AnnouncementCounts(BaseModel):
    id: uuid.UUID
    title: str
    body: str
    classification_filter: str | None
    needs_ack: bool
    sent_at: datetime | None
    created_at: datetime
    total_recipients: int
    sent_count: int
    read_count: int
    acknowledged_count: int


class AnnouncementSummary(BaseModel):
    id: uuid.UUID
    title: str
    sent_at: datetime | None
    created_at: datetime


class InboxItem(BaseModel):
    recipient_id: uuid.UUID
    announcement_id: uuid.UUID
    title: str
    body: str
    status: str
    sent_at: datetime | None
    read_at: datetime | None
    acknowledged_at: datetime | None


class AiDraftRequest(BaseModel):
    raw_text: str = Field(min_length=1)


class AiDraftResponse(BaseModel):
    title: str
    body: str
    push_preview: str
    mode: str  # "llm" | "heuristic"
    degraded: bool
    note: str | None = None
