"""
Сервис переобучения моделей на основе накопленной обратной связи.
Поддерживает глобальное и персональное переобучение.
"""
import logging
import os
import pickle
from typing import List, Tuple

import numpy as np
from sklearn.linear_model import LogisticRegression
from sqlalchemy.orm import Session

from app.config import (
    GLOBAL_MODEL_PATH,
    GLOBAL_RETRAIN_MIN_FEEDBACK,
    USER_RETRAIN_MIN_FEEDBACK,
    USER_MODELS_DIR,
    MODELS_DIR,
)
from app.models.feedback import Feedback
from app.models.it_tender import ITTender
from app.models.user import User
from app.services.embedding_service import json_to_embedding
from app.services import global_classifier_service

logger = logging.getLogger(__name__)


def _gather_global_training_data(
    db: Session,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Собирает данные для обучения глобальной модели из таблицы обратной связи.
    Использует эмбеддинги IT-тендеров и метки пользователей.

    :return: Кортеж (X — матрица признаков, y — вектор меток)
    """
    feedbacks: List[Feedback] = db.query(Feedback).all()

    X_list, y_list = [], []
    for fb in feedbacks:
        # Ищем эмбеддинг тендера в it_tenders
        it_tender = db.get(ITTender, fb.tender_id)
        if it_tender and it_tender.embedding:
            try:
                emb = json_to_embedding(it_tender.embedding)
                X_list.append(emb)
                # label True → 1 (IT), False → 0 (не IT)
                y_list.append(1 if fb.label else 0)
            except Exception as exc:
                logger.warning("Пропуск feedback %d: %s", fb.id, exc)
                continue

    if not X_list:
        return np.array([]), np.array([])

    return np.array(X_list, dtype=np.float32), np.array(y_list, dtype=np.int32)


def retrain_global_model(db: Session, force: bool = False) -> bool:
    """
    Переобучает глобальную модель классификатора IT-тендеров.
    Выполняется при накоплении достаточного числа отзывов.

    :param force: Принудительное переобучение независимо от количества отзывов
    :return: True если переобучение прошло успешно
    """
    feedback_count = db.query(Feedback).count()

    if not force and feedback_count < GLOBAL_RETRAIN_MIN_FEEDBACK:
        logger.info(
            "Недостаточно отзывов для глобального переобучения: %d / %d",
            feedback_count,
            GLOBAL_RETRAIN_MIN_FEEDBACK,
        )
        return False

    logger.info("Запуск глобального переобучения. Всего отзывов: %d", feedback_count)

    X, y = _gather_global_training_data(db)
    if len(X) == 0:
        logger.warning("Нет данных для обучения глобальной модели")
        return False

    # Проверяем наличие обоих классов
    unique_classes = np.unique(y)
    if len(unique_classes) < 2:
        logger.warning("Недостаточно классов для обучения: %s", unique_classes)
        return False

    clf = LogisticRegression(max_iter=1000, class_weight="balanced")
    clf.fit(X, y)

    # Сохраняем обученную модель на диск
    os.makedirs(MODELS_DIR, exist_ok=True)
    with open(GLOBAL_MODEL_PATH, "wb") as f:
        pickle.dump(clf, f)

    # Увеличиваем версию модели и перезагружаем классификатор в памяти
    from app.services.global_classifier_service import reload_classifier, increment_model_version
    increment_model_version()
    reload_classifier()
    logger.info("Глобальная модель переобучена и сохранена в %s", GLOBAL_MODEL_PATH)
    return True


def _gather_user_training_data(
    db: Session, user_id: int
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Собирает данные для обучения персональной модели пользователя.
    """
    feedbacks: List[Feedback] = (
        db.query(Feedback).filter(Feedback.user_id == user_id).all()
    )

    X_list, y_list = [], []
    for fb in feedbacks:
        it_tender = db.get(ITTender, fb.tender_id)
        if it_tender and it_tender.embedding:
            try:
                emb = json_to_embedding(it_tender.embedding)
                X_list.append(emb)
                y_list.append(1 if fb.label else 0)
            except Exception as exc:
                logger.warning("Пропуск feedback %d пользователя %d: %s", fb.id, user_id, exc)
                continue

    if not X_list:
        return np.array([]), np.array([])

    return np.array(X_list, dtype=np.float32), np.array(y_list, dtype=np.int32)


def retrain_user_model(db: Session, user_id: int, force: bool = False) -> bool:
    """
    Переобучает персональную модель пользователя.

    :param force: Принудительное переобучение независимо от количества отзывов
    :return: True если переобучение прошло успешно
    """
    user = db.get(User, user_id)
    if not user:
        logger.error("Пользователь %d не найден", user_id)
        return False

    feedback_count = (
        db.query(Feedback).filter(Feedback.user_id == user_id).count()
    )

    if not force and feedback_count < USER_RETRAIN_MIN_FEEDBACK:
        logger.info(
            "Недостаточно отзывов для переобучения модели пользователя %d: %d / %d",
            user_id,
            feedback_count,
            USER_RETRAIN_MIN_FEEDBACK,
        )
        return False

    logger.info(
        "Запуск переобучения модели пользователя %d. Отзывов: %d",
        user_id,
        feedback_count,
    )

    X, y = _gather_user_training_data(db, user_id)
    if len(X) == 0:
        logger.warning("Нет данных для обучения модели пользователя %d", user_id)
        return False

    unique_classes = np.unique(y)
    if len(unique_classes) < 2:
        logger.warning(
            "Недостаточно классов для обучения модели пользователя %d: %s",
            user_id,
            unique_classes,
        )
        return False

    clf = LogisticRegression(max_iter=1000, class_weight="balanced")
    clf.fit(X, y)

    # Сохраняем персональную модель
    os.makedirs(USER_MODELS_DIR, exist_ok=True)
    model_path = os.path.join(USER_MODELS_DIR, f"user_{user_id}.pkl")
    with open(model_path, "wb") as f:
        pickle.dump(clf, f)

    logger.info(
        "Персональная модель пользователя %d сохранена в %s", user_id, model_path
    )
    return True


def run_daily_retraining(db: Session) -> None:
    """
    Ежедневная задача переобучения: проверяет и обновляет глобальную
    модель и персональные модели всех пользователей.
    """
    logger.info("Запуск ежедневного переобучения моделей")

    # Глобальное переобучение
    retrain_global_model(db)

    # Персональное переобучение для каждого пользователя
    users: List[User] = db.query(User).all()
    for user in users:
        retrain_user_model(db, user.id)

    logger.info("Ежедневное переобучение завершено")
