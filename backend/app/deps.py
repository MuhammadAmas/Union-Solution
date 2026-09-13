from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app import models
from app.database import get_db


def get_current_account(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> models.Account:
    """Every protected endpoint depends on this. There is no code path into the
    API that skips it -- a new router either declares this dependency (and
    inherits Rule 1 via the repo helpers below) or it isn't authenticated at all."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    auth_token = db.get(models.AuthToken, token)
    if auth_token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    account = db.get(models.Account, auth_token.account_id)
    if account is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    return account


def require_leadership(account: models.Account = Depends(get_current_account)) -> models.Account:
    if account.role != "leadership":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Leadership role required")
    return account


def require_member(account: models.Account = Depends(get_current_account)) -> models.Account:
    if account.role != "member":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Member role required")
    return account
