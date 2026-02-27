"""
Планировщик фоновых задач на основе APScheduler.
Управляет периодическим запуском парсеров, классификации и матчинга.
"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from app.database import SessionLocal
from app.services.parser_service import run_all_parsers
from app.services.global_classifier_service import classify_new_tenders
from app.services.matching_service import run_matching_all_users
from app.services.retraining_service import run_daily_retraining

logger = logging.getLogger(__name__)

# Глобальный экземпляр планировщика
scheduler = BackgroundScheduler(timezone="UTC")


def _job_run_parsers() -> None:
    """Задача: запуск парсеров тендеров каждые 30 минут"""
    logger.info("[Scheduler] Запуск задачи парсинга")
    db = SessionLocal()
    try:
        count = run_all_parsers(db)
        logger.info("[Scheduler] Парсинг завершён: %d новых тендеров", count)
    except Exception as exc:
        logger.error("[Scheduler] Ошибка задачи парсинга: %s", exc, exc_info=True)
    finally:
        db.close()


def _job_classify_tenders() -> None:
    """Задача: классификация новых тендеров каждый час"""
    logger.info("[Scheduler] Запуск задачи классификации")
    db = SessionLocal()
    try:
        count = classify_new_tenders(db)
        logger.info("[Scheduler] Классификация завершена: %d IT-тендеров", count)
    except Exception as exc:
        logger.error("[Scheduler] Ошибка задачи классификации: %s", exc, exc_info=True)
    finally:
        db.close()


def _job_run_matching() -> None:
    """Задача: матчинг пользователей с тендерами каждые 15 минут"""
    logger.info("[Scheduler] Запуск задачи матчинга")
    db = SessionLocal()
    try:
        count = run_matching_all_users(db)
        logger.info("[Scheduler] Матчинг завершён: %d новых совпадений", count)
    except Exception as exc:
        logger.error("[Scheduler] Ошибка задачи матчинга: %s", exc, exc_info=True)
    finally:
        db.close()


def _job_daily_retrain() -> None:
    """Задача: ежедневное переобучение моделей в 02:00 UTC"""
    logger.info("[Scheduler] Запуск задачи ежедневного переобучения")
    db = SessionLocal()
    try:
        run_daily_retraining(db)
        logger.info("[Scheduler] Переобучение завершено")
    except Exception as exc:
        logger.error("[Scheduler] Ошибка задачи переобучения: %s", exc, exc_info=True)
    finally:
        db.close()


def start_scheduler() -> None:
    """
    Регистрирует все задачи и запускает планировщик.
    Вызывается при старте приложения.
    """
    # Парсинг каждые 30 минут
    scheduler.add_job(
        _job_run_parsers,
        trigger=IntervalTrigger(minutes=30),
        id="run_parsers",
        name="Парсинг тендеров",
        replace_existing=True,
        max_instances=1,
    )

    # Классификация каждый час
    scheduler.add_job(
        _job_classify_tenders,
        trigger=IntervalTrigger(hours=1),
        id="classify_tenders",
        name="Классификация тендеров",
        replace_existing=True,
        max_instances=1,
    )

    # Матчинг каждые 15 минут
    scheduler.add_job(
        _job_run_matching,
        trigger=IntervalTrigger(minutes=15),
        id="run_matching",
        name="Матчинг тендеров",
        replace_existing=True,
        max_instances=1,
    )

    # Переобучение ежедневно в 02:00 UTC
    scheduler.add_job(
        _job_daily_retrain,
        trigger=CronTrigger(hour=2, minute=0),
        id="daily_retrain",
        name="Ежедневное переобучение",
        replace_existing=True,
        max_instances=1,
    )

    scheduler.start()
    logger.info("Планировщик задач запущен")


def stop_scheduler() -> None:
    """Останавливает планировщик при завершении приложения."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Планировщик задач остановлен")
