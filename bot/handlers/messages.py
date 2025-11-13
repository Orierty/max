"""
Обработчики текстовых сообщений
"""
import logging
from database import get_user, save_user
from bot.utils import send_message
from .menu import show_role_selection, show_needy_menu, show_volunteer_menu, show_moderator_menu
from .image import handle_image_processing
from .sos import handle_sos_location
from .voice import handle_voice_message, handle_voice_to_text_only, voice_mode
from .verification import (
    verification_states, photo_description_states,
    handle_verification_documents, handle_photo_for_description,
    handle_photo_description
)
from .requests import complaint_states, handle_complaint_reason

logger = logging.getLogger(__name__)

def handle_start(chat_id, username, user_id):
    """Обработка команды /start"""
    user = get_user(chat_id)

    if user:
        role = user.get("role")
        if role == "volunteer":
            send_message(chat_id, "Вы уже зарегистрированы как волонтёр!")
        else:
            send_message(chat_id, f"С возвращением! Вы зарегистрированы как {'волонтёр' if role == 'volunteer' else 'нуждающийся'}.")
            show_needy_menu(chat_id)
    else:
        show_role_selection(chat_id)

def handle_switch_role(chat_id, username, user_id=None):
    """Переключение роли пользователя для тестирования"""
    user = get_user(chat_id)

    if not user or not user.get("role"):
        send_message(chat_id, "Сначала используйте /start для регистрации")
        return

    # Переключаем роль
    new_role = "volunteer" if user["role"] == "needy" else "needy"
    save_user(chat_id, new_role, username)

    if new_role == "volunteer":
        send_message(chat_id, "🔄 Роль изменена на: Волонтёр\n\nВы будете получать запросы от нуждающихся.")
    else:
        send_message(chat_id, "🔄 Роль изменена на: Нуждающийся\n\nВам доступно меню функций.")
        show_needy_menu(chat_id)

def handle_message(update):
    """Обработка входящего сообщения"""
    message = update.get('message', {})
    recipient = message.get('recipient', {})
    body = message.get('body', {})
    sender = message.get('sender', {})

    chat_id = recipient.get('chat_id')
    text = body.get('text', '')
    message_id = body.get('mid')
    # Пробуем получить username или name
    username = sender.get('username') or sender.get('name')
    user_id = sender.get('user_id')

    if not chat_id:
        return

    # Проверяем наличие вложений (геолокация, изображения, голосовые и т.д.)
    attachments = body.get('attachments', [])
    location = None
    image_url = None
    voice_url = None

    for attachment in attachments:
        if attachment.get('type') == 'location':
            location = {
                'latitude': attachment.get('latitude'),
                'longitude': attachment.get('longitude')
            }
            break
        elif attachment.get('type') == 'image':
            # Получаем URL изображения
            image_url = attachment.get('payload', {}).get('url')
            break
        elif attachment.get('type') == 'audio' or attachment.get('type') == 'voice':
            # Получаем URL голосового сообщения
            voice_url = attachment.get('payload', {}).get('url')
            break

    # Обрабатываем геолокацию для SOS
    if location:
        logger.info(f"Получена геолокация из чата {chat_id}: {location['latitude']}, {location['longitude']}")
        handle_sos_location(chat_id, username, user_id, location)
        return

    # Обрабатываем изображения
    if image_url:
        logger.info(f"Получено изображение из чата {chat_id}: {image_url}")

        # Проверяем, ждем ли мы фото для описания
        if chat_id in photo_description_states and photo_description_states[chat_id] == "waiting_for_photo":
            handle_photo_for_description(chat_id, attachments)
            return

        # Проверяем, ждем ли мы документы для верификации
        if chat_id in verification_states and verification_states[chat_id] == "waiting_for_documents":
            handle_verification_documents(chat_id, text, attachments)
            return

        # Обычная обработка изображения
        handle_image_processing(chat_id, image_url)
        return

    # Обрабатываем голосовые сообщения
    if voice_url:
        logger.info(f"Получено голосовое сообщение из чата {chat_id}: {voice_url}")

        # Проверяем режим обработки голоса
        if chat_id in voice_mode and voice_mode[chat_id] == "text_only":
            # Только распознавание текста, без команд
            handle_voice_to_text_only(chat_id, voice_url)
        else:
            # Обычный режим с распознаванием команд
            handle_voice_message(chat_id, voice_url, username, user_id)
        return

    # Обрабатываем текстовые сообщения
    if not text:
        return

    logger.info(f"Сообщение от {username} ({chat_id}): {text}")

    # Обработка команд
    if text.strip().lower() in ['/start', 'start', 'старт']:
        handle_start(chat_id, username, user_id)
    elif text.strip().lower() in ['/menu', 'menu', 'меню', '📋 меню']:
        user = get_user(chat_id)
        if user:
            role = user.get("role")
            if role == "needy":
                show_needy_menu(chat_id)
            elif role == "volunteer":
                show_volunteer_menu(chat_id)
            elif role == "moderator":
                show_moderator_menu(chat_id)
        else:
            send_message(chat_id, "Используйте /start для регистрации")
    elif text.strip().lower() in ['🔄 обновить', 'обновить', 'update']:
        # Обновить = показать меню заново
        user = get_user(chat_id)
        if user:
            role = user.get("role")
            if role == "needy":
                show_needy_menu(chat_id)
            elif role == "volunteer":
                show_volunteer_menu(chat_id)
            elif role == "moderator":
                show_moderator_menu(chat_id)
        else:
            send_message(chat_id, "Используйте /start для регистрации")
    elif text.strip().lower() in ['/switch_role', '/switch']:
        handle_switch_role(chat_id, username, user_id)
    elif text.strip().lower() == '/moderator':
        # Временная команда для назначения модератора (для тестирования)
        user = get_user(chat_id)
        if user:
            save_user(chat_id, 'moderator', username)
            send_message(chat_id, "✅ Вы назначены модератором!\n\nИспользуйте /menu для доступа к панели модерации.")
            show_moderator_menu(chat_id)
        else:
            send_message(chat_id, "Сначала используйте /start для регистрации")
    else:
        # Проверяем состояния ожидания ввода

        # Обработка описания фото от волонтера
        if chat_id in photo_description_states:
            state = photo_description_states[chat_id]
            if state.startswith("describing_"):
                if handle_photo_description(chat_id, text):
                    return

        # Обработка причины жалобы
        if chat_id in complaint_states:
            if handle_complaint_reason(chat_id, text):
                return

        # Обработка документов для верификации (текстовый комментарий)
        if chat_id in verification_states and verification_states[chat_id] == "waiting_for_documents":
            send_message(chat_id, "⚠️ Пожалуйста, отправьте фото или файлы документов (паспорт, справка о несудимости).\n\nВаш комментарий будет сохранен.")
            return

        # Эхо для зарегистрированных пользователей
        user = get_user(chat_id)
        if user:
            role = user.get("role")
            if role == "moderator":
                send_message(chat_id, "Используйте /menu для вызова панели модератора")
            else:
                send_message(chat_id, f"Вы написали: {text}\n\nИспользуйте /menu для вызова меню")
        else:
            send_message(chat_id, "Используйте /start для начала работы")
