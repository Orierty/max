"""
Обработчики SOS с геолокацией
"""
import logging
import time
from datetime import datetime
from database import get_all_users_by_role, create_request
from bot.utils import send_message, send_message_with_keyboard, send_location, create_user_mention

logger = logging.getLogger(__name__)

# Временное хранилище для SOS запросов (пока не в БД)
# TODO: Добавить в PostgreSQL таблицу для SOS запросов
sos_requests = {}

def handle_sos(chat_id, username, user_id=None):
    """Обработка кнопки SOS"""
    # Создаём SOS запрос
    sos_id = str(int(time.time()))
    sos_request = {
        "id": sos_id,
        "needy_chat_id": str(chat_id),
        "needy_username": username,
        "needy_user_id": user_id,
        "created_at": datetime.now().isoformat(),
        "status": "sos_pending_location",
        "type": "sos"
    }

    # Сохраняем в памяти (временно)
    sos_requests[str(chat_id)] = sos_request

    # Отправляем кнопку запроса геолокации
    buttons = [
        [{"type": "request_geo_location", "text": "📍 Поделиться местоположением", "quick": False}]
    ]
    send_message_with_keyboard(
        chat_id,
        "🆘 Сигнал SOS активирован!\n\n⚠️ Пожалуйста, поделитесь вашим местоположением, чтобы волонтёры могли вам помочь.",
        buttons
    )

def handle_sos_location(chat_id, username, user_id, location):
    """Обработка получения геолокации для SOS"""
    # Находим активный SOS запрос от этого пользователя
    sos_request = sos_requests.get(str(chat_id))

    if not sos_request or sos_request.get("status") != "sos_pending_location":
        send_message(chat_id, "⚠️ Активный SOS запрос не найден. Нажмите кнопку SOS снова.")
        return

    # Обновляем статус и сохраняем геолокацию
    sos_request["status"] = "sos_active"
    sos_request["latitude"] = location["latitude"]
    sos_request["longitude"] = location["longitude"]

    # Отправляем SOS всем волонтёрам с геолокацией
    volunteers = get_all_users_by_role("volunteer")
    volunteers_notified = 0

    for user_chat_id, user_data in volunteers.items():
        # Формируем сообщение с упоминанием пользователя
        text, markup = create_user_mention(
            f"🆘🆘🆘 ЭКСТРЕННЫЙ СИГНАЛ SOS!\n\nОт: {{mention}}\nВремя: {datetime.now().strftime('%H:%M:%S')}\n📍 Координаты: {location['latitude']}, {location['longitude']}\n\n⚠️ Требуется срочная помощь!",
            username=username,
            user_id=user_id
        )

        # Отправляем сообщение
        send_message(user_chat_id, text, markup=markup)

        # Отправляем геолокацию отдельным сообщением
        send_location(user_chat_id, location["latitude"], location["longitude"])

        volunteers_notified += 1

    # Помечаем запрос как завершённый
    sos_request["status"] = "completed"
    sos_request["completed_at"] = datetime.now().isoformat()

    send_message(chat_id, f"✅ Сигнал SOS с вашим местоположением отправлен {volunteers_notified} волонтёрам!")
