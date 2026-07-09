import html
from aiogram import Router, types
from aiogram.filters import Command
from database.db import get_publications_by_source, get_publications_by_sources
from config import ixbt_sources_list
from services.datetime_utils import format_publication_datetime, publication_sort_key

router = Router()

SOURCE_MAPPING = {
    "drom": ["https://news.drom.ru/honda/"],
    "ixbt": ixbt_sources_list,
}

SOURCE_NAMES = {
    "drom": "🚙 Drom.ru (Honda)",
    "ixbt": "🚗 iXBT (Honda/Acura)",
}

MAX_TITLE_LENGTH = 70
MESSAGE_LIMIT = 4000

def _format_datetime(pub: dict) -> str:
    return format_publication_datetime(pub.get("published_at"))

def _sort_publications(publications: list[dict]) -> list[dict]:
    """Новые публикации сверху."""
    return sorted(publications, key=publication_sort_key, reverse=True)

def _build_table_header(id_width: int, date_width: int) -> str:
    header = (
        f"{'ID':>{id_width}} | {'Дата/время':<{date_width}} | Заголовок\n"
        f"{'-' * id_width}-+-{'-' * date_width}-+{'-' * 11}"
    )
    return f"<pre>{html.escape(header)}</pre>\n"

def _build_table_row(pub: dict, id_width: int, date_width: int) -> str:
    title = html.escape(pub["title"])
    if len(title) > MAX_TITLE_LENGTH:
        title = title[: MAX_TITLE_LENGTH - 3] + "..."

    pid = html.escape(str(pub["id"]))
    date = html.escape(_format_datetime(pub))
    url = html.escape(pub["url"], quote=True)

    return (
        f"<code>{pid:>{id_width}}</code> | "
        f"<code>{date:<{date_width}}</code> | "
        f'<a href="{url}">{title}</a>\n'
    )

def _split_table_messages(publications: list[dict], header_text: str, source_name: str) -> list[str]:
    if not publications:
        return []

    id_width = max(len(str(pub["id"])) for pub in publications)
    id_width = max(id_width, 2)
    date_width = max(len(_format_datetime(pub)) for pub in publications)
    date_width = max(date_width, len("Дата/время"))

    table_header = _build_table_header(id_width, date_width)
    messages = []
    current = header_text + table_header

    for pub in publications:
        row = _build_table_row(pub, id_width, date_width)
        if len(current) + len(row) > MESSAGE_LIMIT:
            messages.append(current.rstrip())
            current = f"📋 <b>Продолжение: {source_name}</b>\n\n" + table_header + row
        else:
            current += row

    if current.strip():
        messages.append(current.rstrip())

    return messages

@router.message(Command("list"))
async def cmd_list(message: types.Message):
    """Обработчик команды /list - просмотр всех публикаций из БД по источнику"""
    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        await message.answer(
            "⚠️ Укажите источник. Примеры:\n"
            "• <code>/list drom</code> - все новости Honda с Drom.ru\n"
            "• <code>/list ixbt</code> - все новости Honda/Acura с iXBT",
            parse_mode="HTML",
        )
        return

    source_key = args[1].strip().lower()

    if source_key not in SOURCE_MAPPING:
        await message.answer(
            f"⚠️ Неизвестный источник: <b>{source_key}</b>\n\n"
            "Доступные источники:\n"
            "• <code>drom</code> - Drom.ru (Honda)\n"
            "• <code>ixbt</code> - iXBT (Honda/Acura)",
            parse_mode="HTML",
        )
        return

    source_urls = SOURCE_MAPPING[source_key]

    if source_key == "ixbt" and not source_urls:
        await message.answer(
            "⚠️ Не настроены источники iXBT.\n"
            "Добавьте <code>IXBT_SOURCES</code> в файл <code>.env</code>.",
            parse_mode="HTML",
        )
        return

    if len(source_urls) == 1:
        publications = await get_publications_by_source(source_urls[0])
    else:
        publications = await get_publications_by_sources(source_urls)

    if not publications:
        await message.answer(
            f"📭 В базе данных нет публикаций из источника <b>{SOURCE_NAMES[source_key].split(' ', 1)[1]}</b>.\n\n"
            f"Используйте команду <code>/{source_key}</code>, чтобы спарсить новости.",
            parse_mode="HTML",
        )
        return

    publications = _sort_publications(publications)
    source_name = SOURCE_NAMES[source_key]

    header_text = (
        f"📋 <b>Все публикации: {source_name}</b>\n"
        f"📊 Всего: {len(publications)}\n\n"
    )

    messages = _split_table_messages(publications, header_text, source_name)

    for msg in messages:
        await message.answer(msg, parse_mode="HTML", disable_web_page_preview=True)
