# Многоэтапная сборка для production-образа
FROM python:3.11-slim AS builder

# Устанавливаем системные зависимости для сборки пакетов
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    pkg-config \
    default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем и устанавливаем зависимости Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# --- Финальный образ ---
FROM python:3.11-slim

# Устанавливаем только runtime-зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем установленные пакеты из builder-этапа
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Копируем исходный код приложения
COPY app/ ./app/

# Создаём директории для моделей
RUN mkdir -p models/users

# Переменные окружения по умолчанию (переопределяются в docker-compose)
ENV DB_HOST=mysql \
    DB_USER=procurement_user \
    DB_PASSWORD=procurement_pass \
    DB_NAME=procurement_db \
    DB_PORT=3306 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Открываем порт приложения
EXPOSE 8000

# Запуск сервера Uvicorn в production-режиме
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--log-level", "info"]
