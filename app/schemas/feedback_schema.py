"""
Pydantic-схемы для обратной связи
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class FeedbackCreate(BaseModel):
    """Схема создания записи обратной связи"""
    tender_id: str = Field(..., description="Идентификатор тендера")
    label: bool = Field(..., description="True = интересно, False = не интересно")
    comment: Optional[str] = Field(None, description="Произвольный комментарий")
    similarity: Optional[float] = Field(None, description="Значение сходства на момент показа")


class FeedbackResponse(BaseModel):
    """Схема ответа с данными обратной связи"""
    id: int
    user_id: int
    tender_id: str
    label: bool
    comment: Optional[str]
    similarity: Optional[float]
    created_at: datetime

    model_config = {"from_attributes": True}


class RetrainResponse(BaseModel):
    """Ответ на запрос переобучения модели"""
    status: str
    message: str
