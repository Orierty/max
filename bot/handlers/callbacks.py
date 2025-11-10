"""
Обработчики callback запросов
"""
import logging
from database import get_user
from bot.utils import answer_callback, send_message
from .menu import handle_role_selection, show_needy_menu, show_volunteer_menu
from .requests import (
    handle_request_call, handle_accept_request, handle_complete_request,
    handle_add_tag, handle_skip_tags, handle_rate_volunteer
)
from .image import handle_image_to_text_request
from .sos import handle_sos

logger = logging.getLogger(__name__)

def handle_callback(update):
    """Обработка callback query"""
    callback = update.get('callback', {})
    message = update.get('message', {})

    callback_id = callback.get('callback_id')
    payload = callback.get('payload')
    user_info = callback.get('user', {})

    chat_id = message.get('recipient', {}).get('chat_id')
    message_id = message.get('body', {}).get('mid')
    # Пробуем получить username или name
    username = user_info.get('username') or user_info.get('name')
    user_id = user_info.get('user_id')

    if not callback_id or not payload or not chat_id:
        return

    logger.info(f"Callback от {username}: {payload}")

    # Выбор роли
    if payload == "role_volunteer":
        handle_role_selection(chat_id, "volunteer", username, user_id, message_id)
        answer_callback(callback_id)

    elif payload == "role_needy":
        handle_role_selection(chat_id, "needy", username, user_id, message_id)
        answer_callback(callback_id)

    # Функции нуждающегося
    elif payload == "request_call":
        handle_request_call(chat_id, username, user_id, message_id)
        answer_callback(callback_id)

    elif payload == "image_to_text":
        handle_image_to_text_request(chat_id)
        answer_callback(callback_id)

    elif payload == "sos":
        handle_sos(chat_id, username, user_id)
        answer_callback(callback_id)

    elif payload in ["voice_to_text", "text_to_voice"]:
        answer_callback(callback_id, "Эта функция скоро будет доступна!")

    # Обработка запросов волонтёров
    elif payload.startswith("accept_request_"):
        request_id = payload.replace("accept_request_", "")
        success = handle_accept_request(chat_id, request_id, username, callback_id)
        if success:
            answer_callback(callback_id)
        else:
            answer_callback(callback_id, "Этот запрос уже принят другим волонтёром")

    elif payload.startswith("complete_request_"):
        request_id = payload.replace("complete_request_", "")
        handle_complete_request(chat_id, request_id)
        answer_callback(callback_id)

    elif payload.startswith("add_tag_"):
        # Формат: add_tag_{request_id}_{tag}
        parts = payload.replace("add_tag_", "").split("_", 1)
        if len(parts) == 2:
            request_id, tag = parts
            handle_add_tag(chat_id, request_id, tag)
        answer_callback(callback_id)

    elif payload.startswith("skip_tags_"):
        request_id = payload.replace("skip_tags_", "")
        handle_skip_tags(chat_id, request_id)
        answer_callback(callback_id)

    elif payload.startswith("rate_volunteer_"):
        # Формат: rate_volunteer_{request_id}_{rating}
        parts = payload.replace("rate_volunteer_", "").rsplit("_", 1)
        if len(parts) == 2:
            request_id, rating = parts
            handle_rate_volunteer(chat_id, request_id, int(rating))
        answer_callback(callback_id)

    # Функции волонтёра
    elif payload == "my_stats":
        # TODO: Показать статистику волонтёра
        answer_callback(callback_id, "Статистика в разработке")

    elif payload == "active_requests":
        # TODO: Показать активные запросы
        answer_callback(callback_id, "Список запросов в разработке")

    else:
        logger.warning(f"Неизвестный payload: {payload}")
        answer_callback(callback_id, "Неизвестная команда")
