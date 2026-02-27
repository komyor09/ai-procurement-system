"""
Конфигурация приложения — загрузка переменных окружения
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Настройки подключения к базе данных
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "secret")
DB_NAME = os.getenv("DB_NAME", "procurement")
DB_PORT = int(os.getenv("DB_PORT", "3306"))

# Строка подключения SQLAlchemy
DATABASE_URL = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    "?charset=utf8mb4"
)

# Путь к директории с моделями
MODELS_DIR = os.getenv("MODELS_DIR", "models")
GLOBAL_MODEL_PATH = os.path.join(MODELS_DIR, "global_model.pkl")
USER_MODELS_DIR = os.path.join(MODELS_DIR, "users")

# Название модели для эмбеддингов
EMBEDDING_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

# Порог вероятности для глобального классификатора IT-тендеров
IT_PROBABILITY_THRESHOLD = 0.6

# Порог косинусного сходства для матчинга
MATCHING_SIMILARITY_THRESHOLD = 0.55

# Минимальное количество отзывов для переобучения глобальной модели
GLOBAL_RETRAIN_MIN_FEEDBACK = 100

# Минимальное количество отзывов для переобучения персональной модели
USER_RETRAIN_MIN_FEEDBACK = 20
