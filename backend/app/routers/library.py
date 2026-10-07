from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.security import get_current_user, get_current_admin
from app.services import library as library_service

# The Library: curated learning resources the Career Coach can recommend
# (see services/library.py). Everyone signed in can browse; only platform
# admins can change it.
router = APIRouter(prefix="/library", tags=["library"])


def _apply(item: models.LibraryItem, payload: schemas.LibraryItemIn) -> None:
    item.title = payload.title.strip()
    item.url = payload.url
    item.description = payload.description.strip()
    item.resource_type = payload.resource_type
    item.fields = ",".join(payload.fields)
    item.level = payload.level
    item.cost = payload.cost
    item.active = payload.active


@router.get("/items", response_model=list[schemas.LibraryItemOut])
def list_items(
    q: str | None = None,
    resource_type: str | None = None,
    cost: str | None = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    query = db.query(models.LibraryItem)
    # Inactive (hidden) items are only visible to admins managing them.
    if not (include_inactive and user.is_admin):
        query = query.filter(models.LibraryItem.active.is_(True))
    if resource_type:
        query = query.filter(models.LibraryItem.resource_type == resource_type)
    if cost:
        query = query.filter(models.LibraryItem.cost == cost)
    items = query.order_by(models.LibraryItem.title.asc()).all()
    if q and q.strip():
        ranked = library_service.retrieve(items, q.strip(), limit=len(items) or 1)
        # Fall back to a plain substring match so searching a tag fragment
        # (e.g. "scr") still finds something the keyword scorer wouldn't.
        if not ranked:
            needle = q.strip().lower()
            ranked = [
                i for i in items
                if needle in f"{i.title} {i.description} {i.fields}".lower()
            ]
        items = ranked
    return items


@router.post("/items", response_model=schemas.LibraryItemOut)
def create_item(
    payload: schemas.LibraryItemIn,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(get_current_admin),
):
    item = models.LibraryItem()
    _apply(item, payload)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/items/{item_id}", response_model=schemas.LibraryItemOut)
def update_item(
    item_id: int,
    payload: schemas.LibraryItemIn,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(get_current_admin),
):
    item = db.query(models.LibraryItem).filter_by(id=item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Library item not found.")
    _apply(item, payload)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/items/{item_id}")
def delete_item(
    item_id: int,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(get_current_admin),
):
    item = db.query(models.LibraryItem).filter_by(id=item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Library item not found.")
    db.delete(item)
    db.commit()
    return {"status": "deleted"}
