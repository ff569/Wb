# WB Детектор

Telegram-бот мониторинга цен Wildberries для селлеров.

## Быстрый запуск на Render

1. Создай Web Service, подключи GitHub-репозиторий.
2. Environment: **Python 3**.
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `python bot.py`
5. Environment Variables:
   - `BOT_TOKEN` — токен из @BotFather
   - `RENDER_EXTERNAL_URL` — Render подставит сам
6. Deploy.

## Переход на PostgreSQL + Docker (для масштабирования)

Замени SQLite на PostgreSQL через `asyncpg` + `SQLAlchemy 2.0`:
- Добавь в `requirements.txt`: `asyncpg`, `sqlalchemy[asyncio]`, `alembic`.
- Замени `sqlite3` на `AsyncSession` в `bot.py`.
- Dockerfile + docker-compose.yml — в `deploy/`.

## Админ-панель

Добавь свой Telegram ID в переменную `ADMIN_IDS` — и получишь команду `/admin` со статистикой.

## Промокоды

Таблица `promocodes` (создаётся в миграции). Выдавай через админку.
