"""
Обёртки для отправки сообщений с автоматическим добавлением кнопки меню
"""
import logging
from .max_api import send_message as _send_message_api, send_message_with_keyboard as _send_message_with_keyboard_api

logger = logging.getLogger(__name__)

def send_message_with_menu_button(chat_id, text, attachments=None, markup=None, add_menu_button=True):
    """
    Отправляет сообщение с автоматическим добавлением кнопки меню для нуждающихся

    Args:
        chat_id: ID чата
        text: Текст сообщения
        attachments: Вложения
        markup: Markup (mentions и т.д.)
        add_menu_button: Добавлять ли кнопку меню (по умолчанию True)
    """
    if not add_menu_button:
        return _send_message_api(chat_id, text, attachments, markup)

    # Проверяем, нуждающийся ли это
    from database import get_user
    user = get_user(chat_id)

    # Добавляем кнопку меню только для нуждающихся
    if user and user.get('role') == 'needy':
        # Создаём клавиатуру с кнопкой меню
        keyboard_buttons = [[{
            "type": "message",
            "text": "📋 Меню",
            "payload": "/menu"
        }]]

        # Добавляем клавиатуру к сообщению
        if not attachments:
            attachments = []

        attachments.append({
            "type": "inline_keyboard",
            "payload": {
                "buttons": keyboard_buttons
            }
        })

    return _send_message_api(chat_id, text, attachments, markup)

def send_message_with_keyboard_and_menu(chat_id, text, buttons, add_menu_button=True):
    """
    Отправляет сообщение с inline клавиатурой и кнопкой меню

    Args:
        chat_id: ID чата
        text: Текст сообщения
        buttons: Inline кнопки
        add_menu_button: Добавлять ли кнопку "Назад в меню" (по умолчанию True)
    """
    # Проверяем, нуждающийся ли это
    from database import get_user
    user = get_user(chat_id)

    # Добавляем кнопку "Назад в меню" только для нуждающихся
    if add_menu_button and user and user.get('role') == 'needy':
        # Проверяем, нет ли уже кнопки меню
        has_menu_button = False
        for row in buttons:
            for btn in row:
                if btn.get('payload') == 'menu' or btn.get('text') == '🔙 Назад в меню':
                    has_menu_button = True
                    break

        # Добавляем кнопку меню, если её ещё нет
        if not has_menu_button:
            buttons = buttons + [[{"type": "callback", "text": "🔙 Назад в меню", "payload": "menu"}]]

    return _send_message_with_keyboard_api(chat_id, text, buttons)
