"""
Обработчики текстовых сообщений
"""
import logging
from database import get_user, save_user
from bot.utils import send_message
from .menu import show_role_selection, show_needy_menu
from .image import handle_image_processing
from .sos import handle_sos_location
from .voice import handle_voice_message

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
        handle_image_processing(chat_id, image_url)
        return

    # Обрабатываем голосовые сообщения
    if voice_url:
        logger.info(f"Получено голосовое сообщение из чата {chat_id}: {voice_url}")
        handle_voice_message(chat_id, voice_url, username, user_id)
        return

    # Обрабатываем текстовые сообщения
    if not text:
        return

    logger.info(f"Сообщение от {username} ({chat_id}): {text}")

    # Обработка команд
    if text.strip().lower() in ['/start', 'start', 'старт']:
        handle_start(chat_id, username, user_id)
    elif text.strip().lower() in ['/menu', 'menu', 'меню']:
        user = get_user(chat_id)
        if user and user.get("role") == "needy":
            show_needy_menu(chat_id)
        else:
            send_message(chat_id, "Используйте /start для регистрации")
    elif text.strip().lower() in ['/switch_role', '/switch']:
        handle_switch_role(chat_id, username, user_id)
    else:
        # Эхо для зарегистрированных пользователей
        user = get_user(chat_id)
        if user:
            send_message(chat_id, f"Вы написали: {text}\n\nИспользуйте /menu для вызова меню")
        else:
            send_message(chat_id, "Используйте /start для начала работы")
