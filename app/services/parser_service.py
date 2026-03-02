"""
Сервис импорта тендеров из БД Goszakup.

Читает готовые лоты из таблицы `lots` базы данных `goszakup`
и синхронизирует их в таблицу `raw_tenders` основной БД.

Ключевые особенности данных:
- Один URL объявления может содержать НЕСКОЛЬКО лотов (разные товары/услуги).
- Уникальность лота определяется по lot_number, а не по URL.
- url_hash считается от "source:lot_number" — это гарантирует уникальность.
- Используется INSERT IGNORE для безопасного пропуска дублей на уровне БД.
"""
import hashlib
import json
import logging
import uuid
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.orm import Session

from app.config import (
    GOSZAKUP_DATABASE_URL,
    GOSZAKUP_IMPORT_BATCH_SIZE,
)
from app.models.raw_tender import RawTender
from decimal import Decimal

logger = logging.getLogger(__name__)

# Движок для чтения из БД Goszakup — только чтение, создаётся один раз
_goszakup_engine = create_engine(
    GOSZAKUP_DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_size=3,
    max_overflow=5,
    echo=False,
)


def _make_url_hash(source: str, lot_number: str) -> str:
    """
    Генерирует SHA256-хеш от "source:lot_number".

    Используем lot_number (не URL) потому что один URL объявления
    может содержать несколько лотов — URL не уникален на уровне лота.
    lot_number вида "85309786-ЗЦП3" уникален для каждого лота.

    :return: Hex-строка SHA256 (64 символа).
    """
    key = f"{source}:{lot_number}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _get_description(raw_data_json: Optional[str], fallback: str) -> Optional[str]:
    """
    Формирует описание лота из поля raw_data (JSON).

    :param raw_data_json: JSON-строка из колонки raw_data таблицы lots.
    :param fallback: Запасное значение если JSON не распарсить.
    :return: Строка описания.
    """
    if not raw_data_json:
        return fallback or None
    try:
        data = json.loads(raw_data_json)
        parts = []

        # Тип товара/услуги — убираем суффикс "История" который портал добавляет
        quantity = (data.get("quantity") or "").replace(" История", "").strip()
        if quantity:
            parts.append(quantity)

        # Статус/способ закупки
        status = (data.get("status") or "").strip()
        if status:
            parts.append(f"Способ: {status}")

        return " | ".join(parts) if parts else fallback
    except (json.JSONDecodeError, TypeError):
        return fallback


def _build_title(lot_name: str) -> str:
    """
    Очищает название лота от числового префикса.

    lot_name в БД имеет вид "16419983-1 Услуги по проведению..."
    Убираем "16419983-1 " чтобы получить читаемый заголовок.
    """
    lot_name = (lot_name or "").strip()
    if not lot_name:
        return ""
    # Префикс имеет вид "XXXXXXXX-N " — число, дефис, число, пробел
    if "-" in lot_name[:15]:
        parts = lot_name.split(" ", 1)
        if len(parts) > 1:
            return parts[1].strip()
    return lot_name


def run_all_parsers(db: Session) -> int:
    """
    Импортирует новые лоты из БД Goszakup в таблицу raw_tenders.

    Алгоритм:
    1. Читает GOSZAKUP_IMPORT_BATCH_SIZE лотов из lots (новые первыми).
    2. Для каждого лота вычисляет url_hash = SHA256("goszakup:lot_number").
    3. Использует INSERT ... ON DUPLICATE KEY UPDATE id=id (MySQL-аналог INSERT IGNORE)
       — при конфликте по url_hash строка молча пропускается, транзакция не рвётся.
    4. Считает реально вставленные строки через rowcount.

    :param db: Сессия основной БД (procurement).
    :return: Количество новых добавленных тендеров.
    """
    logger.info(
        "Импорт лотов из БД Goszakup (лимит=%d)", GOSZAKUP_IMPORT_BATCH_SIZE
    )

    # Запрашиваем lot_number для формирования уникального хеша
    query = text("""
                 SELECT lot_number,
                        lot_url,
                        lot_name,
                        purchase_amount,
                        purchase_method,
                        deadline_date,
                        raw_data,
                        status
                 FROM lots
                 ORDER BY created_at DESC LIMIT :batch_size
                 """)

    try:
        with _goszakup_engine.connect() as conn:
            rows = conn.execute(
                query, {"batch_size": GOSZAKUP_IMPORT_BATCH_SIZE}
            ).fetchall()
    except Exception as exc:
        safe_url = GOSZAKUP_DATABASE_URL.split("@")[-1]
        logger.error("Ошибка подключения к БД Goszakup (%s): %s", safe_url, exc)
        return 0

    if not rows:
        logger.info("В БД Goszakup нет записей для импорта")
        return 0

    logger.info("Получено %d записей из lots, формирую данные...", len(rows))

    # Формируем список словарей для вставки
    records = []
    seen_hashes = set()  # Дедупликация внутри текущего батча

    for row in rows:
        lot = dict(row._mapping)
        url = (lot.get("lot_url") or "").strip()
        lot_number = (lot.get("lot_number") or "").strip()

        if not url or not lot_number:
            continue

        url_hash = _make_url_hash("goszakup", lot_number)

        # Пропускаем дубли внутри одного батча (до обращения к БД)
        if url_hash in seen_hashes:
            continue
        seen_hashes.add(url_hash)

        title = _build_title(lot.get("lot_name") or "")
        if not title:
            continue

        description = _get_description(lot.get("raw_data"), title)

        quantity = to_float(lot.get("purchase_amount"))
        budget = to_float(lot.get("purchase_method"))

        records.append({
            "id": str(uuid.uuid4()),
            "source": "goszakup",
            "title": title,
            "description": description,
            "budget": budget,
            "quantity": quantity,
            "deadline": lot.get("deadline_date"),
            "url": url,
            "url_hash": url_hash,
            "country": "KZ",
            "classified": False,
        })

    if not records:
        logger.info("Нет новых записей для вставки")
        return 0

    # INSERT ... ON DUPLICATE KEY UPDATE id=id
    # При конфликте по url_hash — строка пропускается (rowcount = 0 для дубля).
    # Это MySQL-аналог INSERT IGNORE, но не подавляет другие ошибки.
    stmt = mysql_insert(RawTender).values(records)
    stmt = stmt.prefix_with("IGNORE")

    try:
        result = db.execute(stmt)
        db.commit()
        # MySQL: rowcount = 1 для новой строки, 2 для обновлённой, 0 для пропущенной.
        # on_duplicate_key_update обновляет id на то же значение — считается как 2.
        # Реально новые = строки с rowcount 1 (не было конфликта).
        # Приблизительный подсчёт: affected_rows / 1, дубли дают 0 изменений в данных.
        new_count = result.rowcount
        logger.info(
            "Импорт из Goszakup завершён: вставлено/обработано %d из %d записей",
            new_count,
            len(records),
        )
        return new_count
    except Exception as exc:
        db.rollback()
        logger.error("Ошибка вставки в raw_tenders: %s", exc, exc_info=True)
        return 0


def to_float(value) -> float:
    if value is None:
        return 0.0

    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        # убираем пробелы-разделители тысяч
        return float(value.replace(" ", ""))

    raise TypeError(f"Unsupported type for numeric conversion: {type(value)}")
