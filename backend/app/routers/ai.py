from fastapi import APIRouter, Depends

from app import models
from app.ai import generate_draft
from app.deps import require_leadership
from app.schemas import AiDraftRequest, AiDraftResponse

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/draft", response_model=AiDraftResponse)
def draft(
    payload: AiDraftRequest,
    account: models.Account = Depends(require_leadership),
) -> AiDraftResponse:
    # This never touches the database and never sends anything -- it only
    # returns text for the leadership screen to show as an editable draft.
    return generate_draft(payload.raw_text)
