"""
Обработчики меню
"""
import logging
from database import save_user
from bot.utils import send_message, send_message_with_keyboard, send_message_with_reply_keyboard
from bot.config import VISION_MODEL_ENABLED

logger = logging.getLogger(__name__)

def show_role_selection(chat_id):
    """Показывает выбор роли (волонтёр/нуждающийся)"""
    buttons = [
        [{"type": "callback", "text": "🙋 Я нуждающийся", "payload": "role_needy"}],
        [{"type": "callback", "text": "❤️ Я волонтёр", "payload": "role_volunteer"}]
    ]

    send_message_with_keyboard(
        chat_id,
        "Добро пожаловать! Выберите вашу роль:",
        buttons
    )

def show_needy_menu(chat_id):
    """Показывает главное меню для нуждающегося"""
    # Изменяем текст кнопки в зависимости от статуса нейронки
    image_button_text = "📷 Изображение → Текст"
    if not VISION_MODEL_ENABLED:
        image_button_text += " (заглушка)"

    # Inline кнопки (появляются под сообщением)
    inline_buttons = [
        [{"type": "callback", "text": "📞 Запросить звонок волонтёра", "payload": "request_call"}],
        [{"type": "callback", "text": "🎤 Голосовое → Текст", "payload": "voice_to_text"}],
        [{"type": "callback", "text": "🔊 Текст → Голосовое (скоро)", "payload": "text_to_voice"}],
        [{"type": "callback", "text": image_button_text, "payload": "image_to_text"}],
        [{"type": "callback", "text": "🆘 SOS", "payload": "sos"}]
    ]

    menu_text = "Выберите функцию:"
    if not VISION_MODEL_ENABLED:
        menu_text += "\n\n⚠️ Vision Model работает в режиме заглушек"

    # Отправляем с inline клавиатурой
    send_message_with_keyboard(
        chat_id,
        menu_text,
        inline_buttons
    )

def show_volunteer_menu(chat_id):
    """Показывает главное меню для волонтёра"""
    # Inline кнопки
    inline_buttons = [
        [{"type": "callback", "text": "📊 Моя статистика", "payload": "my_stats"}],
        [{"type": "callback", "text": "📋 Активные запросы", "payload": "active_requests"}]
    ]

    send_message_with_keyboard(
        chat_id,
        "Добро пожаловать, волонтёр!\n\nВы будете получать уведомления о новых запросах.",
        inline_buttons
    )

def handle_role_selection(chat_id, role, username, user_id=None, start_message_id=None):
    """Обработка выбора роли пользователем"""
    save_user(chat_id, role, username)

    if role == "volunteer":
        send_message(chat_id, "✅ Вы зарегистрированы как волонтёр!\n\nВы будете получать уведомления о запросах на помощь от нуждающихся.")
        show_volunteer_menu(chat_id)
    else:  # needy
        send_message(chat_id, "✅ Добро пожаловать!\n\nИнструкция:\n- Вы можете запросить звонок от волонтёра\n- Использовать функции распознавания голоса и текста\n- В экстренной ситуации нажмите кнопку SOS")
        show_needy_menu(chat_id)
