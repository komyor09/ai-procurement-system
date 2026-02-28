"""
Парсер тендеров с портала государственных закупок Казахстана — goszakup.gov.kz.
Выполняет реальные HTTP-запросы к публичному списку объявлений и извлекает данные
с помощью BeautifulSoup. Мок-данные полностью удалены.
"""
import logging
import re
from datetime import datetime
from typing import List, Optional

import httpx
from bs4 import BeautifulSoup, Tag

from app.parsers.base_parser import BaseParser, TenderData

logger = logging.getLogger(__name__)

# Базовый URL портала государственных закупок
_BASE_URL = "https://goszakup.gov.kz"

# URL страницы со списком объявлений (анонсов) тендеров, сортировка по дате
_LIST_URL = f"{_BASE_URL}/ru/announce"

# Максимальное количество тендеров за один запуск парсера
_MAX_TENDERS = 20

# Таймаут HTTP-соединения и чтения (секунды)
_CONNECT_TIMEOUT = 10.0
_READ_TIMEOUT = 30.0

# Заголовки для имитации браузерного запроса — снижает вероятность блокировки
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.5,en;q=0.3",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "DNT": "1",
}


def _parse_budget(raw: str) -> Optional[float]:
    """
    Извлекает числовое значение бюджета из строки вида «15 000 000,00 KZT».
    Удаляет пробелы, валютные метки и преобразует запятую в точку.

    :param raw: Исходная строка с бюджетом.
    :return: Числовое значение или None если распарсить не удалось.
    """
    if not raw:
        return None
    # Оставляем только цифры, точки и запятые
    cleaned = re.sub(r"[^\d.,]", "", raw.strip())
    # Заменяем запятую-разделитель на точку
    cleaned = cleaned.replace(",", ".")
    # Если несколько точек — оставляем только последнюю (целая и дробная части)
    parts = cleaned.split(".")
    if len(parts) > 2:
        cleaned = "".join(parts[:-1]) + "." + parts[-1]
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _parse_deadline(raw: str) -> Optional[datetime]:
    """
    Парсит дату дедлайна из строк форматов:
    «31.12.2025», «31.12.2025 23:59», «2025-12-31», «2025-12-31T23:59:00».

    :param raw: Исходная строка с датой.
    :return: Объект datetime или None если не удалось распарсить.
    """
    if not raw:
        return None

    raw = raw.strip()

    # Перечень поддерживаемых форматов дат
    date_formats = [
        "%d.%m.%Y %H:%M",
        "%d.%m.%Y",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]

    for fmt in date_formats:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue

    return None


def _extract_text(tag: Optional[Tag], default: str = "") -> str:
    """
    Безопасно извлекает и очищает текстовое содержимое HTML-тега.

    :param tag: BeautifulSoup Tag или None.
    :param default: Значение по умолчанию если тег отсутствует.
    :return: Очищенная строка.
    """
    if not tag:
        return default
    return tag.get_text(separator=" ", strip=True)


def _parse_tender_row(row: Tag) -> Optional[TenderData]:
    """
    Извлекает данные одного тендера из строки таблицы (<tr>) или карточки списка.

    Структура HTML goszakup.gov.kz (страница /ru/announce):
    Каждый тендер — строка таблицы <tr> с ячейками <td>:
      [0] Номер объявления
      [1] Наименование (содержит ссылку <a>)
      [2] Заказчик
      [3] Способ закупки
      [4] Сумма (бюджет)
      [5] Дата окончания приёма заявок (дедлайн)
      [6] Статус

    :param row: Тег <tr> из таблицы результатов.
    :return: Объект TenderData или None если строку не удалось разобрать.
    """
    cells = row.find_all("td")

    # Ожидаем минимум 6 ячеек в строке
    if len(cells) < 6:
        return None

    # --- Извлечение заголовка и URL ---
    # Название тендера находится во второй ячейке (индекс 1) внутри тега <a>
    title_cell = cells[1]
    link_tag = title_cell.find("a", href=True)

    if not link_tag:
        return None

    title = _extract_text(link_tag).strip()
    if not title:
        return None

    # Формируем абсолютный URL тендера
    href = link_tag.get("href", "")
    if href.startswith("http"):
        url = href
    elif href.startswith("/"):
        url = f"{_BASE_URL}{href}"
    else:
        url = f"{_BASE_URL}/{href}"

    # --- Извлечение описания ---
    # Краткое описание может быть в атрибуте title ссылки или в подписи под названием
    description_tag = title_cell.find("span", class_=re.compile(r"desc|note|sub", re.I))
    if description_tag:
        description = _extract_text(description_tag)
    else:
        # Берём весь текст ячейки за вычетом текста ссылки как описание
        full_text = _extract_text(title_cell)
        description = full_text.replace(title, "").strip() or None

    # --- Извлечение бюджета (ячейка индекс 4) ---
    budget_raw = _extract_text(cells[4]) if len(cells) > 4 else ""
    budget = _parse_budget(budget_raw)

    # --- Извлечение дедлайна (ячейка индекс 5) ---
    deadline_raw = _extract_text(cells[5]) if len(cells) > 5 else ""
    deadline = _parse_deadline(deadline_raw)

    return TenderData(
        url=url,
        title=title,
        description=description or None,
        budget=budget,
        deadline=deadline,
        source="goszakup",
        country="KZ",
    )


def _parse_tenders_from_html(html: str) -> List[TenderData]:
    """
    Парсит HTML-страницу списка тендеров и возвращает список TenderData.

    Ищет таблицу с объявлениями на странице /ru/announce.
    В случае изменения структуры сайта достаточно адаптировать только эту функцию.

    :param html: Исходный HTML страницы.
    :return: Список распарсенных тендеров (не более _MAX_TENDERS).
    """
    soup = BeautifulSoup(html, "html.parser")
    results: List[TenderData] = []

    # Основная таблица тендеров на странице /ru/announce
    # Ищем таблицу с классом содержащим 'table' — стандартный Bootstrap класс портала
    table = soup.find("table", class_=re.compile(r"table", re.I))

    if not table:
        # Попытка найти таблицу без класса как запасной вариант
        table = soup.find("table")

    if not table:
        logger.warning("Таблица тендеров не найдена на странице goszakup.gov.kz")
        # Попытка найти карточки в альтернативной вёрстке (без таблицы)
        results = _parse_card_layout(soup)
        return results[:_MAX_TENDERS]

    # Пропускаем заголовочную строку <thead> — берём только строки тела таблицы
    tbody = table.find("tbody") or table
    rows = tbody.find_all("tr")

    for row in rows:
        if len(results) >= _MAX_TENDERS:
            break
        try:
            tender = _parse_tender_row(row)
            if tender:
                results.append(tender)
        except Exception as exc:
            # Не прерываем парсинг при ошибке в одной строке
            logger.debug("Не удалось разобрать строку тендера: %s", exc)
            continue

    logger.info("Извлечено %d тендеров из таблицы goszakup.gov.kz", len(results))
    return results


def _parse_card_layout(soup: BeautifulSoup) -> List[TenderData]:
    """
    Запасной метод парсинга для альтернативной вёрстки портала
    в виде карточек (не таблицы).

    Ищет блоки с классами содержащими 'announce', 'tender', 'lot', 'card'.

    :param soup: Разобранный BeautifulSoup документ.
    :return: Список TenderData.
    """
    results: List[TenderData] = []

    # Ищем любые блоки, похожие на карточки тендеров
    cards = soup.find_all(
        ["div", "li", "article"],
        class_=re.compile(r"announce|tender|lot|card|item", re.I),
    )

    for card in cards:
        if len(results) >= _MAX_TENDERS:
            break
        try:
            # Ищем ссылку с заголовком внутри карточки
            link_tag = card.find("a", href=True)
            if not link_tag:
                continue

            title = _extract_text(link_tag).strip()
            if not title or len(title) < 5:
                continue

            href = link_tag.get("href", "")
            if href.startswith("http"):
                url = href
            elif href.startswith("/"):
                url = f"{_BASE_URL}{href}"
            else:
                continue

            # Пытаемся найти описание, бюджет и дедлайн внутри карточки
            description = None
            budget = None
            deadline = None

            # Текст карточки за вычетом заголовка как краткое описание
            full_text = _extract_text(card)
            desc_candidate = full_text.replace(title, "").strip()
            if desc_candidate and len(desc_candidate) > 10:
                description = desc_candidate[:500]

            # Ищем числа, похожие на бюджет
            budget_match = re.search(r"([\d\s]{4,}(?:[.,]\d{1,2})?)\s*(?:тенге|тг|KZT|₸)", full_text, re.I)
            if budget_match:
                budget = _parse_budget(budget_match.group(1))

            # Ищем даты в тексте карточки
            date_match = re.search(r"\d{2}\.\d{2}\.\d{4}", full_text)
            if date_match:
                deadline = _parse_deadline(date_match.group(0))

            results.append(TenderData(
                url=url,
                title=title,
                description=description,
                budget=budget,
                deadline=deadline,
                source="goszakup",
                country="KZ",
            ))

        except Exception as exc:
            logger.debug("Ошибка парсинга карточки: %s", exc)
            continue

    logger.info("Извлечено %d тендеров из карточного макета goszakup.gov.kz", len(results))
    return results


class GoszakupParser(BaseParser):
    """
    Парсер тендерной площадки Goszakup (Казахстан).
    Выполняет реальные синхронные HTTP-запросы через httpx с последующим
    HTML-парсингом через BeautifulSoup.

    Интерфейс BaseParser (fetch_tenders / source_name) сохранён без изменений.
    Парсер вызывается синхронно из планировщика — httpx.Client используется
    вместо httpx.AsyncClient для совместимости с текущей синхронной архитектурой.
    """

    @property
    def source_name(self) -> str:
        return "goszakup"

    def fetch_tenders(self) -> List[TenderData]:
        """
        Загружает страницу списка объявлений goszakup.gov.kz и возвращает
        список тендеров в формате TenderData.

        При любой сетевой или парсинговой ошибке логирует её и возвращает
        пустой список — система при этом не прерывается.

        :return: Список тендеров (не более _MAX_TENDERS=20 штук).
        """
        logger.info("Запрос тендеров с goszakup.gov.kz: %s", _LIST_URL)

        try:
            html = self._fetch_html(_LIST_URL)
        except Exception as exc:
            # Любая сетевая ошибка — возвращаем пустой список
            logger.error(
                "Сетевая ошибка при получении страницы goszakup.gov.kz: %s", exc
            )
            return []

        try:
            tenders = _parse_tenders_from_html(html)
        except Exception as exc:
            # Ошибка парсинга HTML — возвращаем пустой список
            logger.error(
                "Ошибка разбора HTML goszakup.gov.kz: %s", exc, exc_info=True
            )
            return []

        logger.info(
            "Парсер [%s] завершён: получено %d тендеров",
            self.source_name,
            len(tenders),
        )
        return tenders

    def _fetch_html(self, url: str) -> str:
        """
        Выполняет HTTP GET-запрос и возвращает HTML-тело ответа.

        Использует httpx.Client с настроенными таймаутами и заголовками.
        Следует редиректам. Выбрасывает исключение при HTTP-ошибке (4xx, 5xx).

        :param url: URL страницы для загрузки.
        :return: HTML-контент страницы в виде строки.
        :raises httpx.HTTPStatusError: При HTTP-ошибке ответа сервера.
        :raises httpx.TimeoutException: При превышении таймаута.
        :raises httpx.RequestError: При сетевой ошибке.
        """
        timeout = httpx.Timeout(
            connect=_CONNECT_TIMEOUT,
            read=_READ_TIMEOUT,
            write=10.0,
            pool=5.0,
        )

        with httpx.Client(
            headers=_HEADERS,
            timeout=timeout,
            follow_redirects=True,
            # Не проверяем SSL-сертификат только если сайт использует самоподписанный
            # В продакшн-среде verify=True (по умолчанию)
            verify=True,
        ) as client:
            response = client.get(url)
            # Выбрасываем исключение при статусах 4xx и 5xx
            response.raise_for_status()
            logger.debug(
                "HTTP ответ от goszakup.gov.kz: статус=%d, размер=%d байт",
                response.status_code,
                len(response.content),
            )
            return response.text
