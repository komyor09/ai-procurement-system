"""
Базовый абстрактный класс для всех парсеров тендеров
"""
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class TenderData:
    """Структура данных тендера, возвращаемая парсером"""
    # Уникальная ссылка на тендер (используется для дедупликации)
    url: str
    # Заголовок тендера
    title: str
    # Источник парсера
    source: str
    # Описание тендера
    description: Optional[str] = None
    # Бюджет
    budget: Optional[float] = None
    # Дедлайн подачи заявки
    deadline: Optional[datetime] = None
    # Страна
    country: Optional[str] = None


class BaseParser(ABC):
    """
    Абстрактный базовый класс для парсеров тендеров.
    Все конкретные парсеры должны наследоваться от этого класса
    и реализовывать метод fetch_tenders.
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Уникальное имя источника тендеров"""
        ...

    @abstractmethod
    def fetch_tenders(self) -> List[TenderData]:
        """
        Запрашивает и парсит тендеры из источника.

        :return: Список объектов TenderData
        :raises Exception: При ошибке парсинга
        """
        ...

    def safe_fetch(self) -> List[TenderData]:
        """
        Безопасный вызов fetch_tenders с обработкой исключений.
        Логирует ошибки и возвращает пустой список при сбое.
        """
        try:
            results = self.fetch_tenders()
            logger.info(
                "Парсер [%s] получил %d тендеров",
                self.source_name,
                len(results),
            )
            return results
        except Exception as exc:
            logger.error(
                "Ошибка парсера [%s]: %s",
                self.source_name,
                exc,
                exc_info=True,
            )
            return []
