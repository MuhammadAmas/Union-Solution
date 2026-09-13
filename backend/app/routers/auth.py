from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.schemas import LoginRequest, LoginResponse
from app.security import verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    account = db.execute(
        select(models.Account).where(models.Account.email == payload.email)
    ).scalar_one_or_none()
    if account is None or not verify_password(payload.password, account.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    token = models.AuthToken(account_id=account.id)
    db.add(token)
    db.commit()

    return LoginResponse(
        token=token.token,
        role=account.role,
        local_id=account.local_id,
        member_id=account.member_id,
    )
