from aiogram import Router, types
from aiogram.filters import Command
from services.news_parser import parse_new_sources
from database.db import save_publication, get_latest_publications

router = Router()

@router.message(Command("news"))
async def cmd_news(message: types.Message):
    """Обработчик команды /news"""
    await message.answer("⏳ Ищу новые публикации...")
    
    try:
        # ВСЕГДА парсим источники
        raw_news = await parse_new_sources()
        
        if not raw_news:
            # Если парсер не нашёл ничего, показываем последние из БД
            latest = await get_latest_publications(limit=5)
            
            if not latest:
                await message.answer(
                    "❌ Не удалось найти новые публикации.\n"
                    "📭 В базе данных пока нет сохранённых публикаций."
                )
                return
            
            result_text = "📋 <b>Последние сохранённые публикации:</b>\n\n"
            for pub in latest:
                status_icon = "✅" if pub['status'] == 'text_fetched' else "🆕"
                result_text += f"{status_icon} [<b>ID: {pub['id']}</b>] {pub['title']}\n🔗 {pub['url']}\n\n"
            
            await message.answer(
                result_text,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            return
        
        # Сохраняем в БД и формируем ответ
        result_text = "🆕 <b>Новые публикации:</b>\n\n"
        new_count = 0
        
        for item in raw_news:
            pub_id = await save_publication(item['title'], item['url'], item['source'])
            if pub_id:  # Только если это новая запись
                result_text += f"[<b>ID: {pub_id}</b>] {item['title']}\n🔗 {item['url']}\n\n"
                new_count += 1
        
        if new_count == 0:
            await message.answer("✅ Все новости уже в базе данных. Новых нет.")
            return
        
        await message.answer(
            result_text, 
            parse_mode="HTML", 
            disable_web_page_preview=True
        )
        
    except Exception as e:
        await message.answer(f"❌ Ошибка при поиске новостей: {str(e)}")