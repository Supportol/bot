from aiogram import Router, types
from aiogram.filters import Command
from services.news_parser import parse_ixbt_sources
from services.cover_storage import save_publication_cover
from services.datetime_utils import format_publication_datetime
from database.db import (
    save_publication,
    update_publication_cover_path,
    get_latest_publications_by_sources,
)
from config import ixbt_sources_list

router = Router()

def _format_publication_line(pub: dict) -> str:
    line = f"[<b>ID: {pub['id']}</b>] {pub['title']}\n"
    date = format_publication_datetime(pub.get("published_at"))
    if date != "—":
        line += f"🕐 {date}\n"
    line += f"🔗 {pub['url']}\n\n"
    return line

@router.message(Command("ixbt"))
async def cmd_ixbt(message: types.Message):
    """Обработчик команды /ixbt - парсинг новостей Honda/Acura с iXBT"""
    if not ixbt_sources_list:
        await message.answer(
            "⚠️ Не настроены источники iXBT.\n"
            "Добавьте <code>IXBT_SOURCES</code> в файл <code>.env</code>.",
            parse_mode="HTML",
        )
        return

    await message.answer("⏳ Парсю новости Honda/Acura на iXBT...")

    try:
        raw_news = await parse_ixbt_sources()

        if not raw_news:
            latest = await get_latest_publications_by_sources(ixbt_sources_list, limit=5)

            if not latest:
                await message.answer(
                    "❌ Не удалось найти новости на сайте.\n"
                    "📭 В базе данных пока нет сохранённых публикаций."
                )
                return

            result_text = "📋 <b>Последние сохранённые публикации (сайт недоступен):</b>\n\n"
            for pub in latest:
                status_icon = "✅" if pub['status'] == 'text_fetched' else "🆕"
                result_text += f"{status_icon} {_format_publication_line(pub)}"

            await message.answer(
                result_text,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            return

        new_publications = []

        for item in raw_news:
            pub_id = await save_publication(
                item["title"],
                item["url"],
                item["source"],
                published_at=item.get("published_at"),
            )
            if not pub_id:
                continue

            cover_path = None
            if item.get("cover_url"):
                cover_path = await save_publication_cover(pub_id, item["cover_url"])
                if cover_path:
                    await update_publication_cover_path(pub_id, cover_path)

            new_publications.append({
                "id": pub_id,
                "title": item["title"],
                "url": item["url"],
                "published_at": item.get("published_at"),
                "cover_path": cover_path,
            })

        if not new_publications:
            await message.answer("✅ Все найденные новости уже в базе данных. Новых публикаций нет.")
            return

        result_text = f"🚗 <b>Новые новости Honda/Acura на iXBT ({len(new_publications)} шт.):</b>\n\n"

        for pub in new_publications:
            result_text += _format_publication_line(pub)

        await message.answer(
            result_text,
            parse_mode="HTML",
            disable_web_page_preview=True
        )

    except Exception as e:
        await message.answer(f"❌ Ошибка при парсинге iXBT: {str(e)}")
