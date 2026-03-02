"""
API-роуты для работы с пользователями:
создание, просмотр профиля, получение совпадений и отправка обратной связи.
"""
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.match import Match
from app.models.raw_tender import RawTender
from app.models.it_tender import ITTender
from app.models.feedback import Feedback
from app.schemas.user_schema import UserCreate, UserResponse, MatchListResponse, MatchResponse
from app.schemas.feedback_schema import FeedbackCreate, FeedbackResponse
from app.services.embedding_service import generate_embedding, embedding_to_json
from app.services.matching_service import run_matching_for_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["users"])


@router.get("/by-telegram/{telegram_id}", response_model=UserResponse)
def get_user_by_telegram(telegram_id: int, db: Session = Depends(get_db)) -> UserResponse:
    """
    Возвращает пользователя по Telegram ID.
    Используется ботом для проверки существующей регистрации.
    Возвращает 404 если пользователь с таким telegram_id не найден.
    """
    user = (
        db.query(User)
        .filter(User.telegram_id == telegram_id)
        .first()
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Пользователь с telegram_id {telegram_id} не найден",
        )
    return UserResponse.model_validate(user)


@router.post("/create", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, db: Session = Depends(get_db)) -> UserResponse:
    """
    Создаёт нового пользователя.
    Генерирует эмбеддинг для описания и запускает первичный матчинг.
    Если передан telegram_id — проверяет уникальность перед созданием.
    """
    logger.info("Создание нового пользователя")

    # Проверяем уникальность telegram_id если он передан
    if payload.telegram_id is not None:
        existing = (
            db.query(User)
            .filter(User.telegram_id == payload.telegram_id)
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Пользователь с telegram_id {payload.telegram_id} уже существует",
            )

    # Генерируем эмбеддинг для описания пользователя
    try:
        embedding = generate_embedding(payload.description)
        embedding_json = embedding_to_json(embedding)
    except Exception as exc:
        logger.error("Ошибка генерации эмбеддинга: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка генерации эмбеддинга профиля",
        )

    user = User(
        telegram_id=payload.telegram_id,
        description=payload.description,
        embedding=embedding_json,
        min_budget=payload.min_budget,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info("Пользователь создан с ID: %d, telegram_id: %s", user.id, user.telegram_id)

    # Запускаем матчинг сразу после создания
    try:
        matched = run_matching_for_user(db, user)
        logger.info("Первичный матчинг для пользователя %d: %d совпадений", user.id, matched)
    except Exception as exc:
        logger.warning("Ошибка первичного матчинга пользователя %d: %s", user.id, exc)

    return UserResponse.model_validate(user)


@router.get("/{user_id}", response_model=UserResponse)
def get_user(user_id: int, db: Session = Depends(get_db)) -> UserResponse:
    """
    Возвращает профиль пользователя по ID.
    """
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Пользователь с ID {user_id} не найден",
        )
    return UserResponse.model_validate(user)


@router.get("/{user_id}/matches", response_model=MatchListResponse)
def get_user_matches(
    user_id: int,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> MatchListResponse:
    """
    Возвращает список совпадений для пользователя с полными данными тендеров.

    JOIN: matches → it_tenders → raw_tenders
    Каждый элемент содержит поля совпадения (similarity, scores)
    и данные тендера (title, description, deadline, budget, source, url).
    Сортировка по final_score DESC.
    """
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Пользователь с ID {user_id} не найден",
        )

    # JOIN: matches → it_tenders → raw_tenders
    rows = (
        db.query(Match, RawTender)
        .join(ITTender, Match.tender_id == ITTender.tender_id)
        .join(RawTender, ITTender.tender_id == RawTender.id)
        .filter(Match.user_id == user_id)
        .order_by(Match.final_score.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    total = db.query(Match).filter(Match.user_id == user_id).count()

    # Помечаем совпадения как показанные и собираем обогащённый ответ
    result: List[MatchResponse] = []
    for match, raw in rows:
        if not match.shown:
            match.shown = True

        result.append(MatchResponse(
            # Поля совпадения
            id=match.id,
            user_id=match.user_id,
            tender_id=match.tender_id,
            similarity=match.similarity,
            personal_score=match.personal_score,
            final_score=match.final_score,
            shown=match.shown,
            created_at=match.created_at,
            # Данные тендера из raw_tenders
            title=raw.title,
            description=raw.description,
            deadline=raw.deadline,
            budget=raw.budget,
            source=raw.source,
            url=raw.url,
        ))

    db.commit()

    return MatchListResponse(
        user_id=user_id,
        matches=result,
        total=total,
    )


@router.post("/{user_id}/feedback", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
def submit_feedback(
    user_id: int,
    payload: FeedbackCreate,
    db: Session = Depends(get_db),
) -> FeedbackResponse:
    """
    Принимает обратную связь пользователя по тендеру.
    Если комментарий содержит слово "маленьк" — обновляет min_budget.
    """
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Пользователь с ID {user_id} не найден",
        )

    # Обработка ключевого слова в комментарии — обновление минимального бюджета
    if payload.comment and "маленьк" in payload.comment.lower():
        match = (
            db.query(Match)
            .filter(Match.user_id == user_id, Match.tender_id == payload.tender_id)
            .first()
        )
        if match:
            it_tender = db.get(ITTender, payload.tender_id)
            if it_tender and it_tender.budget:
                new_min = it_tender.budget
                user.min_budget = new_min
                logger.info(
                    "Обновлён min_budget пользователя %d → %.2f",
                    user_id,
                    new_min,
                )

    feedback = Feedback(
        user_id=user_id,
        tender_id=payload.tender_id,
        label=payload.label,
        comment=payload.comment,
        similarity=payload.similarity,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)

    logger.info(
        "Обратная связь сохранена: пользователь %d, тендер %s, метка %s",
        user_id,
        payload.tender_id,
        payload.label,
    )
    return FeedbackResponse.model_validate(feedback)
