# AI Procurement System

Система автоматического поиска и матчинга IT-тендеров с пользователями на базе ML.

---

## Data Flow

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────────┐
│   Parsers   │────▶│ raw_tenders  │────▶│  Embedding Service  │
└─────────────┘     └──────────────┘     └──────────┬──────────┘
                                                     │
                                          ┌──────────▼──────────┐
                                          │  Global Classifier  │
                                          │  (LogisticRegress.) │
                                          └──────────┬──────────┘
                                                     │ IT only
                                          ┌──────────▼──────────┐
                                          │     it_tenders      │
                                          └──────────┬──────────┘
                                                     │
                                          ┌──────────▼──────────┐
                                          │   Matching Engine   │
                                          │ (cosine similarity) │
                                          └──────────┬──────────┘
                                                     │
                                          ┌──────────▼──────────┐
                                          │       matches       │
                                          └──────────┬──────────┘
                                                     │ user feedback
                                          ┌──────────▼──────────┐
                                          │     Retraining      │
                                          │  (global + personal)│
                                          └─────────────────────┘
```

---

## Архитектура

```
Layer 0: Парсеры      → Сбор сырых тендеров
Layer 1: IT-фильтр    → Классификация LogisticRegression (глобальная)
Layer 2: Матчинг      → Косинусное сходство + персональная модель
Feedback: Обратная связь → Переобучение моделей
```

---

## Стек технологий

- **Python 3.11** + **FastAPI**
- **MySQL 8** + **SQLAlchemy 2.0**
- **sentence-transformers** (`paraphrase-multilingual-MiniLM-L12-v2`)
- **scikit-learn** (LogisticRegression)
- **APScheduler** (фоновые задачи)
- **Docker** + **docker-compose**

---

## Быстрый старт

```bash
git clone <repo-url>
cd ai-procurement-system
cp .env.example .env
docker-compose up --build -d
curl http://localhost:8000/health
```

---

## API Endpoints

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/users/create` | Создать пользователя |
| GET | `/users/{id}` | Профиль пользователя |
| GET | `/users/{id}/matches` | Совпадения пользователя |
| POST | `/users/{id}/feedback` | Отправить обратную связь |
| POST | `/admin/retrain/global` | Переобучить глобальную модель |
| POST | `/admin/retrain/user/{id}` | Переобучить модель пользователя |
| POST | `/admin/parse` | Запустить парсеры вручную |
| POST | `/admin/classify` | Запустить классификацию вручную |
| POST | `/admin/match` | Запустить матчинг вручную |
| GET | `/health` | Статус сервиса |
| GET | `/docs` | Swagger UI документация |

---

## Расписание задач

| Задача | Интервал |
|--------|----------|
| Парсинг тендеров | каждые 30 минут |
| IT-классификация | каждый час |
| Матчинг пользователей | каждые 15 минут |
| Переобучение моделей | ежедневно в 02:00 UTC |

---

## Логика слоёв

### Layer 1: Глобальный IT-фильтр

LogisticRegression предсказывает вероятность IT-принадлежности тендера.
При вероятности ≥ 0.6 тендер сохраняется в `it_tenders`.

**Cold-start режим** (модель ещё не обучена):

Пока файл `models/global_model.pkl` отсутствует или модель не прошла обучение,
система работает в cold-start режиме. В этом режиме **все тендеры временно
пропускаются в `it_tenders`** без реальной классификации. Такие записи
сохраняются с `model_version=0`.

После первого обучения модели (достигнут порог в 100 отзывов или вызван
`/admin/retrain/global?force=true`) можно переклассифицировать cold-start
тендеры, выбрав записи в `it_tenders` с `model_version=0`.

### Layer 2: Персональный матчинг

- Косинусное сходство между эмбеддингом пользователя и тендера
- Порог: `similarity ≥ 0.55` AND `budget ≥ user.min_budget`

**Итоговый скор:**

| Состояние персональной модели | Формула |
|-------------------------------|---------|
| Модель обучена | `final_score = 0.7 × similarity + 0.3 × personal_score` |
| Cold-start (нет обученной модели) | `final_score = similarity` |

В cold-start режиме персональный скор игнорируется полностью — матчинг
опирается исключительно на косинусное сходство. После накопления ≥ 20 отзывов
персональная модель обучается и начинает влиять на ранжирование.

### Система обратной связи

- Комментарий содержит `"маленьк"` → обновляет `user.min_budget` до бюджета тендера
- После **100 отзывов** глобально → переобучение глобальной модели
- После **20 отзывов** на пользователя → переобучение персональной модели

---

## Хранение эмбеддингов

Эмбеддинги хранятся в MySQL в колонках типа **LONGTEXT** в виде JSON-массива чисел.

```
# Пример значения в БД:
[0.1234, -0.5678, 0.9012, ...]   # 384 числа для MiniLM-L12-v2
```

При чтении из БД они десериализуются в `numpy.ndarray` через функции
`deserialize_embedding()` / `serialize_embedding()` в `embedding_service.py`.

**Компромиссы производительности:**

- JSON-хранение проще в реализации и обслуживании
- JSON занимает ~4× больше места по сравнению с бинарным форматом (BLOB)
- Операции десериализации добавляют незначительные накладные расходы на CPU
- Для MVP (< 100 000 тендеров) эти компромиссы приемлемы
- При масштабировании рекомендуется переход на PostgreSQL + pgvector (см. ниже)

---

## Версионирование моделей

Каждая глобальная модель имеет целочисленную версию, хранящуюся в
`models/global_model_meta.json`. Версия инкрементируется при каждом
успешном переобучении.

Поле `model_version` в таблице `it_tenders` фиксирует, какой версией модели
был классифицирован тендер:

| Значение | Смысл |
|----------|-------|
| `0` | Cold-start: тендер пропущен без классификации |
| `≥ 1` | Версия модели, выполнившей классификацию |

Это позволяет при необходимости переклассифицировать устаревшие записи
после существенного обновления модели.

---

## Дедупликация тендеров

Уникальность тендера определяется составным ключом **(source, url)**:

- Один и тот же URL от разных источников считается разными тендерами
- Перед каждой вставкой выполняется явная проверка по `(source, url)`
- В таблице `raw_tenders` задан `UniqueConstraint("source", "url")` — второй
  уровень защиты на уровне БД

---

## Переменные окружения

```
DB_HOST       - хост MySQL (default: localhost)
DB_USER       - пользователь БД
DB_PASSWORD   - пароль БД
DB_NAME       - имя БД
DB_PORT       - порт (default: 3306)
```

---

## Scaling Considerations

The current architecture is optimised for an MVP with up to ~100 000 tenders.

**Current approach (MySQL + JSON embeddings):**
- Simple to operate, zero additional infrastructure
- JSON deserialization on every read adds CPU overhead
- No native vector index — similarity search loads all embeddings into memory
- Suitable for a single-node deployment with a small user base

**For high-scale deployments (> 500 000 tenders or > 1 000 active users):**

| Concern | Recommendation |
|---------|---------------|
| Vector search | Migrate embeddings to **PostgreSQL + pgvector** for native ANN index |
| Storage size | Store embeddings as binary (`BYTEA` / BLOB) instead of JSON |
| Throughput | Run matching workers as separate horizontally-scaled processes |
| Classification | Serve the global model via a dedicated ML inference service (e.g. TorchServe) |
| Scheduler | Replace APScheduler with a distributed queue (Celery + Redis / RabbitMQ) |

The data model and service boundaries are already isolated such that a MySQL →
PostgreSQL migration requires changes only in `database.py`, `config.py`, and
the `LONGTEXT` column declarations.

---

## Структура проекта

```
ai-procurement-system/
├── app/
│   ├── main.py                    # Точка входа FastAPI
│   ├── config.py                  # Конфигурация
│   ├── database.py                # Подключение к БД
│   ├── scheduler.py               # Планировщик задач
│   ├── models/                    # ORM-модели
│   │   ├── raw_tender.py          # UniqueConstraint(source, url)
│   │   ├── it_tender.py           # + model_version field
│   │   ├── user.py
│   │   ├── match.py
│   │   └── feedback.py
│   ├── schemas/                   # Pydantic-схемы
│   │   ├── user_schema.py
│   │   └── feedback_schema.py
│   ├── services/                  # Бизнес-логика
│   │   ├── parser_service.py      # Дедупликация по (source, url)
│   │   ├── embedding_service.py   # serialize/deserialize_embedding()
│   │   ├── global_classifier_service.py  # Cold-start + versioning
│   │   ├── matching_service.py    # Personal model cold-start
│   │   └── retraining_service.py  # increment_model_version()
│   ├── parsers/                   # Парсеры тендеров
│   │   ├── base_parser.py
│   │   └── goszakup_parser.py
│   └── api/                       # API-роуты
│       ├── user_routes.py
│       └── admin_routes.py
├── models/
│   ├── global_model.pkl           # (генерируется после обучения)
│   ├── global_model_meta.json     # {"version": N}
│   └── users/                     # Персональные модели user_{id}.pkl
├── Dockerfile
├── docker-compose.yml
├── init.sql
├── requirements.txt
└── README.md
```
