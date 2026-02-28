"""
ORM-модель для сырых тендеров, собранных парсерами
"""
from datetime import datetime
from sqlalchemy import String, Text, Float, DateTime, func, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class RawTender(Base):
    __tablename__ = "raw_tenders"

    # Дедупликация выполняется по url_hash (SHA256 от "source:url").
    # UniqueConstraint на (source, url) убран — url VARCHAR(1024) при utf8mb4
    # даёт 3072+ байт и превышает лимит индекса MySQL (3072 байт).
    # url_hash покрывает ту же задачу и занимает ровно 64 байта.
    __table_args__ = (
        UniqueConstraint("url_hash", name="uq_raw_tenders_url_hash"),
        Index("ix_raw_tenders_source", "source"),
    )

    # Уникальный идентификатор (UUID строка)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # Источник тендера (название парсера)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    # Заголовок тендера
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    # Подробное описание тендера
    description: Mapped[str] = mapped_column(Text, nullable=True)
    # Бюджет тендера
    budget: Mapped[float] = mapped_column(Float, nullable=True)
    # Дедлайн подачи заявки
    deadline: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    # Ссылка на оригинальный тендер (полный URL, без индекса — слишком длинный)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    # SHA256-хеш от "source:url" — уникальный ключ для быстрого поиска дублей.
    # Генерируется в parser_service._make_url_hash() при каждой вставке.
    url_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # Страна происхождения тендера
    country: Mapped[str] = mapped_column(String(100), nullable=True)
    # Время добавления в систему
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    # Флаг: был ли тендер уже классифицирован
    classified: Mapped[bool] = mapped_column(default=False, nullable=False)
