"""
Инициализация подключения к базе данных через SQLAlchemy
"""
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import DATABASE_URL

logger = logging.getLogger(__name__)

# Создаём движок с пулом соединений
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,        # Проверять соединение перед использованием
    pool_recycle=3600,         # Переиспользовать соединения каждый час
    pool_size=10,
    max_overflow=20,
    echo=False,
)

# Фабрика сессий
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Базовый класс для всех ORM-моделей"""
    pass


def get_db():
    """
    Зависимость FastAPI — предоставляет сессию БД и закрывает её после запроса
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as exc:
        logger.error("Ошибка в сессии БД: %s", exc)
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    """
    Создаёт все таблицы в базе данных при запуске приложения
    """
    # Импорт всех моделей необходим для регистрации метаданных
    from app.models import raw_tender, it_tender, user, match, feedback  # noqa: F401
    Base.metadata.create_all(bind=engine)
    logger.info("Таблицы базы данных инициализированы")
