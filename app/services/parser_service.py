"""
Сервис управления парсерами тендеров.
Запускает все зарегистрированные парсеры и сохраняет результаты в БД.
Реализует дедупликацию по составному ключу (source, url_hash).
"""
import logging
import uuid
import hashlib
from typing import List

from sqlalchemy.orm import Session

from app.models.raw_tender import RawTender
from app.parsers.base_parser import BaseParser, TenderData
from app.parsers.goszakup_parser import GoszakupParser

logger = logging.getLogger(__name__)

# Реестр всех активных парсеров
_PARSERS: List[BaseParser] = [
    GoszakupParser(),
]


def register_parser(parser: BaseParser) -> None:
    """
    Регистрирует дополнительный парсер в системе.
    Позволяет динамически расширять список источников.
    """
    _PARSERS.append(parser)
    logger.info("Зарегистрирован парсер: %s", parser.source_name)


def generate_url_hash(url: str) -> str:
    """
    Генерирует SHA256-хеш для URL.
    Используется для безопасной дедупликации и индексирования.
    """
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _save_tender(db: Session, tender_data: TenderData) -> bool:
    """
    Сохраняет один тендер в БД.

    Дедупликация выполняется по составному ключу (source, url_hash).
    Это позволяет:
    - избегать ограничения длины индекса MySQL
    - корректно обрабатывать длинные URL

    Возвращает True если тендер новый, False если уже существует.
    """

    url_hash = generate_url_hash(tender_data.url)

    # Проверка на дубликат
    existing = (
        db.query(RawTender)
        .filter(
            RawTender.source == tender_data.source,
            RawTender.url_hash == url_hash,
        )
        .first()
    )

    if existing:
        return False

    raw = RawTender(
        id=str(uuid.uuid4()),
        source=tender_data.source,
        title=tender_data.title,
        description=tender_data.description,
        budget=tender_data.budget,
        deadline=tender_data.deadline,
        url=tender_data.url,
        url_hash=url_hash,  # сохраняем хеш
        country=tender_data.country,
        classified=False,
    )

    db.add(raw)
    return True


def run_all_parsers(db: Session) -> int:
    """
    Запускает все зарегистрированные парсеры и сохраняет новые тендеры.

    :return: Количество новых сохранённых тендеров
    """
    total_new = 0

    for parser in _PARSERS:
        logger.info("Запуск парсера: %s", parser.source_name)
        tenders: List[TenderData] = parser.safe_fetch()

        new_count = 0

        for tender_data in tenders:
            try:
                is_new = _save_tender(db, tender_data)
                if is_new:
                    new_count += 1
            except Exception as exc:
                logger.error(
                    "Ошибка сохранения тендера [%s] %s: %s",
                    parser.source_name,
                    tender_data.url,
                    exc,
                )
                db.rollback()
                continue

        db.commit()

        total_new += new_count

        logger.info(
            "Парсер [%s]: %d новых тендеров из %d",
            parser.source_name,
            new_count,
            len(tenders),
        )

    logger.info("Все парсеры завершены. Всего новых тендеров: %d", total_new)
    return total_new