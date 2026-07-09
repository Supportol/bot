# Newsbot

Telegram-бот на `aiogram 3` для сбора автомобильных новостей (Honda/Acura), извлечения текста статей, обработки обложек и подготовки экспортных файлов.

## Что умеет бот

- собирает новости из iXBT, Drom и Motor.ru;
- сохраняет публикации в SQLite с строковыми ID (`IX_HON_1`, `DR_HON_1`, `MT_HON_1`, ...);
- извлекает полный текст статей и делает рерайт в рамках `/text`;
- обрабатывает обложки автоматически после `/news`;
- формирует экспорт `source.md` + `news.md` и копирует обработанное изображение.

## Команды

- `/news` — агрегированный запуск: `iXBT → Drom → Motor` + автообработка новых обложек;
- `/text <ID,...>` — единая команда: извлечь текст, обновить БД, создать `source.md`, сделать рерайт через TEXT.ru и сохранить `news.md`.

## Требования

- Python `3.10+`;
- Linux/macOS: использовать `python3` (не `python`).

## Установка

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Настройки `.env`

Создайте файл `.env` в корне:

```env
BOT_TOKEN=your_telegram_bot_token
DROM_SOURCES=https://news.drom.ru/honda/
IXBT_SOURCES=https://api.ixbt.com/v0/publications/search?search=HONDA,https://api.ixbt.com/v0/publications/search?search=ACURA
MOTOR_HONDA_SOURCE=https://motor.ru/api/bebop/v2/search?query=Honda&offset=0&limit=15&include=image,rubric
MOTOR_ACURA_SOURCE=https://motor.ru/api/bebop/v2/search?query=Acura&offset=0&limit=15&include=image,rubric
TEXT_API_KEY=your_text_ru_api_key
MAX_NEWS_PER_SOURCE=5
```

## Запуск

```bash
python3 bot.py
```

## Вспомогательные скрипты

- `start.sh` — запустить бота в фоне;
- `stop.sh` — остановить бота;
- `restart.sh` — перезапуск;
- `reset-db.sh` — удалить `bot_database.db`.

## Структура экспорта

После `/text` файлы формируются в:

```text
news/ДД.ММ.ГГГГ/<ID>/
```

- `source.md` — исходный текст статьи;
- `news.md` — итоговый рерайт для публикации;
- `*.jpg` — обработанная обложка.

Формат `news.md`: только рерайт, каждый абзац обёрнут в `<p>...</p>`.

## Важно

- секреты (`.env`) и локальная БД (`*.db`) не коммитятся;
- директории `images/` и `news/` считаются рабочими артефактами;
- при изменении команд/архитектуры обновляйте `AGENTS.md` и `README.md` вместе.
