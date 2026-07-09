import os
from pathlib import Path
from dotenv import load_dotenv
import json
from pydantic import field_validator
from pydantic_settings import BaseSettings
from typing import List

# Загрузка .env
load_dotenv()

class Settings(BaseSettings):
    bot_token: str
    news_sources: str
    ixbt_sources: str = ""
    max_news_per_source: int = 5  # Значение по умолчанию
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

def get_settings() -> Settings:
    return Settings(
        bot_token=os.getenv("BOT_TOKEN"),
        news_sources=os.getenv("NEWS_SOURCES", ""),
        ixbt_sources=os.getenv("IXBT_SOURCES", ""),
        max_news_per_source=int(os.getenv("MAX_NEWS_PER_SOURCE", "5"))
    )

def get_news_sources_list() -> List[str]:
    """Получает список источников новостей"""
    raw = os.getenv("NEWS_SOURCES", "")
    return [source.strip() for source in raw.split(',') if source.strip()]

def get_ixbt_sources_list() -> List[str]:
    """Получает список API-источников iXBT для команды /ixbt"""
    raw = os.getenv("IXBT_SOURCES", "")
    return [source.strip() for source in raw.split(',') if source.strip()]

def get_image_config() -> dict:
    config_path = Path(__file__).parent / "config.json"
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_max_news_per_source() -> int:
    """Получает максимальное количество новостей с одного источника"""
    try:
        return int(os.getenv("MAX_NEWS_PER_SOURCE", "5"))
    except ValueError:
        return 5

# Глобальные настройки
settings = get_settings()
image_config = get_image_config()
news_sources_list = get_news_sources_list()
ixbt_sources_list = get_ixbt_sources_list()
max_news_per_source = get_max_news_per_source()