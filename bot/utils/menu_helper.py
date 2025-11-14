"""
Помощник для автоматического добавления кнопки "Назад в меню"
"""

def add_menu_button_if_needed(buttons, chat_id=None):
    """
    Добавляет кнопку "Назад в меню" к списку кнопок, если её там ещё нет

    Args:
        buttons: Список кнопок (двумерный массив)
        chat_id: ID чата (опционально, для проверки роли)

    Returns:
        Список кнопок с добавленной кнопкой меню
    """
    if not buttons:
        buttons = []

    # Проверяем, есть ли уже кнопка меню
    has_menu_button = False
    for row in buttons:
        for btn in row:
            payload = btn.get('payload', '')
            text = btn.get('text', '')
            if payload == 'menu' or 'меню' in text.lower() or 'назад' in text.lower():
                has_menu_button = True
                break
        if has_menu_button:
            break

    # Если кнопки меню нет, добавляем её
    if not has_menu_button:
        # Если chat_id передан, проверяем роль пользователя
        if chat_id:
            from database import get_user
            user = get_user(chat_id)
            # Добавляем кнопку только для нуждающихся
            if user and user.get('role') == 'needy':
                buttons.append([{"type": "callback", "text": "🔙 Назад в меню", "payload": "menu"}])
        else:
            # Если chat_id не передан, добавляем кнопку всегда
            buttons.append([{"type": "callback", "text": "🔙 Назад в меню", "payload": "menu"}])

    return buttons
