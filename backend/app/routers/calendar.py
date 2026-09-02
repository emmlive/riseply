"""Calendar connection endpoints -- separate router from auth.py's
login OAuth, since this is a logged-in-user action (connecting a
calendar to an already-authenticated account), not an authentication
method itself.

Google Calendar isn't implemented yet -- this only supports
provider="microsoft" for now. Structured so a second provider can be
added by extending get_connect_url/exchange_code_for_tokens per-
provider rather than needing to touch these endpoints' shape.
"""
import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.security import get_current_user
from app.services import calendar_oauth, calendar_encryption

router = APIRouter(prefix="/calendar", tags=["calendar"])

SUPPORTED_PROVIDERS = {"microsoft"}


@router.get("/connect/{provider}", response_model=schemas.CalendarConnectUrlOut)
def get_connect_url(provider: str, user: models.User = Depends(get_current_user)):
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"'{provider}' isn't a supported calendar provider yet.")

    # Generated here (not on the frontend) so it can't be predicted or
    # replayed cross-session, same reasoning as any server-issued CSRF
    # token -- the frontend stores it and compares it against what
    # Microsoft round-trips back before ever calling /callback below,
    # same pattern the existing login OAuth flow already uses.
    state = secrets.token_urlsafe(24)
    url = calendar_oauth.get_connect_url(state)
    return schemas.CalendarConnectUrlOut(url=url, state=state)


@router.post("/callback/{provider}", response_model=schemas.CalendarConnectionOut)
def callback(
    provider: str,
    payload: schemas.CalendarCallbackRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"'{provider}' isn't a supported calendar provider yet.")

    tokens = calendar_oauth.exchange_code_for_tokens(payload.code)

    existing = db.query(models.CalendarConnection).filter_by(user_id=user.id, provider=provider).first()
    if existing is None:
        existing = models.CalendarConnection(user_id=user.id, provider=provider)
        db.add(existing)

    existing.access_token = calendar_encryption.encrypt_token(tokens["access_token"])
    existing.refresh_token = calendar_encryption.encrypt_token(tokens["refresh_token"])
    existing.expires_at = tokens["expires_at"]
    db.commit()
    db.refresh(existing)

    return schemas.CalendarConnectionOut(provider=existing.provider, connected_at=existing.connected_at)


@router.get("/connections", response_model=list[schemas.CalendarConnectionOut])
def list_connections(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    rows = db.query(models.CalendarConnection).filter_by(user_id=user.id).all()
    return [schemas.CalendarConnectionOut(provider=r.provider, connected_at=r.connected_at) for r in rows]


@router.delete("/connections/{provider}")
def disconnect(provider: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    row = db.query(models.CalendarConnection).filter_by(user_id=user.id, provider=provider).first()
    if row is None:
        raise HTTPException(status_code=404, detail="No connection to disconnect.")
    db.delete(row)
    db.commit()
    return {"disconnected": True}


def get_valid_access_token(db: Session, connection: models.CalendarConnection) -> str:
    """Thin delegate to calendar_oauth.get_valid_access_token -- kept
    importable from here too since it's the natural place a router
    function would look for it, and existing tests already reference
    it via this module. The real implementation lives in the service
    module now that routers/org_buddy.py's scheduling endpoints need
    it too (see that module's docstring on why)."""
    return calendar_oauth.get_valid_access_token(db, connection)
