"""
Функции для работы с Max.ru API
"""
import requests
import logging
from bot.config import BASE_URL, HEADERS

logger = logging.getLogger(__name__)

def get_updates(marker=None):
    """Получает новые обновления через long polling"""
    params = {}
    if marker is not None:
        params['marker'] = marker

    response = requests.get(f"{BASE_URL}/updates", headers=HEADERS, params=params)

    if response.status_code == 200:
        data = response.json()
        return data
    else:
        logger.error(f"Ошибка получения обновлений: {response.status_code}")
        logger.error(f"Ответ сервера: {response.text}")
        return None

def send_message(chat_id, text, attachments=None, markup=None):
    """Отправляет сообщение в чат с optional inline клавиатурой и markup"""
    params = {"chat_id": chat_id}

    data = {"text": text}

    if attachments:
        data["attachments"] = attachments

    if markup:
        data["markup"] = markup

    response = requests.post(f"{BASE_URL}/messages", headers=HEADERS, params=params, json=data)

    if response.status_code == 200:
        logger.info(f"Сообщение отправлено в чат {chat_id}: {text}")
        return response.json()
    else:
        logger.error(f"Ошибка отправки сообщения: {response.status_code}, {response.text}")
        return None

def send_message_with_keyboard(chat_id, text, buttons, markup=None):
    """Отправляет сообщение с inline клавиатурой"""
    attachments = [{
        "type": "inline_keyboard",
        "payload": {
            "buttons": buttons
        }
    }]
    return send_message(chat_id, text, attachments, markup=markup)

def answer_callback(callback_id, text=None):
    """Отвечает на callback query"""
    params = {"callback_id": callback_id}

    data = {}
    # notification должен быть строкой, а не объектом
    if text:
        data["notification"] = text
    else:
        # Пустая строка для подтверждения нажатия
        data["notification"] = ""

    response = requests.post(f"{BASE_URL}/answers", headers=HEADERS, params=params, json=data)

    if response.status_code == 200:
        logger.info("Ответ на callback отправлен")
        return response.json()
    else:
        logger.error(f"Ошибка ответа на callback: {response.status_code}, {response.text}")
        return None

def send_location(chat_id, latitude, longitude):
    """Отправляет геолокацию в чат"""
    params = {"chat_id": chat_id}

    data = {
        "text": "",
        "attachments": [
            {
                "type": "location",
                "latitude": latitude,
                "longitude": longitude
            }
        ],
        "link": None
    }

    response = requests.post(f"{BASE_URL}/messages", headers=HEADERS, params=params, json=data)

    if response.status_code == 200:
        logger.info(f"Геолокация отправлена в чат {chat_id}: {latitude}, {longitude}")
        return response.json()
    else:
        logger.error(f"Ошибка отправки геолокации: {response.status_code}, {response.text}")
        return None

def get_bot_info():
    """Получает информацию о боте"""
    response = requests.get(f"{BASE_URL}/me", headers=HEADERS)

    if response.status_code == 200:
        return response.json()
    else:
        logger.error(f"Ошибка получения информации о боте: {response.status_code}")
        return None

def get_bot_link(start_payload=None):
    """Генерирует deep link на бота"""
    bot_info = get_bot_info()
    if bot_info and bot_info.get('username'):
        username = bot_info['username']
        if start_payload:
            return f"https://max.ru/{username}?start={start_payload}"
        else:
            return f"https://max.ru/{username}"
    return None

def forward_message(chat_id, message_id, text=None):
    """Пересылает сообщение в чат"""
    params = {"chat_id": chat_id}

    data = {
        "text": text,
        "attachments": None,
        "link": {
            "type": "forward",
            "mid": str(message_id)
        }
    }

    logger.debug(f"DEBUG forward: chat_id={chat_id}, message_id={message_id}, text={text}")
    logger.debug(f"DEBUG forward data: {data}")

    response = requests.post(f"{BASE_URL}/messages", headers=HEADERS, params=params, json=data)

    if response.status_code == 200:
        logger.info(f"Сообщение переслано в чат {chat_id}")
        return response.json()
    else:
        logger.error(f"Ошибка пересылки сообщения: {response.status_code}, {response.text}")
        return None

def create_user_mention(text, username=None, user_id=None):
    """Создаёт текст с mention пользователя и markup для него"""
    if username:
        mention_text = f"@{username}"
    elif user_id:
        mention_text = f"Пользователь {user_id}"
    else:
        mention_text = "неизвестно"

    full_text = text.replace("{mention}", mention_text)

    # Создаём markup для mention
    markup = []
    if user_id or username:
        mention_start = full_text.index(mention_text)
        markup_item = {
            "type": "user_mention",
            "from": mention_start,
            "length": len(mention_text)
        }
        if username:
            markup_item["user_link"] = f"@{username}"
        if user_id:
            markup_item["user_id"] = int(user_id)
        markup.append(markup_item)

    return full_text, markup if markup else None
