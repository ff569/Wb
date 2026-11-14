# WB Детектор

SaaS-бот мониторинга цен Wildberries для селлеров: следит за ценами 24/7 и присылает алерты при падении цены или достижении целевой.

## Возможности

- Мониторинг до 50 товаров (Pro) с проверкой каждый час
- Алерты: падение цены на N% (настраивается) или достижение целевой цены
- Добавление товара одной ссылкой, целевая цена — через пробел после ссылки
- «Проверить сейчас» — внеочередная проверка
- Настройки: вкл/выкл алертов, порог падения 3/5/10/15%
- Подписка Pro за Telegram Stars (XTR), без карт и внешних платёжек
- Антифлуд, авто-регистрация пользователей, скрытая админ-команда `/stats`
- SQLite (WAL), Repository pattern, фоновый asyncio-планировщик

## Структура

```
main.py                  # точка входа: webhook (aiohttp) или polling, запуск планировщика
app/
  config.py              # настройки из окружения
  texts.py               # все тексты UI (приветствие, FAQ, ошибки, алерты)
  utils.py               # парсинг ссылок и целевой цены
  database/
    db.py                # aiosqlite-подключение, WAL, схема
    repositories.py      # Repository pattern: users, tracks, payments
  services/
    wb_api.py            # клиент WB API: таймауты, ретраи с backoff, батчи по 100
    scheduler.py         # фоновый цикл проверки цен и рассылки алертов
  middlewares/
    registration.py      # авто-регистрация пользователя, инъекция репозиториев
    antiflood.py         # rate limiter (20 сообщений/мин)
  keyboards/
    reply.py             # reply-меню
    inline.py            # все inline-клавиатуры
  handlers/
    common.py            # /start, /help, навигация
    monitoring.py        # добавление/список/удаление товаров, проверка сейчас
    subscription.py      # оплата Stars, pre-checkout, активация Pro
    settings.py          # настройки алертов
    admin.py             # /stats для владельца
```

## Деплой на Render

1. Создай **Web Service** из своего GitHub-репозитория.
2. Runtime: **Python 3** (или используй `render.yaml` — Render подхватит его автоматически).
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `python main.py`
5. Environment Variables:
   - `BOT_TOKEN` — токен из @BotFather
   - `ADMIN_IDS` — твой Telegram ID (узнать: @userinfobot)
   - `WEBHOOK_SECRET` — любая случайная строка (Render может сгенерировать)
   - `RENDER_EXTERNAL_URL` — Render подставит сам
6. Health Check Path: `/health`

`RENDER_EXTERNAL_URL` подставляется автоматически — бот сам зарегистрирует webhook при старте. Если переменная пуста (локальный запуск), бот работает в polling-режиме.

### Пинг, чтобы бесплатный инстанс не засыпал

Free-план Render засыпает после 15 минут без HTTP-запросов. Настрой внешний cron (например, cron-job.org, каждые 10 минут):

```
GET https://<твой-app>.onrender.com/health
```

### Важно про SQLite на бесплатном плане

Файловая система бесплатного инстанса эфемерна: при каждом деплое база пересоздаётся. Для продакшена подключи Render Disk (платно) и укажи `DB_PATH=/var/data/wb_detector.db`, либо смирись с потерей базы на редеплое на старте проекта.

## Telegram Stars: что включить

1. В @BotFather: `/mybots` → бот → **Payments** → включи **Stars payments** (если предлагается).
2. Оплата идёт валютой `XTR` с пустым provider-токеном — код уже готов.

## Локальный запуск

```bash
pip install -r requirements.txt
export BOT_TOKEN=...
export ADMIN_IDS=...
python main.py   # без RENDER_EXTERNAL_URL запустится polling
```

## Админка

`/stats` — только для ID из `ADMIN_IDS`: пользователи (+новые за 24ч), активные Pro, товары в мониторинге, выручка в Stars (всего и за 24ч), число платежей.
