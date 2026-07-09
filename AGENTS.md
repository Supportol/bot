# Newsbot — руководство для агентов

Telegram-бот на **aiogram 3** для сбора автомобильных новостей, извлечения полного текста статей и обработки изображений. Язык интерфейса и сообщений — русский.

## Быстрый старт

```bash
python -m venv venv
source venv/bin/activate   # Linux/Mac
pip install -r requirements.txt
```

Создать `.env` в корне проекта:

```env
BOT_TOKEN=your_telegram_bot_token
NEWS_SOURCES=https://example.com/feed.xml,https://news.drom.ru/honda/
MAX_NEWS_PER_SOURCE=5
```

Запуск:

```bash
python bot.py
```

## Стек

| Компонент | Библиотека |
|-----------|------------|
| Telegram Bot API | aiogram 3.15 |
| HTTP-клиент | aiohttp |
| БД | aiosqlite (SQLite, `bot_database.db`) |
| Конфигурация | python-dotenv, pydantic-settings |
| RSS | feedparser |
| HTML-парсинг | BeautifulSoup4 + lxml |
| Извлечение текста | trafilatura |
| Обработка изображений | Pillow |

## Структура проекта

```
newsbot/
├── bot.py                 # Точка входа, регистрация роутеров, меню команд
├── config.py              # Настройки из .env и config.json
├── config.json            # Параметры обработки изображений
├── handlers/              # Обработчики команд Telegram
│   ├── news.py            # /news — RSS и источники из NEWS_SOURCES
│   ├── ixbt.py            # /ixbt — iXBT Car
│   ├── drom.py            # /drom — Drom.ru Honda
│   ├── list.py            # /list <drom|ixbt> — все публикации из БД
│   ├── processing.py      # /processing <id,...> — извлечение текста
│   ├── images.py          # /images + приём фото/документов
│   └── text.py            # /text — заглушка (не реализовано)
├── services/
│   ├── news_parser.py     # Парсеры RSS, HTML и специализированные
│   ├── text_extractor.py  # trafilatura: полный текст по URL
│   └── image_processor.py # Resize + размытый фон (Pillow)
└── database/
    └── db.py              # SQLite: publications
```

## Команды бота

| Команда | Описание |
|---------|----------|
| `/news` | Парсит все источники из `NEWS_SOURCES`. Сохраняет новые публикации в БД, возвращает ID. При отсутствии новых — показывает последние 5 из БД. |
| `/ixbt` | Парсит `https://www.ixbt.com/car/`. Только новые записи. Fallback — последние 5 из БД по этому источнику. |
| `/drom` | Парсит `https://news.drom.ru/honda/`. Аналогично `/ixbt`. |
| `/list drom` / `/list ixbt` | Все сохранённые публикации по источнику. Длинные ответы разбиваются на части (лимит Telegram ~4096 символов). |
| `/processing 1, 2, 3` | По ID скачивает страницы, извлекает текст (trafilatura), сохраняет в `full_text`, ставит `status = text_fetched`. |
| `/images` | Просит отправить фото. После `/images` или без него — обрабатывает `F.photo` и `F.document` (image/*). |
| `/text` | Заглушка: «будет реализована позже». |

Статусы публикаций в ответах: 🆕 `new`, ✅ `text_fetched`.

## База данных

Файл: `bot_database.db` (в `.gitignore` через `*.db`).

Таблица `publications`:

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | INTEGER PK | Автоинкремент, используется в `/processing` и списках |
| `title` | TEXT | Заголовок |
| `url` | TEXT UNIQUE | Дедупликация по URL |
| `source` | TEXT | URL источника (RSS-фид или страница раздела) |
| `full_text` | TEXT | Извлечённый текст (после `/processing`) |
| `status` | TEXT | `new` (по умолчанию) или `text_fetched` |
| `created_at` | TIMESTAMP | Время добавления |

Ключевые функции в `database/db.py`:

- `save_publication()` — возвращает `id` новой записи или `None`, если URL уже есть
- `check_url_exists()` — проверка перед парсингом в `parse_new_sources()`
- `get_publications_by_ids()`, `update_publication_text()`
- `get_latest_publications()`, `get_publications_by_source()`

## Парсинг новостей (`services/news_parser.py`)

`parse_new_sources()` читает `NEWS_SOURCES` (через запятую) и выбирает парсер по URL:

| Условие | Парсер |
|---------|--------|
| URL содержит `rss`, `feed`, `xml`, `atom` | `parse_rss_feed()` — feedparser |
| Домен `drom.ru` | `parse_drom_honda()` — 3 стратегии (b-info-block, /info/, по датам) |
| Домен `ixbt.com` | `parse_ixbt_car()` — ссылки с `/car/`, без категорий `/car/\d+/` |
| Домен `motor.ru` | `parse_motor_search()` — `/news/`, `/articles/`, `/test-drives/` |
| Остальное | `parse_generic_html()` — `<article>` или классы news/article/post |

Лимит на источник: `MAX_NEWS_PER_SOURCE` (по умолчанию 5). Парсинг источников — параллельно через `asyncio.gather`.

Команды `/ixbt` и `/drom` вызывают специализированные парсеры напрямую, не через `NEWS_SOURCES`.

## Извлечение текста

`services/text_extractor.py`: HTTP GET → `trafilatura.extract()` с `favor_precision=True`. При пустом результате — `ValueError`.

## Обработка изображений

Настройки в `config.json`:

```json
{
  "image_processing": {
    "width": 1000,
    "height": 500,
    "quality": 85
  }
}
```

Алгоритм (`image_processor.py`): размытый фон на целевой размер + вписанное по центру фото с сохранением пропорций → JPEG.

## Конфигурация

- **`.env`** — секреты и runtime: `BOT_TOKEN`, `NEWS_SOURCES`, `MAX_NEWS_PER_SOURCE`
- **`config.json`** — только параметры изображений (не секреты)
- **`config.py`** — `settings`, `news_sources_list`, `image_config`, `max_news_per_source`

Не коммитить `.env` и `*.db`.

## Архитектурные соглашения

- Каждая команда — отдельный роутер в `handlers/`, подключается в `bot.py`
- Бизнес-логика парсинга/обработки — в `services/`, не в хендлерах
- HTML-ответы бота: `parse_mode=HTML`, превью ссылок отключено где уместно
- Дедупликация новостей — только по `url` в БД
- Отладочный вывод парсеров — через `print()` с префиксами `[RSS]`, `[DROM]`, `[IXBT-CAR]` и т.д.

## Расширение проекта

**Новый источник новостей:**

1. Добавить URL в `NEWS_SOURCES` (для `/news`) или создать хендлер по образцу `ixbt.py`/`drom.py`
2. При нестандартной вёрстке — новая функция в `news_parser.py` и ветка в `parse_new_sources()`
3. Для `/list` — расширить `SOURCE_MAPPING` в `handlers/list.py`

**Новая команда:**

1. Создать `handlers/<name>.py` с `router = Router()`
2. Экспортировать в `handlers/__init__.py`
3. Подключить в `bot.py` и добавить в `set_bot_commands()`

**Команда `/text`:** сейчас заглушка в `handlers/text.py` — место для будущего функционала преобразования текста.

## Ограничения и заметки

- README устарел: не упоминает `/ixbt`, `/drom`, `/list`
- `get_publications_by_ids()` не возвращает извлечённый текст пользователю — только обновляет БД и отчёт об успехе/ошибках
- Парсеры зависят от вёрстки сайтов; при изменении HTML стратегии могут перестать находить новости
- Таймаут HTTP-запросов: 15 секунд
- Python 3.10+

## Типичный workflow пользователя

1. `/drom` или `/ixbt` — собрать новые публикации, получить ID
2. `/list drom` — просмотреть все сохранённые
3. `/processing 12, 13` — извлечь полный текст статей в БД
4. `/images` — отправить фото для ресайза под 1000×500
