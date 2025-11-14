"""
Конфигурация бота
"""
import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Max.ru Bot Token
MAX_TOKEN = os.getenv("MAX_TOKEN")
if not MAX_TOKEN:
    raise ValueError("MAX_TOKEN не найден в переменных окружения! Создайте файл .env")

# Vision Model Settings
VISION_MODEL_ENABLED = os.getenv("VISION_MODEL_ENABLED", "false").lower() == "true"

# Voice Control Settings
VOICE_ENABLED = os.getenv("VOICE_ENABLED", "false").lower() == "true"

# Database Settings
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "max_bot")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

# Max.ru API
BASE_URL = "https://platform-api.max.ru"
MAX_API_URL = BASE_URL  # Алиас для совместимости
# Max.ru использует access_token как query parameter, а не Authorization header
HEADERS = {
    "Content-Type": "application/json"
}

# Пути
DOWNLOADS_DIR = "downloads"
MODELS_DIR = "models"
