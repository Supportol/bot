from aiogram import Router, types
from aiogram.filters import Command

from database.db import get_latest_publications, save_publication, update_publication_cover_path
from handlers.images import process_publication_covers
from services.news_parser import parse_drom_honda
from services.cover_storage import save_publication_cover
from services.datetime_utils import format_publication_datetime

router = Router()

DROM_SOURCE = "https://news.drom.ru/honda/"

def _format_publication_line(pub: dict) -> str:
    line = f"[<b>ID: {pub['id']}</b>] {pub['title']}\n"
    date = format_publication_datetime(pub.get("published_at"))
    if date != "—":
        line += f"🕐 {date}\n"
    line += f"🔗 {pub['url']}\n\n"
    return line

@router.message(Command("drom"))
async def cmd_drom(message: types.Message):
    """Обработчик команды /drom - парсинг новостей Honda на Drom.ru"""
    await message.answer("🚗 Парсю новости Honda на Drom.ru...")

    try:
        raw_news = await parse_drom_honda(DROM_SOURCE)

        if not raw_news:
            latest = await get_latest_publications(limit=5, source=DROM_SOURCE)

            if not latest:
                await message.answer(
                    "❌ Не удалось найти новости на сайте.\n"
                    "📭 В базе данных пока нет сохранённых публикаций."
                )
                return

            result_text = "📋 <b>Последние сохранённые публикации Drom (Honda):</b>\n\n"
            for pub in latest:
                status_icon = "✅" if pub["status"] == "text_fetched" else "🆕"
                result_text += f"{status_icon} {_format_publication_line(pub)}"

            await message.answer(
                result_text,
                parse_mode="HTML",
                disable_web_page_preview=True,
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
                cover_path = await save_publication_cover(pub_id, item["title"], item["cover_url"])
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

        result_text = f"🚙 <b>Новые Honda на Drom.ru ({len(new_publications)} шт.):</b>\n\n"

        for pub in new_publications:
            result_text += _format_publication_line(pub)

        processed_count, image_errors = await process_publication_covers(new_publications)
        result_text += f"🖼 Автообработка обложек: {processed_count}/{len(new_publications)}\n"
        if image_errors:
            result_text += f"⚠️ Ошибок обработки: {len(image_errors)}\n"

        await message.answer(
            result_text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )

    except Exception as e:
        await message.answer(f"❌ Ошибка при парсинге Drom: {str(e)}")
