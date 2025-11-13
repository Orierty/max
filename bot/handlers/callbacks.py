"""
Обработчики callback запросов
"""
import logging
from database import get_user
from bot.utils import answer_callback, send_message
from .menu import handle_role_selection, show_needy_menu, show_volunteer_menu, show_moderator_menu
from .requests import (
    handle_request_call, handle_accept_request, handle_complete_request,
    handle_add_tag, handle_skip_tags, handle_rate_volunteer, handle_complaint
)
from .image import handle_image_to_text_request
from .sos import handle_sos
from .voice import handle_voice_to_text_request
from .verification import (
    handle_verification_request,
    handle_photo_description_request,
    show_photo_requests_for_volunteer,
    handle_take_photo_request
)
from .moderator import (
    show_verification_requests,
    show_verification_request_details,
    approve_verification,
    reject_verification,
    show_complaints,
    show_complaint_details,
    block_volunteer,
    dismiss_complaint
)

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

    elif payload == "voice_to_text":
        handle_voice_to_text_request(chat_id)
        answer_callback(callback_id)

    elif payload == "text_to_voice":
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

    # Верификация волонтеров
    elif payload == "request_verification":
        handle_verification_request(chat_id)
        answer_callback(callback_id)

    # Запросы на описание фото
    elif payload == "request_photo_description":
        handle_photo_description_request(chat_id)
        answer_callback(callback_id)

    elif payload == "volunteer_photo_requests":
        show_photo_requests_for_volunteer(chat_id)
        answer_callback(callback_id)

    elif payload.startswith("take_photo_"):
        request_id = int(payload.replace("take_photo_", ""))
        handle_take_photo_request(chat_id, request_id)
        answer_callback(callback_id)

    elif payload.startswith("view_photo_"):
        request_id = int(payload.replace("view_photo_", ""))
        handle_take_photo_request(chat_id, request_id)
        answer_callback(callback_id)

    # Жалобы
    elif payload.startswith("complaint_"):
        request_id = payload.replace("complaint_", "")
        handle_complaint(chat_id, request_id)
        answer_callback(callback_id)

    # Модератор - Верификация
    elif payload == "mod_verifications":
        show_verification_requests(chat_id)
        answer_callback(callback_id)

    elif payload.startswith("mod_verify_"):
        request_id = int(payload.replace("mod_verify_", ""))
        show_verification_request_details(chat_id, request_id)
        answer_callback(callback_id)

    elif payload.startswith("mod_approve_"):
        request_id = int(payload.replace("mod_approve_", ""))
        approve_verification(chat_id, request_id)
        answer_callback(callback_id)

    elif payload.startswith("mod_reject_"):
        request_id = int(payload.replace("mod_reject_", ""))
        reject_verification(chat_id, request_id)
        answer_callback(callback_id)

    # Модератор - Жалобы
    elif payload == "mod_complaints":
        show_complaints(chat_id)
        answer_callback(callback_id)

    elif payload.startswith("mod_complaint_"):
        complaint_id = int(payload.replace("mod_complaint_", ""))
        show_complaint_details(chat_id, complaint_id)
        answer_callback(callback_id)

    elif payload.startswith("mod_block_"):
        complaint_id = int(payload.replace("mod_block_", ""))
        block_volunteer(chat_id, complaint_id)
        answer_callback(callback_id)

    elif payload.startswith("mod_dismiss_"):
        complaint_id = int(payload.replace("mod_dismiss_", ""))
        dismiss_complaint(chat_id, complaint_id)
        answer_callback(callback_id)

    # Навигационные кнопки
    elif payload == "show_menu" or payload == "refresh_menu" or payload == "menu":
        # Показываем меню в зависимости от роли пользователя
        user = get_user(chat_id)
        if user:
            if user.get("role") == "needy":
                show_needy_menu(chat_id)
            elif user.get("role") == "volunteer":
                show_volunteer_menu(chat_id)
            elif user.get("role") == "moderator":
                show_moderator_menu(chat_id)
        answer_callback(callback_id)

    elif payload == "moderator_menu":
        show_moderator_menu(chat_id)
        answer_callback(callback_id)

    else:
        logger.warning(f"Неизвестный payload: {payload}")
        answer_callback(callback_id, "Неизвестная команда")
