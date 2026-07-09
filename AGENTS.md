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
DROM_SOURCES=https://news.drom.ru/honda/
IXBT_SOURCES=https://api.ixbt.com/v0/publications/search?search=HONDA,https://api.ixbt.com/v0/publications/search?search=ACURA
MOTOR_HONDA_SOURCE=https://motor.ru/api/bebop/v2/search?query=Honda&offset=0&limit=15&include=image,rubric
MOTOR_ACURA_SOURCE=https://motor.ru/api/bebop/v2/search?query=Acura&offset=0&limit=15&include=image,rubric
TEXT_API_KEY=your_text_ru_api_key
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
│   ├── news.py                # /news — источники из DROM_SOURCES
│   ├── ixbt.py                # /ixbt — iXBT API (Honda/Acura)
│   ├── drom.py                # /drom — Drom.ru Honda
│   ├── motor.py               # /motor — Motor.ru API (Honda/Acura)
│   ├── list.py                # /list <drom|ixbt|motor> — таблица публикаций
│   ├── processing.py          # /processing <ID,...> — извлечение текста
│   ├── images.py              # /images <ID,...> + приём фото/документов
│   ├── text.py                # /text <ID,...> — экспорт source.md + изображения
│   └── rewrite.py             # /rewrite <ID,...> — рерайт текста через TEXT.ru API
├── services/
│   ├── news_parser.py         # Парсеры RSS, HTML, iXBT API
│   ├── text_extractor.py      # trafilatura: полный текст по URL
│   ├── rewrite_service.py     # Клиент TEXT.ru: создание задачи и polling результата
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
| `/news` | Сводная команда: **последовательно** запускает `iXBT → Drom → Motor`, сохраняет новые публикации и возвращает ID. При отсутствии новых — последние 5 из БД. |
| `/ixbt` | Парсит API-источники из `IXBT_SOURCES`. Сохраняет новые записи, скачивает обложки. Требует `IXBT_SOURCES` в `.env`. Fallback — последние 5 из БД. |
| `/drom` | Парсит `https://news.drom.ru/honda/`. Аналогично `/ixbt`. |
| `/motor` | Парсит API-источники из `MOTOR_HONDA_SOURCE` и `MOTOR_ACURA_SOURCE`. Сохраняет новые записи, скачивает обложки из `included.image.versions.*.rel_url`. Fallback — последние 5 из БД. |
| `/list drom` / `/list ixbt` / `/list motor` | Таблица всех публикаций по источнику: **ID**, **дата/время**, **заголовок (ссылка)**. Новые сверху. Длинные ответы разбиваются (~4000 символов). |
| `/processing IX_HON_1, IX_AC_2` | По ID скачивает страницы, извлекает текст (trafilatura), сохраняет в `full_text`, ставит `status = text_fetched`. |
| `/images IX_HON_1, IX_AC_2` | Обрабатывает сохранённые обложки по ID. Без аргументов — просит указать ID. Также принимает `F.photo` и `F.document` (image/*) для произвольных фото. |
| `/text` | Формирует экспорт-пакет по ID: `news/ДД.ММ.ГГГГ/<ID>/` с обработанным изображением и файлом `source.md`. Если ID не переданы — команда ждёт следующее сообщение с ID. |
| `/rewrite IX_HON_1, DR_HON_1` | Запускает рерайт исходного текста по ID через TEXT.ru API, ждёт результат и сохраняет `news.md` в папку новости (`news/ДД.ММ.ГГГГ/<ID>/news.md`). Если ID не переданы — команда ждёт следующее сообщение с ID. |

Статусы публикаций в ответах: 🆕 `new`, ✅ `text_fetched`.

## Идентификаторы публикаций

ID — **строка** (`TEXT PRIMARY KEY`), отдельная нумерация для каждого источника:

| Источник | Префикс | Примеры |
|----------|---------|---------|
| iXBT Honda (`search=HONDA`) | `IX_HON` | `IX_HON_1`, `IX_HON_2` |
| iXBT Acura (`search=ACURA`) | `IX_AC` | `IX_AC_1`, `IX_AC_77` |
| Drom.ru Honda | `DR_HON` | `DR_HON_1` |
| Motor.ru Honda (`query=Honda`) | `MT_HON` | `MT_HON_1`, `MT_HON_4` |
| Motor.ru Acura (`query=Acura`) | `MT_AC` | `MT_AC_1`, `MT_AC_9` |
| Прочие | `GEN` | `GEN_1` |

Логика в `services/publication_id.py`:

- `get_source_id_prefix(source)` — префикс по URL источника
- `next_publication_id(prefix, existing_ids)` — следующий свободный номер
- `parse_publication_ids(text)` — извлечение ID из аргументов команд (`/processing`, `/images`)

Обложки сохраняются в поддиректории с именем ID:

```
images/09.07.2026/IX_HON_1/honda-nachala-prodazhi-svoego-pervogo-elektromototsikla.jpg
images/09.07.2026/IX_AC_2/acura-predstavila-obnovlennuyu-model.webp
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
| `cover_path` | TEXT | Относительный путь к обложке (`images/09.07.2026/IX_HON_1/honda-nachala-prodazhi....jpg`) |
| `created_at` | TIMESTAMP | Время добавления в БД |

Сортировка по дате публикации: `ORDER BY (published_at IS NULL), published_at DESC, created_at DESC`.

Ключевые функции в `database/db.py`:

- `init_db()` — создание таблицы, миграции колонок и ID
- `save_publication()` — возвращает строковый `id` новой записи или `None`, если URL уже есть
- `check_url_exists()` — проверка перед парсингом
- `get_publications_by_ids()`, `update_publication_text()`, `update_publication_cover_path()`
- `get_latest_publications()`, `get_publications_by_source()`, `get_publications_by_sources()`

## Парсинг новостей (`services/news_parser.py`)

### `/news` — сводный поток

Команда `/news` выполняет источники последовательно:

1. `parse_ixbt_sources()` (источники из `IXBT_SOURCES`)
2. `parse_drom_honda()` для каждого URL из `DROM_SOURCES`
3. `parse_motor_sources()` (источники `MOTOR_HONDA_SOURCE` + `MOTOR_ACURA_SOURCE`)

После этого:

- дедупликация по URL в рамках запуска
- сохранение в БД через `save_publication(...)`
- сохранение обложки через `cover_storage` (если `cover_url` есть)

`parse_new_sources()` — legacy-агрегатор на базе `DROM_SOURCES`, сохранён для обратной совместимости/расширений.

`parse_new_sources()` читает `DROM_SOURCES` (через запятую) и выбирает парсер по URL:

| Условие | Парсер |
|---------|--------|
| URL содержит `rss`, `feed`, `xml`, `atom` | `parse_rss_feed()` — feedparser |
| Домен `drom.ru` | `parse_drom_honda()` — карточки `.b-info-block_like-text` на `news.drom.ru/honda/` |
| Домен `ixbt.com` | `parse_ixbt_car()` — ссылки с `/car/` (legacy HTML-парсер) |
| Домен `motor.ru` | `parse_motor_search()` — legacy HTML-поиск `/news/`, `/articles/`, `/test-drives/` |
| Остальное | `parse_generic_html()` — `<article>` или классы news/article/post |

### `/drom` — `parse_drom_honda()`

Парсит HTML-страницу [news.drom.ru/honda/](https://news.drom.ru/honda/):

- Карточки: `.b-info-block.b-info-block_like-text a.b-info-block__cont[href]`
- Заголовок: `.b-info-block__title`
- Дата: `.b-info-block__text_type_news-date` (ДД.ММ.ГГГГ → ISO в `published_at`)
- Обложка: `img` внутри карточки → `images/DR_HON_N/`
- RSS `drom.ru/export/xml/news.rss` — общий фид (cp1251, без фильтра Honda), не используется

### `/ixbt` — `parse_ixbt_sources()`

Парсит API iXBT (`/api/publications/search` или аналог из `IXBT_SOURCES`):

- Пагинация до `MAX_NEWS_PER_SOURCE` записей на источник (макс. 30 страниц)
- Фильтр по бренду: заголовок, подзаголовок, теги (`HONDA` / `ACURA`, границы слов — исключает ложные срабатывания вроде «Lada Aura»)
- `source` в БД — нормализованный API URL с `page=1` (`_ixbt_source_key()`)
- `published_at` — ISO `pubdatetime` из ответа API (не `formated_pubdatetime`)
- `cover_url` — скачивается в `handlers/ixbt.py` через `cover_storage`

### `/motor` — `parse_motor_sources()`

Парсит API Motor.ru (`/api/bebop/v2/search`) из `MOTOR_HONDA_SOURCE` и `MOTOR_ACURA_SOURCE`:

- Пагинация через `offset` + `limit` до `MAX_NEWS_PER_SOURCE` записей на источник
- Фильтр по бренду (`query=Honda` / `query=Acura`) в `headline`, `announce`, `slug`
- `source` в БД — нормализованный API URL с `offset=0` (`_motor_source_key()`)
- `published_at` — ISO `attributes.published_at`
- `cover_url` — из `included[type=image].attributes.versions.*.rel_url` + префикс `https://motor.ru`
- Приоритет версий изображения: `list_large` → `list_3/2` → `list_16/9` → `main` → `thumbnail`

Команды `/ixbt`, `/drom` и `/motor` вызывают специализированные парсеры напрямую, не через `DROM_SOURCES`.

Лимит на источник: `MAX_NEWS_PER_SOURCE` (по умолчанию 5). Парсинг источников — параллельно через `asyncio.gather`.

## Даты публикаций

`services/datetime_utils.py`:

- В БД хранится ISO `pubdatetime` (`2026-07-05T17:03:00+03:00`)
- Отображение: `ДД.ММ.ГГГГ чч:мм` (`05.07.2026 17:03`)
- `format_publication_datetime()` — для вывода в `/list`, `/ixbt`, `/drom`, `/motor`
- `publication_sort_key()` — сортировка по `published_at`, затем `created_at`

## Извлечение текста

`services/text_extractor.py`: HTTP GET → `trafilatura.extract()` с `favor_precision=True`. При пустом результате — `ValueError`.

Fallback для `motor.ru`:

- если страница возвращает auth-controller и `trafilatura` не извлекает текст,
- основной fallback: `https://motor.ru/api/bebop/v2/topics/<encoded-link>?include=all`
  - полный текст берётся из `included[type=content].attributes.widgets[].attributes.body`
  - служебный блок `**Читайте также**` отрезается
- резервный fallback: `headline + announce` из постраничного `topics` по точному совпадению `attributes.link`.

Fallback для `ixbt.com`:

- если `trafilatura` вернул служебный текст (например, «Перейти к содержимому») или пусто,
- основной fallback: встроенный JSON `{"component":"Publication"}` → `props.publication.blocks[*].html` (полный текст статьи),
- дополнительный fallback: `NewsArticle` JSON-LD (`headline + description`), если блоки не найдены.

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

Обложки iXBT/Motor/Drom (`cover_storage.py`): скачивание по `cover_url` → `images/ДД.ММ.ГГГГ/<pub_id>/<seo-alias>.<ext>`, где `seo-alias` формируется из заголовка (латиница, дефисы, укороченная длина).

Команда `/images` (обработка сохранённых обложек по ID):

- читает оригинал из папки публикации (`images/ДД.ММ.ГГГГ/<pub_id>/...`)
- создаёт подпапку `res` рядом с оригиналом
- сохраняет результат как JPG с тем же базовым именем файла:
  - `images/ДД.ММ.ГГГГ/<pub_id>/res/<seo-alias>.jpg`
- добавляет watermark из `watermark.png` в правый нижний угол
  - отступы: 20px от правого и нижнего края
- режим без аргументов (`/images`):
  - автоматически обрабатывает все обложки из папки текущей даты `images/ДД.ММ.ГГГГ/`
  - если для публикации уже существует подпапка `res`, эта публикация пропускается

## Конфигурация

- **`.env`** — секреты и runtime:
  - `BOT_TOKEN` — токен Telegram-бота
  - `DROM_SOURCES` — источники для `/news` (через запятую)
  - `IXBT_SOURCES` — API URL для `/ixbt` и `/list ixbt` (через запятую)
  - `MOTOR_HONDA_SOURCE` — API URL для `/motor` и `/list motor` (Honda)
  - `MOTOR_ACURA_SOURCE` — API URL для `/motor` и `/list motor` (Acura)
  - `TEXT_API_KEY` — ключ авторизации для API рерайта TEXT.ru (команда `/rewrite`)
  - `MAX_NEWS_PER_SOURCE` — лимит новостей с одного источника (по умолчанию 5)
- **`config.json`** — только параметры изображений (не секреты)
- **`config.py`** — `settings`, `drom_sources_list`, `ixbt_sources_list`, `motor_sources_list`, `image_config`, `max_news_per_source`

Не коммитить: `.env`, `*.db`, `images/**`, `*.log`, `*.pid`, `venv`, `*.sh`.

## Архитектурные соглашения

- Каждая команда — отдельный роутер в `handlers/`, подключается в `bot.py`
- Бизнес-логика парсинга/обработки — в `services/`, не в хендлерах
- HTML-ответы бота: `parse_mode=HTML`, превью ссылок отключено где уместно
- Дедупликация новостей — только по `url` в БД
- Отладочный вывод парсеров — через `print()` с префиксами `[RSS]`, `[DROM]`, `[IXBT-API]`, `[MOTOR-API]`, `[IXBT-CAR]` и т.д.
- Импорт `services.publication_id` в `database/db.py` — ленивый (внутри функций), чтобы избежать циклического импорта

## Расширение проекта

**Новый источник новостей:**

1. Добавить URL в `DROM_SOURCES` (для `/news`) или создать хендлер по образцу `ixbt.py`/`drom.py`
2. При нестандартной вёрстке — новая функция в `news_parser.py` и ветка в `parse_new_sources()`
3. Для `/list` — расширить `SOURCE_MAPPING` в `handlers/list.py`
4. Для строковых ID — добавить префикс в `get_source_id_prefix()` в `publication_id.py`
5. **Обновить `AGENTS.md`**

**Новая команда:**

1. Создать `handlers/<name>.py` с `router = Router()`
2. Экспортировать в `handlers/__init__.py`
3. Подключить в `bot.py` и добавить в `set_bot_commands()`
4. **Обновить `AGENTS.md`**

**Команда `/text`:**

- принимает ID в команде (`/text IX_HON_1, MT_HON_3`) или ждёт следующее сообщение с ID
- получает полный текст публикации:
  - **всегда** заново извлекает по URL (`extract_text_from_url`) и обновляет БД (`status = text_fetched`)
  - не использует ранее сохранённый `full_text` из БД (актуально для IXBT, Drom, Motor)
- создаёт структуру экспорта:
  - `news/ДД.ММ.ГГГГ/<ID>/`
  - копирует обработанное изображение из `images/.../<ID>/res/*.jpg`
  - создаёт `source.md` с исходным текстом статьи
- отправляет отчёт в Telegram (успехи/ошибки/не найденные ID)

**Команда `/rewrite`:**

- принимает ID в команде (`/rewrite IX_HON_1, MT_HON_3`) или ждёт следующее сообщение с ID
- берёт исходный текст публикации:
  - если `full_text` уже есть в БД — использует его
  - если текста нет — извлекает по URL (`extract_text_from_url`) и сохраняет в БД
- отправляет текст в TEXT.ru API (`services/rewrite_service.py`):
  - перед запуском рерайта проверяет баланс через `GET https://api.text.ru/neurotools/api/v1/balance` с заголовком `X-USERKEY` (берётся из `TEXT_API_KEY`)
  - создаёт задачу рерайта
  - опрашивает статус задачи до готового результата
- сохраняет результат в `news.md` в директории новости `news/ДД.ММ.ГГГГ/<ID>/`
  - файл содержит только готовый рерайт (без заголовка/URL/исходного текста)
- отправляет отчёт в Telegram (успехи/ошибки/не найденные ID)

## Ограничения и заметки

- README устарел относительно текущего функционала — ориентироваться на `AGENTS.md`
- `get_publications_by_ids()` не возвращает извлечённый текст пользователю — только обновляет БД и отчёт
- Парсеры зависят от вёрстки/API сайтов; при изменениях стратегии могут перестать находить новости
- Таймаут HTTP-запросов: 15 секунд
- Python 3.10+ (на Linux использовать `python3`, не `python`)
- После смены схемы ID рекомендуется `./reset-db.sh` и повторный парсинг

## Типичный workflow пользователя

1. `/ixbt`, `/drom` или `/motor` — собрать новые публикации, получить ID (`IX_HON_1`, `MT_AC_2`, …)
2. `/list ixbt` или `/list motor` — просмотреть таблицу всех сохранённых
3. `/processing IX_HON_1, IX_AC_2` — извлечь полный текст статей в БД
4. `/images IX_HON_1` — обработать сохранённые обложки (или отправить произвольное фото)
5. `/text IX_HON_1` — собрать экспорт с `source.md` и изображением в `news/.../<ID>/`
6. `/rewrite IX_HON_1` — получить рерайт и сохранить его в `news/.../<ID>/news.md`
