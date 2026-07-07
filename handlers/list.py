from aiogram import Router, types
from aiogram.filters import Command
from database.db import get_publications_by_source

router = Router()

# Маппинг аргументов к реальным URL источников
SOURCE_MAPPING = {
    "drom": "https://news.drom.ru/honda/",
    "ixbt": "https://www.ixbt.com/car/",
}

@router.message(Command("list"))
async def cmd_list(message: types.Message):
    """Обработчик команды /list - просмотр всех публикаций из БД по источнику"""
    # Получаем аргумент команды
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer(
            "⚠️ Укажите источник. Примеры:\n"
            "• <code>/list drom</code> - все новости Honda с Drom.ru\n"
            "• <code>/list ixbt</code> - все новости с iXBT Car",
            parse_mode="HTML"
        )
        return
    
    source_key = args[1].strip().lower()
    
    # Проверяем, что источник известен
    if source_key not in SOURCE_MAPPING:
        await message.answer(
            f"⚠️ Неизвестный источник: <b>{source_key}</b>\n\n"
            "Доступные источники:\n"
            "• <code>drom</code> - Drom.ru (Honda)\n"
            "• <code>ixbt</code> - iXBT (Автомобили)",
            parse_mode="HTML"
        )
        return
    
    source_url = SOURCE_MAPPING[source_key]
    
    # Получаем все публикации из БД
    publications = await get_publications_by_source(source_url)
    
    if not publications:
        source_names = {
            "drom": "Drom.ru (Honda)",
            "ixbt": "iXBT (Автомобили)"
        }
        await message.answer(
            f"📭 В базе данных нет публикаций из источника <b>{source_names[source_key]}</b>.\n\n"
            f"Используйте команду <code>/{source_key}</code>, чтобы спарсить новости.",
            parse_mode="HTML"
        )
        return
    
    # Формируем ответ
    source_names = {
        "drom": "🚙 Drom.ru (Honda)",
        "ixbt": "🚗 iXBT (Автомобили)"
    }
    
    result_text = f"📋 <b>Все публикации: {source_names[source_key]}</b>\n"
    result_text += f"📊 Всего: {len(publications)}\n\n"
    
    # Разбиваем на части, так как Telegram ограничивает длину сообщения
    messages = []
    current_message = result_text
    
    for pub in publications:
        status_icon = "✅" if pub['status'] == 'text_fetched' else "🆕"
        item_text = f"{status_icon} [<b>ID: {pub['id']}</b>] {pub['title']}\n🔗 {pub['url']}\n\n"
        
        # Проверяем, не превысит ли сообщение лимит Telegram (4096 символов)
        if len(current_message + item_text) > 4000:
            messages.append(current_message)
            current_message = f"📋 <b>Продолжение: {source_names[source_key]}</b>\n\n"
        
        current_message += item_text
    
    if current_message.strip() != result_text.strip():
        messages.append(current_message)
    
    # Отправляем все части
    for msg in messages:
        await message.answer(
            msg,
            parse_mode="HTML",
            disable_web_page_preview=True
        )