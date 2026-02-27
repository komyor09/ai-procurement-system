"""
ORM-модель обратной связи пользователя по тендерам
"""
from datetime import datetime
from sqlalchemy import Integer, String, Boolean, Text, Float, DateTime, func, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Feedback(Base):
    __tablename__ = "feedback"

    # Первичный ключ
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Идентификатор пользователя
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    # Идентификатор тендера
    tender_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("raw_tenders.id"), nullable=False
    )
    # Метка: True = интересно, False = не интересно
    label: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # Произвольный комментарий пользователя
    comment: Mapped[str] = mapped_column(Text, nullable=True)
    # Значение косинусного сходства на момент показа
    similarity: Mapped[float] = mapped_column(Float, nullable=True)
    # Время записи отзыва
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
