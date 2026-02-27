"""
Сервис персонального матчинга пользователей с IT-тендерами.
Для каждого пользователя вычисляется косинусное сходство с каждым IT-тендером.
"""
import logging
import os
import pickle
from typing import List, Optional

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import MATCHING_SIMILARITY_THRESHOLD, USER_MODELS_DIR
from app.models.it_tender import ITTender
from app.models.user import User
from app.models.match import Match
from app.services.embedding_service import cosine_similarity, json_to_embedding

logger = logging.getLogger(__name__)


def _load_user_model(user_id: int) -> Optional[object]:
    """
    Пытается загрузить персональную модель пользователя.
    Возвращает None, если модель не найдена.
    """
    model_path = os.path.join(USER_MODELS_DIR, f"user_{user_id}.pkl")
    if os.path.exists(model_path):
        try:
            with open(model_path, "rb") as f:
                return pickle.load(f)
        except Exception as exc:
            logger.warning("Не удалось загрузить модель пользователя %d: %s", user_id, exc)
    return None


def _compute_personal_score(
    user_model: object,
    tender_embedding: np.ndarray,
) -> float:
    """
    Вычисляет персональный скор тендера с использованием личной модели пользователя.

    :return: Вероятность интереса пользователя (0-1), или 0 если модель не обучена
    """
    if user_model is None:
        return 0.0
    if not hasattr(user_model, "classes_"):
        return 0.0

    try:
        proba = user_model.predict_proba(tender_embedding.reshape(1, -1))[0]
        class_list = list(user_model.classes_)
        if 1 in class_list:
            return float(proba[class_list.index(1)])
    except Exception as exc:
        logger.warning("Ошибка вычисления персонального скора: %s", exc)
    return 0.0


def run_matching_for_user(db: Session, user: User) -> int:
    """
    Запускает матчинг IT-тендеров для конкретного пользователя.

    :return: Количество новых совпадений
    """
    if not user.embedding:
        logger.warning("У пользователя %d отсутствует эмбеддинг — пропуск", user.id)
        return 0

    user_emb = json_to_embedding(user.embedding)
    user_model = _load_user_model(user.id)

    # Получаем ID тендеров, с которыми у пользователя уже есть совпадение
    existing_tender_ids = set(
        row[0]
        for row in db.execute(
            select(Match.tender_id).where(Match.user_id == user.id)
        ).fetchall()
    )

    # Загружаем все IT-тендеры
    it_tenders: List[ITTender] = db.query(ITTender).all()
    new_matches_count = 0

    for tender in it_tenders:
        # Пропускаем уже обработанные тендеры
        if tender.tender_id in existing_tender_ids:
            continue

        try:
            tender_emb = json_to_embedding(tender.embedding)
        except Exception as exc:
            logger.warning("Не удалось разобрать эмбеддинг тендера %s: %s", tender.tender_id, exc)
            continue

        # Вычисляем косинусное сходство вручную
        sim = cosine_similarity(user_emb, tender_emb)

        # Проверяем пороговые условия
        budget_ok = (tender.budget is None) or (tender.budget >= user.min_budget)
        if sim < MATCHING_SIMILARITY_THRESHOLD or not budget_ok:
            continue

        # Вычисляем персональный скор только если личная модель обучена.
        # Cold-start пользователя (нет обученной модели): final_score = sim.
        # Это предотвращает искажение результатов необученной моделью.
        personal_score = _compute_personal_score(user_model, tender_emb)

        # Если персональная модель обучена (personal_score > 0):
        #   final_score = 70% косинусное сходство + 30% персональный скор
        # Иначе (cold-start): final_score = только косинусное сходство
        if personal_score > 0:
            final_score = 0.7 * sim + 0.3 * personal_score
        else:
            final_score = sim  # Cold-start: полагаемся исключительно на сходство

        match = Match(
            user_id=user.id,
            tender_id=tender.tender_id,
            similarity=sim,
            personal_score=personal_score,
            final_score=final_score,
        )
        db.add(match)
        new_matches_count += 1

    if new_matches_count > 0:
        db.commit()

    logger.info(
        "Матчинг пользователя %d завершён: %d новых совпадений",
        user.id,
        new_matches_count,
    )
    return new_matches_count


def run_matching_all_users(db: Session) -> int:
    """
    Запускает матчинг для всех зарегистрированных пользователей.

    :return: Суммарное количество новых совпадений
    """
    users: List[User] = db.query(User).all()
    total = 0
    for user in users:
        total += run_matching_for_user(db, user)
    logger.info("Матчинг завершён для %d пользователей. Итого совпадений: %d", len(users), total)
    return total
