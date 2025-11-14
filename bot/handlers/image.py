"""
Обработчики распознавания изображений
"""
import logging
import os
import time
from datetime import datetime
from database import get_request, create_request, complete_request
from bot.utils import send_message, download_image, describe_image, send_message_with_menu_button
from bot.config import DOWNLOADS_DIR

logger = logging.getLogger(__name__)

def handle_image_to_text_request(chat_id):
    """Обработка запроса на распознавание изображения"""
    # Создаём запрос на ожидание фото в PostgreSQL
    request_id = create_request(chat_id, urgency="normal")

    # Помечаем запрос как ожидающий изображение
    # TODO: Добавить поле type в таблицу requests или использовать отдельную таблицу

    send_message_with_menu_button(chat_id, "📷 Отправьте мне фотографию, и я опишу что на ней изображено.\n\nПросто прикрепите фото к следующему сообщению.")

def handle_image_processing(chat_id, image_url):
    """Обработка полученного изображения"""
    try:
        # Отправляем сообщение о начале обработки
        send_message_with_menu_button(chat_id, "⏳ Обрабатываю изображение, подождите немного...")

        # Скачиваем изображение
        image_filename = f"image_{chat_id}_{int(time.time())}.jpg"
        image_path = os.path.join(DOWNLOADS_DIR, image_filename)

        if not download_image(image_url, image_path):
            send_message_with_menu_button(chat_id, "❌ Ошибка при скачивании изображения. Попробуйте ещё раз.")
            return

        # Распознаём изображение
        description = describe_image(image_path)

        # Отправляем результат
        send_message_with_menu_button(chat_id, f"📝 Описание изображения:\n\n{description}")

        # Удаляем временный файл изображения
        try:
            os.remove(image_path)
            logger.info(f"Временный файл {image_path} удалён")
        except:
            pass

    except Exception as e:
        logger.error(f"Ошибка при обработке изображения: {e}", exc_info=True)
        send_message_with_menu_button(chat_id, f"❌ Произошла ошибка при обработке изображения: {str(e)}")
