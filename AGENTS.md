# Newsbot — руководство для агентов

Telegram-бот на **aiogram 3** для сбора автомобильных новостей, извлечения полного текста статей и обработки изображений. Язык интерфейса и сообщений — русский.

> **Правило для агентов:** при любом изменении архитектуры, команд, схемы БД, конфигурации, парсеров, форматов ID, путей к файлам или workflow — **обязательно обновляй этот файл в том же PR/коммите**. Информация в `AGENTS.md` должна неукоснительно отражать текущее состояние проекта. Если сомневаешься — лучше обновить лишний раз, чем оставить устаревшее описание.

## Быстрый старт

```bash
python3 -m venv venv
source venv/bin/activate   # Linux/Mac
pip install -r requirements.txt
```

Создать `.env` в корне проекта (см. `.env.example`):

```env
BOT_TOKEN=your_telegram_bot_token
NEWS_SOURCES=https://example.com/feed.xml,https://news.drom.ru/honda/
IXBT_SOURCES=https://api.ixbt.com/v0/publications/search?search=HONDA,https://api.ixbt.com/v0/publications/search?search=ACURA
MAX_NEWS_PER_SOURCE=5
```

Запуск:

```bash
python3 bot.py
```

Фоновый запуск (скрипты в корне, в `.gitignore`):

| Скрипт | Назначение |
|--------|------------|
| `start.sh` | venv + фоновый запуск, PID в `.bot.pid`, лог в `bot.log` |
| `stop.sh` | остановка бота |
| `restart.sh` | stop → sleep → start |
| `reset-db.sh` | удаление `bot_database.db` |

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
├── bot.py                     # Точка входа, регистрация роутеров, меню команд
├── config.py                  # Настройки из .env и config.json
├── config.json                # Параметры обработки изображений
├── handlers/
│   ├── news.py                # /news — RSS и источники из NEWS_SOURCES
│   ├── ixbt.py                # /ixbt — iXBT API (Honda/Acura)
│   ├── drom.py                # /drom — Drom.ru Honda
│   ├── list.py                # /list <drom|ixbt> — таблица публикаций
│   ├── processing.py          # /processing <ID,...> — извлечение текста
│   ├── images.py              # /images <ID,...> + приём фото/документов
│   └── text.py                # /text — заглушка (не реализовано)
├── services/
│   ├── news_parser.py         # Парсеры RSS, HTML, iXBT API
│   ├── text_extractor.py      # trafilatura: полный текст по URL
│   ├── image_processor.py     # Resize + размытый фон (Pillow)
│   ├── cover_storage.py       # Скачивание обложек iXBT
│   ├── publication_id.py      # Генерация строковых ID по источнику
│   └── datetime_utils.py      # Форматирование pubdatetime
├── database/
│   └── db.py                  # SQLite: publications
└── images/                    # Обложки публикаций (в .gitignore)
    └── .gitkeep
```

## Команды бота

| Команда | Описание |
|---------|----------|
| `/news` | Парсит все источники из `NEWS_SOURCES`. Сохраняет новые публикации в БД, возвращает ID. При отсутствии новых — последние 5 из БД. |
| `/ixbt` | Парсит API-источники из `IXBT_SOURCES`. Сохраняет новые записи, скачивает обложки. Требует `IXBT_SOURCES` в `.env`. Fallback — последние 5 из БД. |
| `/drom` | Парсит `https://news.drom.ru/honda/`. Аналогично `/ixbt`. |
| `/list drom` / `/list ixbt` | Таблица всех публикаций по источнику: **ID**, **дата/время**, **заголовок (ссылка)**. Новые сверху. Длинные ответы разбиваются (~4000 символов). |
| `/processing IX_HON_1, IX_AC_2` | По ID скачивает страницы, извлекает текст (trafilatura), сохраняет в `full_text`, ставит `status = text_fetched`. |
| `/images IX_HON_1, IX_AC_2` | Обрабатывает сохранённые обложки по ID. Без аргументов — просит указать ID. Также принимает `F.photo` и `F.document` (image/*) для произвольных фото. |
| `/text` | Заглушка: «будет реализована позже». |

Статусы публикаций в ответах: 🆕 `new`, ✅ `text_fetched`.

## Идентификаторы публикаций

ID — **строка** (`TEXT PRIMARY KEY`), отдельная нумерация для каждого источника:

| Источник | Префикс | Примеры |
|----------|---------|---------|
| iXBT Honda (`search=HONDA`) | `IX_HON` | `IX_HON_1`, `IX_HON_2` |
| iXBT Acura (`search=ACURA`) | `IX_AC` | `IX_AC_1`, `IX_AC_77` |
| Drom.ru Honda | `DR_HON` | `DR_HON_1` |
| Прочие | `GEN` | `GEN_1` |

Логика в `services/publication_id.py`:

- `get_source_id_prefix(source)` — префикс по URL источника
- `next_publication_id(prefix, existing_ids)` — следующий свободный номер
- `parse_publication_ids(text)` — извлечение ID из аргументов команд (`/processing`, `/images`)

Обложки сохраняются в поддиректории с именем ID:

```
images/IX_HON_1/cover.jpg
images/IX_AC_2/cover.webp
```

При старте бота выполняется миграция со старых числовых `INTEGER id` на строковые ID.

## База данных

Файл: `bot_database.db` (в `.gitignore` через `*.db`).

Таблица `publications`:

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | TEXT PK | Строковый ID (`IX_HON_1`, `IX_AC_2`, …) |
| `title` | TEXT | Заголовок |
| `url` | TEXT UNIQUE | Дедупликация по URL |
| `source` | TEXT | URL источника (RSS-фид, страница раздела или API URL с `page=1`) |
| `full_text` | TEXT | Извлечённый текст (после `/processing`) |
| `status` | TEXT | `new` (по умолчанию) или `text_fetched` |
| `published_at` | TEXT | ISO-дата публикации (`pubdatetime` из API iXBT) |
| `cover_path` | TEXT | Относительный путь к обложке (`images/IX_HON_1/cover.jpg`) |
| `created_at` | TIMESTAMP | Время добавления в БД |

Сортировка по дате публикации: `ORDER BY (published_at IS NULL), published_at DESC, created_at DESC`.

Ключевые функции в `database/db.py`:

- `init_db()` — создание таблицы, миграции колонок и ID
- `save_publication()` — возвращает строковый `id` новой записи или `None`, если URL уже есть
- `check_url_exists()` — проверка перед парсингом
- `get_publications_by_ids()`, `update_publication_text()`, `update_publication_cover_path()`
- `get_latest_publications()`, `get_publications_by_source()`, `get_publications_by_sources()`

## Парсинг новостей (`services/news_parser.py`)

### `/news` — `parse_new_sources()`

Читает `NEWS_SOURCES` (через запятую) и выбирает парсер по URL:

| Условие | Парсер |
|---------|--------|
| URL содержит `rss`, `feed`, `xml`, `atom` | `parse_rss_feed()` — feedparser |
| Домен `drom.ru` | `parse_drom_honda()` — 3 стратегии (b-info-block, /info/, по датам) |
| Домен `ixbt.com` | `parse_ixbt_car()` — ссылки с `/car/` (legacy HTML-парсер) |
| Домен `motor.ru` | `parse_motor_search()` — `/news/`, `/articles/`, `/test-drives/` |
| Остальное | `parse_generic_html()` — `<article>` или классы news/article/post |

### `/ixbt` — `parse_ixbt_sources()`

Парсит API iXBT (`/api/publications/search` или аналог из `IXBT_SOURCES`):

- Пагинация до `MAX_NEWS_PER_SOURCE` записей на источник (макс. 30 страниц)
- Фильтр по бренду: заголовок, подзаголовок, теги (`HONDA` / `ACURA`, границы слов — исключает ложные срабатывания вроде «Lada Aura»)
- `source` в БД — нормализованный API URL с `page=1` (`_ixbt_source_key()`)
- `published_at` — ISO `pubdatetime` из ответа API (не `formated_pubdatetime`)
- `cover_url` — скачивается в `handlers/ixbt.py` через `cover_storage`

Команды `/ixbt` и `/drom` вызывают специализированные парсеры напрямую, не через `NEWS_SOURCES`.

Лимит на источник: `MAX_NEWS_PER_SOURCE` (по умолчанию 5). Парсинг источников — параллельно через `asyncio.gather`.

## Даты публикаций

`services/datetime_utils.py`:

- В БД хранится ISO `pubdatetime` (`2026-07-05T17:03:00+03:00`)
- Отображение: `ДД.ММ.ГГГГ чч:мм` (`05.07.2026 17:03`)
- `format_publication_datetime()` — для вывода в `/list`, `/ixbt`
- `publication_sort_key()` — сортировка по `published_at`, затем `created_at`

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

Обложки iXBT (`cover_storage.py`): скачивание по `cover_url` → `images/<pub_id>/cover.<ext>`.

## Конфигурация

- **`.env`** — секреты и runtime:
  - `BOT_TOKEN` — токен Telegram-бота
  - `NEWS_SOURCES` — источники для `/news` (через запятую)
  - `IXBT_SOURCES` — API URL для `/ixbt` и `/list ixbt` (через запятую)
  - `MAX_NEWS_PER_SOURCE` — лимит новостей с одного источника (по умолчанию 5)
- **`config.json`** — только параметры изображений (не секреты)
- **`config.py`** — `settings`, `news_sources_list`, `ixbt_sources_list`, `image_config`, `max_news_per_source`

Не коммитить: `.env`, `*.db`, `images/**`, `*.log`, `*.pid`, `venv`, `*.sh`.

## Архитектурные соглашения

- Каждая команда — отдельный роутер в `handlers/`, подключается в `bot.py`
- Бизнес-логика парсинга/обработки — в `services/`, не в хендлерах
- HTML-ответы бота: `parse_mode=HTML`, превью ссылок отключено где уместно
- Дедупликация новостей — только по `url` в БД
- Отладочный вывод парсеров — через `print()` с префиксами `[RSS]`, `[DROM]`, `[IXBT-API]`, `[IXBT-CAR]` и т.д.
- Импорт `services.publication_id` в `database/db.py` — ленивый (внутри функций), чтобы избежать циклического импорта

## Расширение проекта

**Новый источник новостей:**

1. Добавить URL в `NEWS_SOURCES` (для `/news`) или создать хендлер по образцу `ixbt.py`/`drom.py`
2. При нестандартной вёрстке — новая функция в `news_parser.py` и ветка в `parse_new_sources()`
3. Для `/list` — расширить `SOURCE_MAPPING` в `handlers/list.py`
4. Для строковых ID — добавить префикс в `get_source_id_prefix()` в `publication_id.py`
5. **Обновить `AGENTS.md`**

**Новая команда:**

1. Создать `handlers/<name>.py` с `router = Router()`
2. Экспортировать в `handlers/__init__.py`
3. Подключить в `bot.py` и добавить в `set_bot_commands()`
4. **Обновить `AGENTS.md`**

**Команда `/text`:** заглушка в `handlers/text.py` — место для будущего функционала преобразования текста.

## Ограничения и заметки

- README устарел относительно текущего функционала — ориентироваться на `AGENTS.md`
- `get_publications_by_ids()` не возвращает извлечённый текст пользователю — только обновляет БД и отчёт
- Парсеры зависят от вёрстки/API сайтов; при изменениях стратегии могут перестать находить новости
- Таймаут HTTP-запросов: 15 секунд
- Python 3.10+ (на Linux использовать `python3`, не `python`)
- После смены схемы ID рекомендуется `./reset-db.sh` и повторный парсинг

## Типичный workflow пользователя

1. `/ixbt` или `/drom` — собрать новые публикации, получить ID (`IX_HON_1`, …)
2. `/list ixbt` — просмотреть таблицу всех сохранённых
3. `/processing IX_HON_1, IX_AC_2` — извлечь полный текст статей в БД
4. `/images IX_HON_1` — обработать сохранённые обложки (или отправить произвольное фото)
