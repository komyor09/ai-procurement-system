"""
Парсер тендеров с портала Goszakup (Казахстан).
В данной реализации используются мок-данные для демонстрации архитектуры.
В реальной системе необходимо заменить на HTTP-запросы к API или HTML-парсинг.
"""
import logging
from datetime import datetime, timedelta
from typing import List

from app.parsers.base_parser import BaseParser, TenderData

logger = logging.getLogger(__name__)

# Мок-тендеры для демонстрации работы системы
_MOCK_TENDERS = [
    {
        "url": "https://goszakup.gov.kz/ru/announce/index/1001",
        "title": "Разработка информационной системы управления документооборотом",
        "description": (
            "Требуется разработка веб-приложения для автоматизации электронного "
            "документооборота государственного органа. Стек: Python, PostgreSQL, React."
        ),
        "budget": 15_000_000.0,
        "country": "KZ",
    },
    {
        "url": "https://goszakup.gov.kz/ru/announce/index/1002",
        "title": "Поставка компьютерного оборудования для школ",
        "description": (
            "Закупка ноутбуков, принтеров и серверного оборудования для 50 школ. "
            "Требования: процессор Intel i5, ОЗУ 16 ГБ, SSD 512 ГБ."
        ),
        "budget": 45_000_000.0,
        "country": "KZ",
    },
    {
        "url": "https://goszakup.gov.kz/ru/announce/index/1003",
        "title": "Строительство нового здания акимата",
        "description": (
            "Строительство административного здания площадью 2000 кв.м. "
            "Материалы: кирпич, железобетон, стекло."
        ),
        "budget": 800_000_000.0,
        "country": "KZ",
    },
    {
        "url": "https://goszakup.gov.kz/ru/announce/index/1004",
        "title": "Внедрение системы кибербезопасности и мониторинга сети",
        "description": (
            "Внедрение SIEM-системы, настройка межсетевых экранов, "
            "проведение пентестирования инфраструктуры. Лицензии Microsoft Azure Defender."
        ),
        "budget": 25_000_000.0,
        "country": "KZ",
    },
    {
        "url": "https://goszakup.gov.kz/ru/announce/index/1005",
        "title": "Закупка продуктов питания для детских садов",
        "description": (
            "Поставка овощей, фруктов, молочных продуктов и мяса "
            "для 30 муниципальных детских садов на год."
        ),
        "budget": 12_000_000.0,
        "country": "KZ",
    },
    {
        "url": "https://goszakup.gov.kz/ru/announce/index/1006",
        "title": "Создание мобильного приложения для граждан",
        "description": (
            "Разработка iOS и Android приложений для получения государственных услуг. "
            "Интеграция с существующими API, поддержка казахского и русского языков."
        ),
        "budget": 8_000_000.0,
        "country": "KZ",
    },
    {
        "url": "https://goszakup.gov.kz/ru/announce/index/1007",
        "title": "Облачная миграция серверной инфраструктуры",
        "description": (
            "Перенос on-premise серверов в облачную среду AWS/GCP. "
            "Настройка CI/CD пайплайнов, контейнеризация микросервисов на Docker/Kubernetes."
        ),
        "budget": 35_000_000.0,
        "country": "KZ",
    },
]


class GoszakupParser(BaseParser):
    """
    Парсер тендерной площадки Goszakup (Казахстан).
    Использует мок-данные — в продакшне следует реализовать
    реальные HTTP-запросы к API goszakup.gov.kz.
    """

    @property
    def source_name(self) -> str:
        return "goszakup"

    def fetch_tenders(self) -> List[TenderData]:
        """
        Возвращает список тендеров.
        Дедлайн устанавливается как текущее время + 30 дней для мок-данных.
        """
        logger.info("Запрос тендеров с Goszakup (мок-режим)")
        deadline = datetime.utcnow() + timedelta(days=30)
        result = []

        for item in _MOCK_TENDERS:
            tender = TenderData(
                url=item["url"],
                title=item["title"],
                description=item.get("description"),
                budget=item.get("budget"),
                deadline=deadline,
                source=self.source_name,
                country=item.get("country", "KZ"),
            )
            result.append(tender)

        return result
