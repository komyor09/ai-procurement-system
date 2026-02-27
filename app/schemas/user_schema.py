"""
Pydantic-схемы для пользователей и совпадений
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    """Схема создания пользователя"""
    description: str = Field(..., min_length=10, description="Описание профиля пользователя")
    min_budget: float = Field(default=0.0, ge=0.0, description="Минимальный бюджет тендера")


class UserResponse(BaseModel):
    """Схема ответа с данными пользователя"""
    id: int
    description: str
    min_budget: float
    created_at: datetime

    model_config = {"from_attributes": True}


class MatchResponse(BaseModel):
    """Схема ответа с данными совпадения"""
    id: int
    user_id: int
    tender_id: str
    similarity: float
    personal_score: float
    final_score: float
    shown: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class MatchListResponse(BaseModel):
    """Список совпадений пользователя"""
    user_id: int
    matches: List[MatchResponse]
    total: int
