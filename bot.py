import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand, BotCommandScopeDefault
from config import settings
from database.db import init_db
from handlers import (
    news_router, 
    processing_router, 
    images_router, 
    text_router, 
    ixbt_router,
    drom_router,
    motor_router,
    list_router,
    rewrite_router,
)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def set_bot_commands(bot: Bot):
    """Устанавливает меню команд бота"""
    commands = [
        BotCommand(command="news", description="📰 Получить новые публикации"),
        BotCommand(command="ixbt", description="🚗 Новости Honda/Acura iXBT"),
        BotCommand(command="drom", description="🚙 Новости Honda на Drom.ru"),
        BotCommand(command="motor", description="🏎 Новости Honda/Acura Motor.ru"),
        BotCommand(command="list", description="📋 Список всех публикаций (drom/ixbt/motor)"),
        BotCommand(command="processing", description="⚙️ Извлечь текст публикаций (ID)"),
        BotCommand(command="images", description="🖼 Обработать обложки (ID) или фото"),
        BotCommand(command="text", description="📝 Экспорт исходного текста (ID)"),
        BotCommand(command="rewrite", description="✍️ Рерайт текста через TEXT.ru (ID)"),
    ]
    
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
    logger.info("Меню команд установлено")

async def main():
    """Главная функция запуска бота"""
    # Инициализация базы данных
    await init_db()
    logger.info("База данных инициализирована")
    
    # Создание бота и диспетчера
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    # Устанавливаем меню команд
    await set_bot_commands(bot)
    
    dp = Dispatcher()
    
    # Подключаем роутеры
    dp.include_router(news_router)
    dp.include_router(ixbt_router)
    dp.include_router(drom_router)
    dp.include_router(motor_router)
    dp.include_router(list_router)  # НОВЫЙ РОУТЕР
    dp.include_router(processing_router)
    dp.include_router(images_router)
    dp.include_router(text_router)
    dp.include_router(rewrite_router)
    
    logger.info("Бот запущен")
    
    # Запуск polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")