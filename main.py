"""
Max.ru Bot - Главный файл
Бот для связи волонтёров с нуждающимися
"""
import logging
import time
import sys
import os

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Импорт конфигурации
try:
    from bot.config import MAX_TOKEN, VISION_MODEL_ENABLED, DOWNLOADS_DIR
except ImportError as e:
    logger.error(f"Ошибка импорта конфигурации: {e}")
    logger.error("Убедитесь, что файл .env настроен правильно")
    sys.exit(1)

# Импорт утилит
from bot.utils import get_updates, get_bot_info

# Импорт database
from database import init_db_pool, close_db_pool

# Импорт обработчиков
from bot.handlers.messages import handle_message
from bot.handlers.callbacks import handle_callback

# Импорт wave sender
from bot.wave_sender import start_wave_sender, stop_wave_sender

logger.info(f"Vision Model: {'ENABLED' if VISION_MODEL_ENABLED else 'DISABLED (using stubs)'}")

def main():
    """Главная функция бота"""
    logger.info("Запуск Max.ru бота волонтёров...")

    # Инициализируем подключение к PostgreSQL
    if not init_db_pool():
        logger.error("Не удалось подключиться к PostgreSQL. Проверьте настройки в .env")
        return

    # Создаём папку для загрузок
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)

    # Получаем информацию о боте
    bot_info = get_bot_info()
    if bot_info:
        logger.info(f"Бот запущен: {bot_info.get('name')} (@{bot_info.get('username')})")
    else:
        logger.error("Не удалось получить информацию о боте. Проверьте токен.")
        close_db_pool()
        return

    logger.info("Ожидание сообщений...")

    # Запускаем фоновый поток для отправки волн
    start_wave_sender()

    marker = None
    error_count = 0
    max_errors = 5

    try:
        while True:
            try:
                # Получаем обновления
                data = get_updates(marker)

                if data:
                    updates = data.get("updates", [])

                    for update in updates:
                        try:
                            update_type = update.get('update_type')

                            # Обрабатываем новые сообщения
                            if update_type == 'message_created':
                                handle_message(update)
                            # Обрабатываем callback'и (нажатия на кнопки)
                            elif update_type == 'message_callback':
                                handle_callback(update)

                        except Exception as e:
                            logger.error(f"Ошибка обработки обновления: {e}", exc_info=True)

                    # Обновляем marker
                    new_marker = data.get("marker")
                    if new_marker:
                        marker = new_marker

                    # Сбрасываем счётчик ошибок при успешной обработке
                    error_count = 0
                else:
                    time.sleep(1)

            except KeyboardInterrupt:
                logger.info("Получен сигнал остановки")
                break

            except Exception as e:
                error_count += 1
                logger.error(f"Неожиданная ошибка ({error_count}/{max_errors}): {e}", exc_info=True)

                if error_count >= max_errors:
                    logger.error("Слишком много ошибок подряд. Перезапуск через 30 секунд...")
                    time.sleep(30)
                    error_count = 0
                    marker = None
                else:
                    time.sleep(5)

    finally:
        stop_wave_sender()
        close_db_pool()
        logger.info("Бот остановлен")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)
