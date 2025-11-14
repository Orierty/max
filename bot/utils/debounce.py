"""
Система защиты от множественных нажатий (debounce)
"""
import time
import logging
from threading import Lock

logger = logging.getLogger(__name__)

# Хранилище последних действий пользователей
# Формат: {(chat_id, action): timestamp}
_last_actions = {}
_lock = Lock()

# Время ожидания между одинаковыми действиями (в секундах)
DEBOUNCE_TIME = 2  # 2 секунды

def is_action_allowed(chat_id, action):
    """
    Проверяет, можно ли выполнить действие (прошло ли достаточно времени с последнего)

    Args:
        chat_id: ID чата пользователя
        action: Название действия (например, "request_call", "accept_request_123")

    Returns:
        bool: True если действие разрешено, False если нужно подождать
    """
    with _lock:
        key = (str(chat_id), action)
        current_time = time.time()

        # Проверяем, было ли это действие недавно
        if key in _last_actions:
            time_since_last = current_time - _last_actions[key]

            if time_since_last < DEBOUNCE_TIME:
                logger.warning(f"Debounce: пользователь {chat_id} пытается повторить действие '{action}' слишком быстро")
                return False

        # Разрешаем действие и сохраняем время
        _last_actions[key] = current_time

        # Очищаем старые записи (старше 10 секунд)
        _cleanup_old_actions(current_time)

        return True

def _cleanup_old_actions(current_time):
    """Удаляет старые записи из кэша"""
    keys_to_remove = []

    for key, timestamp in _last_actions.items():
        if current_time - timestamp > 10:  # Старше 10 секунд
            keys_to_remove.append(key)

    for key in keys_to_remove:
        del _last_actions[key]

def clear_action(chat_id, action):
    """
    Принудительно очищает действие (используется когда нужно разрешить повторное действие)
    """
    with _lock:
        key = (str(chat_id), action)
        if key in _last_actions:
            del _last_actions[key]
