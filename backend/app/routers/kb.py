from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.security import get_current_user, get_current_admin
from app.services import kb as kb_service
from app import models, schemas

router = APIRouter(prefix="/kb", tags=["knowledge-base"])


@router.get("/articles", response_model=list[schemas.KBArticleOut])
def list_articles(
    category: str | None = None,
    db: Session = Depends(get_db),
    _user: models.User = Depends(get_current_user),
):
    q = db.query(models.KnowledgeBaseArticle)
    if category:
        q = q.filter_by(category=category)
    return q.order_by(models.KnowledgeBaseArticle.category, models.KnowledgeBaseArticle.title).all()


@router.get("/categories", response_model=list[str])
def list_categories(db: Session = Depends(get_db), _user: models.User = Depends(get_current_user)):
    rows = db.query(models.KnowledgeBaseArticle.category).distinct().all()
    return sorted({r[0] for r in rows})


@router.get("/articles/{article_id}", response_model=schemas.KBArticleOut)
def get_article(
    article_id: int,
    db: Session = Depends(get_db),
    _user: models.User = Depends(get_current_user),
):
    article = db.query(models.KnowledgeBaseArticle).filter_by(id=article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found.")
    return article


@router.post("/ask", response_model=schemas.KBAskResponse)
def ask(
    payload: schemas.KBAskRequest,
    db: Session = Depends(get_db),
    _user: models.User = Depends(get_current_user),
):
    all_articles = db.query(models.KnowledgeBaseArticle).all()
    relevant = kb_service.retrieve_relevant_articles(payload.question, all_articles)
    try:
        answer = kb_service.answer_question(payload.question, relevant)
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Couldn't get an answer right now — try again shortly, or use the Support tab.",
        )
    return schemas.KBAskResponse(answer=answer, sources=relevant)


# --- Admin CRUD (platform-wide admin, not org-scoped) ---

@router.post("/articles", response_model=schemas.KBArticleOut)
def create_article(
    payload: schemas.KBArticleCreate,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(get_current_admin),
):
    article = models.KnowledgeBaseArticle(
        category=payload.category, title=payload.title, content=payload.content,
    )
    db.add(article)
    db.commit()
    db.refresh(article)
    return article


@router.put("/articles/{article_id}", response_model=schemas.KBArticleOut)
def update_article(
    article_id: int,
    payload: schemas.KBArticleCreate,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(get_current_admin),
):
    article = db.query(models.KnowledgeBaseArticle).filter_by(id=article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found.")
    article.category = payload.category
    article.title = payload.title
    article.content = payload.content
    db.commit()
    db.refresh(article)
    return article


@router.delete("/articles/{article_id}")
def delete_article(
    article_id: int,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(get_current_admin),
):
    article = db.query(models.KnowledgeBaseArticle).filter_by(id=article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found.")
    db.delete(article)
    db.commit()
    return {"deleted": True}
