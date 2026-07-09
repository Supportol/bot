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
    drom_sources: str
    ixbt_sources: str = ""
    motor_honda_source: str = ""
    motor_acura_source: str = ""
    text_api_key: str = ""
    max_news_per_source: int = 5  # Значение по умолчанию
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

def get_settings() -> Settings:
    return Settings(
        bot_token=os.getenv("BOT_TOKEN"),
        drom_sources=os.getenv("DROM_SOURCES", ""),
        ixbt_sources=os.getenv("IXBT_SOURCES", ""),
        motor_honda_source=os.getenv("MOTOR_HONDA_SOURCE", ""),
        motor_acura_source=os.getenv("MOTOR_ACURA_SOURCE", ""),
        text_api_key=os.getenv("TEXT_API_KEY", ""),
        max_news_per_source=int(os.getenv("MAX_NEWS_PER_SOURCE", "5"))
    )

def get_drom_sources_list() -> List[str]:
    """Получает список источников для команды /news."""
    raw = os.getenv("DROM_SOURCES", "")
    return [source.strip() for source in raw.split(',') if source.strip()]

def get_ixbt_sources_list() -> List[str]:
    """Получает список API-источников iXBT для команды /ixbt"""
    raw = os.getenv("IXBT_SOURCES", "")
    return [source.strip() for source in raw.split(',') if source.strip()]

def get_motor_sources_list() -> List[str]:
    """Получает список API-источников Motor.ru для Honda/Acura."""
    raw_sources = [
        os.getenv("MOTOR_HONDA_SOURCE", "").strip(),
        os.getenv("MOTOR_ACURA_SOURCE", "").strip(),
    ]
    return [source for source in raw_sources if source]

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
drom_sources_list = get_drom_sources_list()
ixbt_sources_list = get_ixbt_sources_list()
motor_sources_list = get_motor_sources_list()
max_news_per_source = get_max_news_per_source()