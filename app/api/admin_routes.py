"""
Административные API-роуты:
принудительный запуск парсинга, классификации и переобучения моделей.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.feedback_schema import RetrainResponse
from app.services.retraining_service import retrain_global_model, retrain_user_model
from app.services.parser_service import run_all_parsers
from app.services.global_classifier_service import classify_new_tenders
from app.services.matching_service import run_matching_all_users

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/retrain/global", response_model=RetrainResponse)
def admin_retrain_global(
    force: bool = False,
    db: Session = Depends(get_db),
) -> RetrainResponse:
    """
    Запускает переобучение глобальной модели.
    По умолчанию проверяет пороговое количество отзывов.
    При force=true игнорирует порог.
    """
    logger.info("Запрос на глобальное переобучение (force=%s)", force)
    success = retrain_global_model(db, force=force)

    if success:
        return RetrainResponse(
            status="success",
            message="Глобальная модель успешно переобучена",
        )
    else:
        return RetrainResponse(
            status="skipped",
            message="Переобучение пропущено: недостаточно данных или ошибка",
        )


@router.post("/retrain/user/{user_id}", response_model=RetrainResponse)
def admin_retrain_user(
    user_id: int,
    force: bool = False,
    db: Session = Depends(get_db),
) -> RetrainResponse:
    """
    Запускает переобучение персональной модели пользователя.
    При force=true игнорирует порог минимального количества отзывов.
    """
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Пользователь с ID {user_id} не найден",
        )

    logger.info("Запрос на переобучение модели пользователя %d (force=%s)", user_id, force)
    success = retrain_user_model(db, user_id, force=force)

    if success:
        return RetrainResponse(
            status="success",
            message=f"Персональная модель пользователя {user_id} успешно переобучена",
        )
    else:
        return RetrainResponse(
            status="skipped",
            message="Переобучение пропущено: недостаточно данных или ошибка",
        )


@router.post("/parse", response_model=RetrainResponse)
def admin_run_parsers(db: Session = Depends(get_db)) -> RetrainResponse:
    """
    Принудительно запускает все парсеры тендеров.
    """
    logger.info("Принудительный запуск парсеров")
    count = run_all_parsers(db)
    return RetrainResponse(
        status="success",
        message=f"Парсинг завершён: {count} новых тендеров",
    )


@router.post("/classify", response_model=RetrainResponse)
def admin_classify(db: Session = Depends(get_db)) -> RetrainResponse:
    """
    Принудительно запускает классификацию необработанных тендеров.
    """
    logger.info("Принудительный запуск классификации")
    count = classify_new_tenders(db)
    return RetrainResponse(
        status="success",
        message=f"Классификация завершена: {count} новых IT-тендеров",
    )


@router.post("/match", response_model=RetrainResponse)
def admin_run_matching(db: Session = Depends(get_db)) -> RetrainResponse:
    """
    Принудительно запускает матчинг для всех пользователей.
    """
    logger.info("Принудительный запуск матчинга")
    count = run_matching_all_users(db)
    return RetrainResponse(
        status="success",
        message=f"Матчинг завершён: {count} новых совпадений",
    )
