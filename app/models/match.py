"""
ORM-модель совпадений пользователя с IT-тендерами
"""
from datetime import datetime
from sqlalchemy import Integer, String, Float, Boolean, DateTime, func, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Match(Base):
    __tablename__ = "matches"

    # Первичный ключ
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Идентификатор пользователя
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    # Идентификатор IT-тендера
    tender_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("it_tenders.tender_id"), nullable=False, index=True
    )
    # Косинусное сходство между пользователем и тендером
    similarity: Mapped[float] = mapped_column(Float, nullable=False)
    # Персональный скор (из личной модели пользователя, если есть)
    personal_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    # Итоговый финальный скор (среднее или взвешенная комбинация)
    final_score: Mapped[float] = mapped_column(Float, nullable=False)
    # Был ли показан пользователю
    shown: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Время создания совпадения
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
