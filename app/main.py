"""
Точка входа FastAPI-приложения.
Инициализация БД, планировщика и регистрация роутов.
"""
import logging
import os
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.scheduler import start_scheduler, stop_scheduler
from app.api.user_routes import router as user_router
from app.api.admin_routes import router as admin_router

# Настройка логирования в формате production
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Создаём приложение FastAPI
app = FastAPI(
    title="AI Procurement System",
    description="Система автоматического поиска и матчинга IT-тендеров с пользователями",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Настройка CORS для клиентских приложений
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Регистрация роутов
app.include_router(user_router)
app.include_router(admin_router)


@app.on_event("startup")
async def on_startup() -> None:
    """
    Инициализация при запуске приложения:
    - Создание таблиц в БД
    - Создание директорий для моделей
    - Запуск планировщика задач
    """
    logger.info("Запуск приложения AI Procurement System")

    # Создаём директории для хранения моделей
    os.makedirs("models/users", exist_ok=True)

    # Инициализируем схему базы данных
    init_db()

    # Запускаем планировщик фоновых задач
    start_scheduler()

    logger.info("Приложение успешно запущено")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    """Корректное завершение: остановка планировщика"""
    stop_scheduler()
    logger.info("Приложение остановлено")


@app.get("/health", tags=["system"])
def health_check() -> dict:
    """Проверка работоспособности сервиса"""
    return {"status": "ok", "service": "ai-procurement-system"}
