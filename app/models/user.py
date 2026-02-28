"""
ORM-модель пользователя системы
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import Integer, BigInteger, Text, Float, DateTime, func
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class User(Base):
    __tablename__ = "users"

    # Автоинкрементный числовой идентификатор
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Уникальный Telegram ID пользователя (BigInteger — Telegram IDs превышают 2^31)
    # Nullable для обратной совместимости с пользователями созданными без бота
    telegram_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, unique=True, nullable=True, index=True
    )
    # Текстовое описание профиля пользователя (сфера деятельности, интересы)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # Эмбеддинг описания пользователя в формате JSON-списка
    embedding: Mapped[str] = mapped_column(LONGTEXT, nullable=True)
    # Минимальный бюджет тендера, который интересует пользователя
    min_budget: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # Время регистрации
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
