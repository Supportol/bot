from aiogram import Router, types
from aiogram.filters import Command

from config import drom_sources_list
from database.db import get_latest_publications, save_publication, update_publication_cover_path
from handlers.images import process_publication_covers
from handlers.telegram_messages import answer_long_blocks
from services.cover_storage import save_publication_cover
from services.datetime_utils import format_publication_datetime
from services.news_parser import parse_drom_honda, parse_ixbt_sources, parse_motor_sources

router = Router()


def _format_publication_line(pub: dict) -> str:
    line = f"[<b>ID: {pub['id']}</b>] {pub['title']}\n"
    date = format_publication_datetime(pub.get("published_at"))
    if date != "—":
        line += f"🕐 {date}\n"
    line += f"🔗 {pub['url']}\n\n"
    return line


@router.message(Command("news"))
async def cmd_news(message: types.Message):
    """Сводная команда: последовательно парсит IXBT -> DROM -> MOTOR."""
    await message.answer("⏳ Запускаю сводный сбор новостей: iXBT → Drom → Motor...")

    try:
        raw_news = []
        seen_urls = set()

        ixbt_items = await parse_ixbt_sources()
        for item in ixbt_items:
            if item["url"] in seen_urls:
                continue
            seen_urls.add(item["url"])
            raw_news.append(item)

        for source_url in drom_sources_list:
            drom_items = await parse_drom_honda(source_url)
            for item in drom_items:
                if item["url"] in seen_urls:
                    continue
                seen_urls.add(item["url"])
                raw_news.append(item)

        motor_items = await parse_motor_sources()
        for item in motor_items:
            if item["url"] in seen_urls:
                continue
            seen_urls.add(item["url"])
            raw_news.append(item)

        if not raw_news:
            latest = await get_latest_publications(limit=5)
            if not latest:
                await message.answer(
                    "❌ Не удалось найти новые публикации.\n"
                    "📭 В базе данных пока нет сохранённых публикаций."
                )
                return

            blocks = []
            for pub in latest:
                status_icon = "✅" if pub["status"] == "text_fetched" else "🆕"
                blocks.append(f"{status_icon} {_format_publication_line(pub)}")

            await answer_long_blocks(
                message,
                blocks,
                "📋 <b>Последние сохранённые публикации:</b>\n\n",
                continuation_header="📋 <b>Продолжение списка публикаций:</b>\n\n",
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

            new_publications.append(
                {
                    "id": pub_id,
                    "title": item["title"],
                    "url": item["url"],
                    "published_at": item.get("published_at"),
                    "cover_path": cover_path,
                }
            )

        if not new_publications:
            await message.answer("✅ Все новости уже в базе данных. Новых нет.")
            return

        blocks = [_format_publication_line(pub) for pub in new_publications]

        processed_count, image_errors = await process_publication_covers(new_publications)
        footer = f"🖼 Автообработка обложек: {processed_count}/{len(new_publications)}\n"
        if image_errors:
            footer += f"⚠️ Ошибок обработки: {len(image_errors)}\n"

        await answer_long_blocks(
            message,
            blocks,
            f"🆕 <b>Новые публикации ({len(new_publications)} шт.):</b>\n\n",
            continuation_header="🆕 <b>Продолжение списка публикаций:</b>\n\n",
            footer=footer,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )

    except Exception as e:
        await message.answer(f"❌ Ошибка при поиске новостей: {str(e)}")
