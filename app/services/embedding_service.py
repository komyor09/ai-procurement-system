"""
Сервис генерации эмбеддингов с использованием SentenceTransformer
Модель загружается один раз при первом обращении (паттерн Singleton)
"""
import json
import logging
from typing import List

import numpy as np
from sentence_transformers import SentenceTransformer

from app.config import EMBEDDING_MODEL_NAME

logger = logging.getLogger(__name__)

# Глобальный экземпляр модели — загружается единожды
_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    """
    Возвращает загруженную модель SentenceTransformer.
    При первом вызове инициализирует и кеширует модель.
    """
    global _model
    if _model is None:
        logger.info("Загрузка модели эмбеддингов: %s", EMBEDDING_MODEL_NAME)
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        logger.info("Модель эмбеддингов успешно загружена")
    return _model


def generate_embedding(text: str) -> List[float]:
    """
    Генерирует эмбеддинг для переданного текста.

    :param text: Входной текст
    :return: Список числовых значений (вектор)
    """
    if not text or not text.strip():
        raise ValueError("Текст для генерации эмбеддинга не может быть пустым")

    model = get_model()
    embedding: np.ndarray = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()


def embedding_to_json(embedding: List[float]) -> str:
    """
    Сериализует эмбеддинг в JSON-строку для хранения в БД.
    Используйте serialize_embedding() как каноническое имя.
    """
    return json.dumps(embedding)


def json_to_embedding(json_str: str) -> np.ndarray:
    """
    Десериализует эмбеддинг из JSON-строки.
    Используйте deserialize_embedding() как каноническое имя.

    :return: numpy-массив float32
    """
    return np.array(json.loads(json_str), dtype=np.float32)


def serialize_embedding(embedding: List[float]) -> str:
    """
    Каноническая функция сериализации эмбеддинга для записи в MySQL LONGTEXT.

    Эмбеддинги хранятся в БД как JSON-строка (список float).
    Пример: "[0.123, -0.456, 0.789, ...]"

    Компромиссы производительности:
    - Простота реализации и переносимость
    - JSON занимает ~4x больше места, чем бинарный формат (BLOB)
    - Для MVP (< 100k тендеров) накладные расходы приемлемы
    - При масштабировании рекомендуется перейти на pgvector (PostgreSQL)
    """
    return json.dumps(embedding)


def deserialize_embedding(json_str: str) -> np.ndarray:
    """
    Каноническая функция десериализации эмбеддинга из MySQL LONGTEXT в numpy-массив.

    Вызывается при каждом чтении тендера или профиля пользователя из БД.
    Возвращает массив float32 для совместимости с scikit-learn и numpy.
    """
    return np.array(json.loads(json_str), dtype=np.float32)


def cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    """
    Вычисляет косинусное сходство между двумя векторами вручную
    (без использования sklearn для производительности).

    :return: Значение от -1 до 1
    """
    norm_a = np.linalg.norm(vec_a)
    norm_b = np.linalg.norm(vec_b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(vec_a, vec_b) / (norm_a * norm_b))
