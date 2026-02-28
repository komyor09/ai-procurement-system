"""
Сервис импорта тендеров из БД Goszakup.

Вместо HTTP-парсеров читает готовые лоты из таблицы `lots` базы данных `goszakup`
и синхронизирует их в таблицу `raw_tenders` основной БД приложения.

Интерфейс run_all_parsers(db) сохранён без изменений — планировщик вызывает
его как раньше, никакой другой код трогать не нужно.
"""
import hashlib
import json
import logging
import uuid
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.config import (
    GOSZAKUP_DATABASE_URL,
    GOSZAKUP_IMPORT_BATCH_SIZE,
)
from app.models.raw_tender import RawTender

logger = logging.getLogger(__name__)

# Движок для чтения из БД Goszakup — создаётся один раз при импорте модуля
_goszakup_engine = create_engine(
    GOSZAKUP_DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_size=3,
    max_overflow=5,
    echo=False,
)


def _make_url_hash(url: str) -> str:
    """
    Генерирует SHA256-хеш от URL.
    Используется как быстрый уникальный ключ для поиска дублей.

    :param url: URL тендера.
    :return: Hex-строка SHA256 (64 символа).
    """
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _get_description(raw_data_json: Optional[str], lot_name: str) -> Optional[str]:
    """
    Формирует описание лота из поля raw_data (JSON) таблицы lots.

    :param raw_data_json: Строка JSON из колонки raw_data.
    :param lot_name: Название лота как запасной вариант.
    :return: Строка описания или None.
    """
    if not raw_data_json:
        return None
    try:
        data = json.loads(raw_data_json)
        parts = []

        # Тип товара / услуги — убираем суффикс "История" который портал добавляет
        quantity = (data.get("quantity") or "").replace(" История", "").strip()
        if quantity:
            parts.append(quantity)

        # Способ / статус закупки
        status = data.get("status") or ""
        if status:
            parts.append(f"Способ: {status}")

        return " | ".join(parts) if parts else lot_name
    except (json.JSONDecodeError, TypeError):
        return lot_name


def _save_lot(db: Session, lot: dict) -> bool:
    """
    Сохраняет один лот из БД Goszakup в таблицу raw_tenders.

    Дедупликация сначала по url_hash (быстро через индекс),
    затем по составному ключу (source, url) как страховка.

    :param db: Сессия основной БД приложения.
    :param lot: Словарь с полями из таблицы lots.
    :return: True если лот новый и был добавлен, False если уже существует.
    """
    url = (lot.get("lot_url") or "").strip()
    if not url:
        return False

    source = "goszakup"
    url_hash = _make_url_hash(f"{source}:{url}")

    # Дедупликация по url_hash — быстрее чем по (source, url)
    existing = (
        db.query(RawTender)
        .filter(RawTender.url_hash == url_hash)
        .first()
    )
    if existing:
        return False

    # Формируем заголовок: убираем числовой префикс "16419983-1 "
    lot_name = (lot.get("lot_name") or "").strip()
    if lot_name and "-" in lot_name[:15]:
        parts = lot_name.split(" ", 1)
        title = parts[1].strip() if len(parts) > 1 else lot_name
    else:
        title = lot_name

    if not title:
        return False

    # Описание из raw_data JSON
    description = _get_description(lot.get("raw_data"), title)

    # Бюджет — колонка purchase_amount (Decimal → float)
    budget = None
    raw_amount = lot.get("purchase_amount")
    if raw_amount is not None:
        try:
            budget = float(raw_amount)
        except (TypeError, ValueError):
            budget = None

    # Дедлайн — колонка deadline_date
    deadline = lot.get("deadline_date")

    raw = RawTender(
        id=str(uuid.uuid4()),
        source=source,
        title=title,
        description=description,
        budget=budget,
        deadline=deadline,
        url=url,
        url_hash=url_hash,
        country="KZ",
        classified=False,
    )
    db.add(raw)
    return True


def run_all_parsers(db: Session) -> int:
    """
    Импортирует новые лоты из БД Goszakup в таблицу raw_tenders.

    Читает GOSZAKUP_IMPORT_BATCH_SIZE записей (новые первыми),
    пропускает уже импортированные и сохраняет новые.

    Сигнатура run_all_parsers(db) сохранена для совместимости со scheduler.py.

    :param db: Сессия основной БД (procurement).
    :return: Количество новых добавленных тендеров.
    """
    logger.info(
        "Импорт лотов из БД Goszakup (лимит=%d)", GOSZAKUP_IMPORT_BATCH_SIZE
    )

    query = text("""
        SELECT
            lot_url,
            lot_name,
            purchase_amount,
            deadline_date,
            raw_data,
            status,
            customer_name,
            subject_type
        FROM lots
        ORDER BY created_at DESC
        LIMIT :batch_size
    """)

    try:
        with _goszakup_engine.connect() as conn:
            rows = conn.execute(
                query, {"batch_size": GOSZAKUP_IMPORT_BATCH_SIZE}
            ).fetchall()
    except Exception as exc:
        # Логируем host/db без пароля
        safe_url = GOSZAKUP_DATABASE_URL.split("@")[-1]
        logger.error("Ошибка подключения к БД Goszakup (%s): %s", safe_url, exc)
        return 0

    if not rows:
        logger.info("В БД Goszakup нет записей для импорта")
        return 0

    logger.info("Получено %d записей из lots, начинаю сохранение...", len(rows))

    new_count = 0
    for row in rows:
        lot = dict(row._mapping)
        try:
            is_new = _save_lot(db, lot)
            if is_new:
                new_count += 1
        except Exception as exc:
            logger.error(
                "Ошибка сохранения лота [%s]: %s",
                lot.get("lot_url", "?"),
                exc,
            )
            continue

    db.commit()
    logger.info(
        "Импорт из Goszakup завершён: %d новых из %d прочитанных",
        new_count,
        len(rows),
    )
    return new_count
