# Newsbot

Telegram-бот на **aiogram 3** для сбора автомобильных новостей (Honda / Acura), извлечения полного текста статей, обработки обложек и подготовки экспортных файлов для публикации. Язык интерфейса и сообщений бота — русский.

## Возможности

- сбор новостей из **iXBT**, **Drom.ru** и **Motor.ru**;
- дедупликация по URL и хранение в SQLite с **строковыми ID** (`IX_HON_1`, `DR_HON_1`, `MT_AC_2`, …);
- автоматическое скачивание и обработка обложек (resize, размытый фон, watermark);
- извлечение полного текста статей с fallback для iXBT и Motor.ru;
- рерайт через **TEXT.ru API** (заголовок из `source.md` добавляется в начало текста и переписывается вместе с ним одним запросом);
- экспорт готовых материалов: `source.md`, `news.md` и обработанное изображение.

## Стек технологий

| Компонент | Библиотека |
|-----------|------------|
| Telegram Bot API | aiogram 3.29 |
| HTTP-клиент | aiohttp |
| База данных | aiosqlite (SQLite) |
| Конфигурация | python-dotenv, pydantic, pydantic-settings |
| RSS | feedparser |
| HTML-парсинг | BeautifulSoup4 + lxml |
| Извлечение текста | trafilatura |
| Обработка изображений | Pillow |

Полный список зависимостей с версиями — в [`requirements.txt`](requirements.txt).

## Требования

- Python **3.10+**
- Токен Telegram-бота (`BOT_TOKEN`)
- API-ключ TEXT.ru (`TEXT_API_KEY`) — для команды `/text`
- Linux/macOS: использовать `python3` (на Windows подойдёт `python`)

## Установка

```bash
python3 -m venv venv
source venv/bin/activate   # Linux/macOS
# venv\Scripts\activate    # Windows
pip install -r requirements.txt
```

## Настройка

### `.env`

Создайте файл `.env` в корне проекта (образец — [`.env.example`](.env.example)):

```env
BOT_TOKEN=your_telegram_bot_token
DROM_SOURCES=https://news.drom.ru/honda/
IXBT_SOURCES=https://api.ixbt.com/v0/publications/search?search=HONDA,https://api.ixbt.com/v0/publications/search?search=ACURA
MOTOR_HONDA_SOURCE=https://motor.ru/api/bebop/v2/search?query=Honda&offset=0&limit=15&include=image,rubric
MOTOR_ACURA_SOURCE=https://motor.ru/api/bebop/v2/search?query=Acura&offset=0&limit=15&include=image,rubric
TEXT_API_KEY=your_text_ru_api_key
MAX_NEWS_PER_SOURCE=5
```

| Переменная | Описание |
|------------|----------|
| `BOT_TOKEN` | Токен Telegram-бота |
| `DROM_SOURCES` | URL источников Drom для `/news` (через запятую) |
| `IXBT_SOURCES` | API URL iXBT для Honda и Acura (через запятую) |
| `MOTOR_HONDA_SOURCE` | API URL Motor.ru для Honda |
| `MOTOR_ACURA_SOURCE` | API URL Motor.ru для Acura |
| `TEXT_API_KEY` | Ключ TEXT.ru (`X-USERKEY`) для рерайта в `/text` |
| `MAX_NEWS_PER_SOURCE` | Лимит новостей с одного источника за запуск (по умолчанию 5) |

### `config.json`

Параметры обработки изображений (не секреты):

```json
{
  "image_processing": {
    "width": 735,
    "height": 454,
    "quality": 85
  }
}
```

Watermark накладывается из файла `watermark.png` (правый нижний угол, отступ 20 px).

## Запуск

```bash
python3 bot.py
```

### Фоновые скрипты (Linux/macOS)

Скрипты в корне проекта, в `.gitignore`:

| Скрипт | Назначение |
|--------|------------|
| `start.sh` | venv + фоновый запуск, PID в `.bot.pid`, лог в `bot.log` |
| `stop.sh` | остановка бота |
| `restart.sh` | stop → sleep → start |
| `reset-db.sh` | удаление `bot_database.db` |

## Команды бота

В меню Telegram подключены две команды:

| Команда | Описание |
|---------|----------|
| `/news` | Сводный сбор: **iXBT → Drom → Motor**. Сохраняет новые публикации, возвращает ID. Для новых записей автоматически обрабатывает обложки. Если новых нет — показывает последние 5 из БД. |
| `/text <ID,...>` | Извлечение текста, рерайт через TEXT.ru, экспорт в `news/ДД.ММ.ГГГГ/<ID>/`. Без аргументов — ждёт следующее сообщение с ID. |

**Примеры:**

```
/news
/text IX_HON_1, MT_HON_3
/text
IX_HON_7, DR_HON_2
```

Статусы публикаций в ответах: 🆕 `new`, ✅ `text_fetched`.

### Внутренние команды (не в меню)

Роутеры есть в коде, но в `bot.py` не подключены:

- `/ixbt`, `/drom`, `/motor` — отдельный парсинг одного источника;
- `/images` — обработка обложек по ID;
- `/list` — список публикаций по источнику;
- `/processing` — только извлечение текста в БД;
- `/rewrite` — legacy-рерайт (заменён командой `/text`).

## Типичный workflow

1. **`/news`** — собрать новые публикации, получить ID (`IX_HON_1`, `MT_AC_2`, …) и автоматически обработанные обложки в `images/`.
2. **`/text IX_HON_1, MT_HON_3`** — извлечь текст, выполнить рерайт заголовка и текста, получить `source.md` + `news.md` в `news/ДД.ММ.ГГГГ/<ID>/`.

## Идентификаторы публикаций

ID — строка, отдельная нумерация для каждого источника:

| Источник | Префикс | Примеры |
|----------|---------|---------|
| iXBT Honda (`search=HONDA`) | `IX_HON` | `IX_HON_1`, `IX_HON_2` |
| iXBT Acura (`search=ACURA`) | `IX_AC` | `IX_AC_1`, `IX_AC_77` |
| Drom.ru Honda | `DR_HON` | `DR_HON_1` |
| Motor.ru Honda (`query=Honda`) | `MT_HON` | `MT_HON_1`, `MT_HON_4` |
| Motor.ru Acura (`query=Acura`) | `MT_AC` | `MT_AC_1`, `MT_AC_9` |
| Прочие | `GEN` | `GEN_1` |

Логика генерации — в `services/publication_id.py`. При старте бота выполняется миграция со старых числовых `INTEGER id` на строковые ID.

## База данных

Файл: `bot_database.db` (не коммитится).

Таблица `publications`:

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | TEXT PK | Строковый ID (`IX_HON_1`, …) |
| `title` | TEXT | Заголовок |
| `url` | TEXT UNIQUE | Дедупликация по URL |
| `source` | TEXT | URL источника |
| `full_text` | TEXT | Извлечённый текст |
| `status` | TEXT | `new` или `text_fetched` |
| `published_at` | TEXT | ISO-дата публикации |
| `cover_path` | TEXT | Путь к обложке (`images/ДД.ММ.ГГГГ/<ID>/...`) |
| `created_at` | TIMESTAMP | Время добавления в БД |

Сортировка: `ORDER BY (published_at IS NULL), published_at DESC, created_at DESC`.

## Источники и парсинг

### `/news` — порядок запуска

1. `parse_ixbt_sources()` — API iXBT из `IXBT_SOURCES`
2. `parse_drom_honda()` — HTML [news.drom.ru/honda/](https://news.drom.ru/honda/) из `DROM_SOURCES`
3. `parse_motor_sources()` — API Motor.ru (`MOTOR_HONDA_SOURCE` + `MOTOR_ACURA_SOURCE`)

После парсинга: дедупликация по URL, сохранение в БД, скачивание обложек, автообработка изображений для новых ID.

### iXBT

- API `/api/publications/search`, пагинация до `MAX_NEWS_PER_SOURCE` на источник
- Фильтр по бренду в заголовке, подзаголовке и тегах (границы слов — исключает ложные срабатывания вроде «Lada Aura»)
- Дата: ISO `pubdatetime` из API

### Drom.ru

- HTML-карточки `.b-info-block_like-text`
- Дата: `ДД.ММ.ГГГГ` → ISO в `published_at`
- Обложка: первая кликабельная картинка со страницы статьи (полноразмерный `href` ссылки), иначе главная (`og:image`), иначе превью из карточки ленты

### Motor.ru

- API `/api/bebop/v2/search`, пагинация через `offset` + `limit`
- Фильтр по `query=Honda` / `query=Acura` в `headline`, `announce`, `slug`
- Обложка из `included[type=image]` (приоритет: `list_large` → `list_3/2` → `list_16/9` → `main` → `thumbnail`)

Лимит на источник: `MAX_NEWS_PER_SOURCE` (по умолчанию 5). Внутри одного источника парсинг идёт параллельно через `asyncio.gather`.

## Извлечение текста

`services/text_extractor.py`: HTTP GET → `trafilatura.extract()` с `favor_precision=True`.

**Fallback Motor.ru:** API `https://motor.ru/api/bebop/v2/topics/<link>?include=all` — текст из `widgets[].attributes.body`, блок «Читайте также» отрезается.

**Fallback iXBT:** встроенный JSON `{"component":"Publication"}` → `props.publication.blocks[*].html`, либо JSON-LD `NewsArticle`.

Команда `/text` **всегда** заново извлекает текст по URL и обновляет БД (`status = text_fetched`), не используя ранее сохранённый `full_text`.

## Обработка изображений

1. **Скачивание** (`cover_storage.py`): `images/ДД.ММ.ГГГГ/<ID>/<seo-alias>.<ext>`
2. **Обработка** (`image_processor.py`): размытый фон + вписанное по центру фото → JPEG в `images/.../<ID>/res/<seo-alias>.jpg` + watermark

Автоматически запускается после `/news` для новых публикаций. Вручную — через `/images` (не в меню).

## Рерайт TEXT.ru

`services/rewrite_service.py` — клиент Neuro Rewriting API.

При `/text` выполняется **один запрос** рерайта:

1. Заголовок из `source.md` (строка `# ...`) добавляется в начало текста статьи
2. Объединённый текст отправляется в TEXT.ru
3. Из результата извлекается переписанный заголовок (первый абзац или первое предложение), остальное — тело статьи

Перед рерайтом проверяется баланс: `GET https://api.text.ru/neurotools/api/v1/balance` (заголовок `X-USERKEY`). Затем создаётся задача и опрашивается статус до готового результата.

## Структура экспорта

После `/text` файлы формируются в:

```text
news/ДД.ММ.ГГГГ/<ID>/
├── source.md          # оригинальный заголовок и исходный текст
├── news.md            # рерайт для публикации
└── <обложка>.jpg      # копия обработанного изображения из images/.../res/
```

### `source.md`

```markdown
# Заголовок публикации

Источник: https://...

---

Текст статьи...
```

### `news.md`

```text
1. Заголовок: <переписанный заголовок из source.md>
2. Картинка: <p><img src="/_upload/content/news/<имя-файла>.jpg" alt="Заголовок" /></p>

<p>Абзац рерайта...</p>
<p>Следующий абзац...</p>
```

Обложки до экспорта хранятся в:

```text
images/ДД.ММ.ГГГГ/<ID>/
├── <seo-alias>.jpg          # оригинал (скачанный)
└── res/
    └── <seo-alias>.jpg      # обработанный (используется в /text)
```

## Структура проекта

```text
bot/
├── bot.py                     # Точка входа, меню команд, polling
├── config.py                  # Настройки из .env
├── config.json                # Параметры обработки изображений
├── requirements.txt           # Зависимости Python
├── watermark.png              # Watermark для обложек
├── handlers/
│   ├── news.py                # /news
│   ├── text.py                # /text — извлечение + рерайт + экспорт
│   ├── ixbt.py                # Внутренний: iXBT (не в меню)
│   ├── drom.py                # Внутренний: Drom (не в меню)
│   ├── motor.py               # Внутренний: Motor (не в меню)
│   ├── images.py              # Обработка обложек
│   ├── list.py                # Внутренний: список (не в меню)
│   ├── processing.py          # Внутренний: извлечение (не в меню)
│   └── rewrite.py             # Legacy /rewrite (не подключён)
├── services/
│   ├── news_parser.py         # Парсеры RSS, HTML, API
│   ├── text_extractor.py      # trafilatura + fallbacks
│   ├── rewrite_service.py     # Клиент TEXT.ru
│   ├── image_processor.py     # Resize, размытый фон, watermark
│   ├── cover_storage.py       # Скачивание обложек
│   ├── publication_id.py      # Строковые ID по источнику
│   └── datetime_utils.py      # Форматирование дат
├── database/
│   └── db.py                  # SQLite: publications
├── images/                    # Обложки (в .gitignore)
└── news/                      # Экспорт материалов (в .gitignore)
```

## Что не коммитить

- `.env` — секреты
- `*.db` — локальная база
- `images/**`, `news/**` — рабочие артефакты
- `*.log`, `*.pid`, `venv/`, `*.sh` — runtime

## Ограничения

- Парсеры зависят от вёрстки и API сайтов-источников
- Таймаут HTTP-запросов: 15 секунд
- Рерайт `/text` списывает баланс TEXT.ru за **один** запрос на публикацию (заголовок + текст)
- После смены схемы ID рекомендуется `reset-db.sh` и повторный парсинг

## Документация для разработчиков

Подробное техническое руководство (архитектура, расширение, соглашения) — в [`AGENTS.md`](AGENTS.md). При изменении функционала обновляйте **оба** файла: `README.md` и `AGENTS.md`.
