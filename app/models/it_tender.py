"""
ORM-модель для IT-тендеров, прошедших глобальную классификацию
"""
from datetime import datetime
from sqlalchemy import String, Float, DateTime, func, ForeignKey, Integer
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class ITTender(Base):
    __tablename__ = "it_tenders"

    # Ссылка на исходный тендер в raw_tenders
    tender_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("raw_tenders.id"), primary_key=True
    )
    # Эмбеддинг тендера в формате JSON-списка чисел (LONGTEXT).
    # При чтении преобразуется в numpy-массив через deserialize_embedding().
    embedding: Mapped[str] = mapped_column(LONGTEXT, nullable=False)
    # Бюджет (дублируется для удобства выборки)
    budget: Mapped[float] = mapped_column(Float, nullable=True)
    # Дедлайн (дублируется для удобства выборки)
    deadline: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    # Версия глобальной модели, которая классифицировала этот тендер.
    # Значение 0 означает cold-start: тендер пропущен без реальной классификации
    # и будет переклассифицирован после первого обучения модели.
    model_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Время добавления записи
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
