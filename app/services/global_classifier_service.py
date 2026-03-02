"""
Сервис глобального классификатора IT-тендеров.
Использует LogisticRegression для определения принадлежности тендера к IT-сфере.
"""
import json
import logging
import os
import pickle
from typing import Tuple

import numpy as np
from sklearn.linear_model import LogisticRegression
from sqlalchemy.orm import Session

from app.config import (
    GLOBAL_MODEL_PATH,
    IT_PROBABILITY_THRESHOLD,
    MODELS_DIR,
)
from app.models.raw_tender import RawTender
from app.models.it_tender import ITTender
from app.services.embedding_service import (
    generate_embedding,
    serialize_embedding,
    deserialize_embedding,
)

logger = logging.getLogger(__name__)

# Глобальный классификатор — загружается/создаётся один раз
_classifier: LogisticRegression | None = None

# Метаданные модели: версия инкрементируется при каждом переобучении.
# Версия 0 зарезервирована для cold-start (необученная модель).
_MODEL_META_PATH = os.path.join(MODELS_DIR if MODELS_DIR else "models", "global_model_meta.json")


def _load_model_version() -> int:
    """Читает текущую версию глобальной модели из файла метаданных."""
    if os.path.exists(_MODEL_META_PATH):
        try:
            with open(_MODEL_META_PATH, "r") as f:
                return int(json.load(f).get("version", 0))
        except Exception:
            pass
    return 0


def _save_model_version(version: int) -> None:
    """Сохраняет версию глобальной модели в файл метаданных."""
    os.makedirs(os.path.dirname(_MODEL_META_PATH), exist_ok=True)
    with open(_MODEL_META_PATH, "w") as f:
        json.dump({"version": version}, f)


def get_model_version() -> int:
    """Возвращает актуальную версию глобальной модели."""
    return _load_model_version()


def increment_model_version() -> int:
    """Увеличивает версию модели на 1 и возвращает новое значение."""
    new_version = _load_model_version() + 1
    _save_model_version(new_version)
    logger.info("Версия глобальной модели обновлена: %d", new_version)
    return new_version


def is_cold_start() -> bool:
    """
    Возвращает True, если глобальная модель ещё не обучена (cold-start режим).
    В этом режиме все тендеры пропускаются в it_tenders без классификации.
    """
    clf = get_classifier()
    return not hasattr(clf, "classes_")


def get_classifier() -> LogisticRegression:
    """
    Возвращает глобальную модель классификатора.
    Загружает из файла, либо создаёт новую пустую модель.
    """
    global _classifier
    if _classifier is not None:
        return _classifier

    os.makedirs(MODELS_DIR, exist_ok=True)

    if os.path.exists(GLOBAL_MODEL_PATH):
        logger.info("Загрузка глобальной модели из %s", GLOBAL_MODEL_PATH)
        with open(GLOBAL_MODEL_PATH, "rb") as f:
            _classifier = pickle.load(f)
    else:
        logger.warning(
            "Файл глобальной модели не найден — активирован cold-start режим. "
            "Все тендеры будут временно сохранены в it_tenders до первого обучения."
        )
        _classifier = LogisticRegression(max_iter=1000, class_weight="balanced")

    return _classifier


def reload_classifier() -> None:
    """Принудительно перезагружает классификатор из файла."""
    global _classifier
    _classifier = None
    get_classifier()
    logger.info("Глобальный классификатор перезагружен")


def predict_it_probability(embedding: np.ndarray) -> float:
    """
    Предсказывает вероятность принадлежности тендера к IT-сфере.

    :param embedding: Вектор тендера
    :return: Вероятность от 0 до 1
    """
    clf = get_classifier()

    # Cold-start: модель не обучена — вероятность не вычисляется.
    # Вызывающий код (classify_new_tenders) обрабатывает этот случай отдельно.
    if not hasattr(clf, "classes_"):
        return 1.0  # Возвращаем 1.0 чтобы тендер прошёл через порог в cold-start

    proba = clf.predict_proba(embedding.reshape(1, -1))[0]
    it_class_index = list(clf.classes_).index(1) if 1 in clf.classes_ else -1
    if it_class_index == -1:
        return 0.0
    return float(proba[it_class_index])


def classify_new_tenders(db: Session) -> int:
    """
    Классифицирует все необработанные тендеры из raw_tenders.
    IT-тендеры (вероятность > порога) сохраняются в it_tenders.

    Cold-start поведение:
    Если глобальная модель ещё не обучена, ВСЕ тендеры временно
    сохраняются в it_tenders с model_version=0. После первого обучения
    модели эти тендеры можно переклассифицировать, отфильтровав по
    model_version=0.

    :return: Количество новых IT-тендеров
    """
    unclassified = (
        db.query(RawTender)
        .filter(RawTender.classified == False)  # noqa: E712
        .all()
    )

    if not unclassified:
        logger.info("Нет новых тендеров для классификации")
        return 0

    cold_start = is_cold_start()
    current_version = get_model_version()

    if cold_start:
        logger.warning(
            "Cold-start режим: глобальная модель не обучена. "
            "%d тендеров будут сохранены в it_tenders с model_version=0 "
            "и переклассифицированы после обучения.",
            len(unclassified),
        )

    logger.info("Классификация %d тендеров (версия модели: %d)...", len(unclassified), current_version)
    new_it_count = 0

    for tender in unclassified:
        try:
            text = f"{tender.title} {tender.description or ''}".strip()
            embedding = generate_embedding(text)
            emb_array = np.array(embedding, dtype=np.float32)

            probability = predict_it_probability(emb_array)
            logger.debug("Тендер %s — IT-вероятность: %.3f", tender.id, probability)

            if probability >= IT_PROBABILITY_THRESHOLD:
                existing = db.get(ITTender, tender.id)
                if not existing:
                    it_tender = ITTender(
                        tender_id=tender.id,
                        embedding=serialize_embedding(embedding),
                        budget=tender.budget,
                        quantity=tender.quantity,
                        deadline=tender.deadline,
                        # cold-start: version=0; нормальный режим: текущая версия модели
                        model_version=0 if cold_start else current_version,
                    )
                    db.add(it_tender)
                    new_it_count += 1

            tender.classified = True

        except Exception as exc:
            logger.error("Ошибка классификации тендера %s: %s", tender.id, exc)
            continue

    db.commit()
    logger.info("Классификация завершена. Новых IT-тендеров: %d", new_it_count)
    return new_it_count
