from aiogram import Router, types
from aiogram.filters import Command
from services.news_parser import parse_drom_honda
from database.db import save_publication, get_latest_publications

router = Router()

@router.message(Command("drom"))
async def cmd_drom(message: types.Message):
    """Обработчик команды /drom - парсинг новостей Honda на Drom.ru"""
    await message.answer("🚗 Парсю новости Honda на Drom.ru...")
    
    try:
        # ВСЕГДА парсим сайт
        raw_news = await parse_drom_honda("https://news.drom.ru/honda/")
        
        if not raw_news:
            # Если парсер не нашёл ничего, показываем последние из БД
            latest = await get_latest_publications(limit=5, source="https://news.drom.ru/honda/")
            
            if not latest:
                await message.answer(
                    "❌ Не удалось найти новости на сайте.\n"
                    "📭 В базе данных пока нет сохранённых публикаций."
                )
                return
            
            result_text = "📋 <b>Последние сохранённые публикации Drom (Honda):</b>\n\n"
            for pub in latest:
                status_icon = "✅" if pub['status'] == 'text_fetched' else "🆕"
                result_text += f"{status_icon} [<b>ID: {pub['id']}</b>] {pub['title']}\n🔗 {pub['url']}\n\n"
            
            await message.answer(
                result_text,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            return
        
        result_text = "🚙 <b>Новости Honda на Drom.ru:</b>\n\n"
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
        await message.answer(f"❌ Ошибка при парсинге Drom: {str(e)}")