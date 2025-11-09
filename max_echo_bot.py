import requests
import time
import sys
import os
import json
from datetime import datetime


MAX_TOKEN = "f9LHodD0cOLlinzAz04btRFhnP3C8M0E3pndlaixzJo2Jgaivnoz5pSguc3ZHT8MAmiY_Mg4bTQ9yJZCz8XC"

BASE_URL = "https://platform-api.max.ru"

HEADERS = {
    "Authorization": MAX_TOKEN,
    "Content-Type": "application/json"
}


def load_db():
    """Загружает базу данных из JSON файла"""
    try:
        with open("database.json", "r", encoding="utf-8") as f:
            db = json.load(f)
            # Проверяем структуру базы данных
            if not isinstance(db, dict):
                raise ValueError("База данных повреждена: не является словарём")
            if "users" not in db:
                db["users"] = {}
            if "active_requests" not in db:
                db["active_requests"] = []
            if "completed_requests" not in db:
                db["completed_requests"] = []
            return db
    except FileNotFoundError:
        print("⚠️  Файл database.json не найден, создаём новый")
        return {"users": {}, "active_requests": [], "completed_requests": []}
    except json.JSONDecodeError as e:
        print(f"❌ Ошибка чтения database.json: {e}")
        # Создаём резервную копию повреждённого файла
        import shutil
        import time
        backup_name = f"database_corrupted_{int(time.time())}.json"
        try:
            shutil.copy("database.json", backup_name)
            print(f"💾 Создана резервная копия: {backup_name}")
        except:
            pass
        return {"users": {}, "active_requests": [], "completed_requests": []}
    except Exception as e:
        print(f"❌ Неожиданная ошибка при загрузке БД: {e}")
        return {"users": {}, "active_requests": [], "completed_requests": []}

def save_db(db):
    """Сохраняет базу данных в JSON файл безопасно через временный файл"""
    try:
        # Сохраняем во временный файл
        temp_file = "database.json.tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)

        # Если запись успешна, заменяем основной файл
        import shutil
        shutil.move(temp_file, "database.json")
    except Exception as e:
        print(f"❌ Ошибка сохранения БД: {e}")
        # Удаляем временный файл если он существует
        if os.path.exists("database.json.tmp"):
            try:
                os.remove("database.json.tmp")
            except:
                pass

def get_user(chat_id):
    """Получает данные пользователя"""
    db = load_db()
    return db["users"].get(str(chat_id))

def save_user(chat_id, role, username=None, user_id=None, start_message_id=None):
    """Сохраняет пользователя в базу"""
    db = load_db()

    # Получаем существующие данные пользователя, если есть
    existing_user = db["users"].get(str(chat_id), {})

    user_data = {
        "role": role,  # "volunteer" или "needy"
        "username": username,
        "user_id": user_id,
        "registered_at": datetime.now().isoformat()
    }

    # Сохраняем start_message_id, если он передан ИЛИ если он уже есть у пользователя
    if start_message_id:
        user_data["start_message_id"] = start_message_id
    elif existing_user.get("start_message_id"):
        user_data["start_message_id"] = existing_user["start_message_id"]

    db["users"][str(chat_id)] = user_data
    save_db(db)

# === API функции ===

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
        print(f"Ошибка получения обновлений: {response.status_code}")
        print(f"Ответ сервера: {response.text}")
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
        print(f"Сообщение отправлено в чат {chat_id}: {text}", flush=True)
        return response.json()
    else:
        print(f"Ошибка отправки сообщения: {response.status_code}, {response.text}", flush=True)
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
        print(f"Геолокация отправлена в чат {chat_id}: {latitude}, {longitude}", flush=True)
        return response.json()
    else:
        print(f"Ошибка отправки геолокации: {response.status_code}, {response.text}", flush=True)
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

def send_message_with_keyboard(chat_id, text, buttons, markup=None):
    """Отправляет сообщение с inline клавиатурой"""
    attachments = [{
        "type": "inline_keyboard",
        "payload": {
            "buttons": buttons
        }
    }]
    return send_message(chat_id, text, attachments, markup=markup)

def forward_message(chat_id, message_id, text=None):
    """Пересылает сообщение в чат"""
    params = {"chat_id": chat_id}

    # Согласно swagger, все поля text, attachments, link обязательны (required)
    # даже если они nullable
    data = {
        "text": text,  # может быть None (nullable)
        "attachments": None,  # nullable
        "link": {
            "type": "forward",
            "mid": str(message_id)
        }
    }

    print(f"DEBUG forward: chat_id={chat_id}, message_id={message_id}, text={text}", flush=True)
    print(f"DEBUG forward data: {data}", flush=True)

    response = requests.post(f"{BASE_URL}/messages", headers=HEADERS, params=params, json=data)

    if response.status_code == 200:
        print(f"Сообщение переслано в чат {chat_id}", flush=True)
        return response.json()
    else:
        print(f"Ошибка пересылки сообщения: {response.status_code}, {response.text}", flush=True)
        return None

def answer_callback(callback_id, text=None):
    """Отправляет ответ на нажатие кнопки"""
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
        print(f"Ответ на callback отправлен", flush=True)
        return response.json()
    else:
        print(f"Ошибка ответа на callback: {response.status_code}, {response.text}", flush=True)
        return None

def get_bot_info():
    """Получает информацию о боте"""
    response = requests.get(f"{BASE_URL}/me", headers=HEADERS)

    if response.status_code == 200:
        return response.json()
    else:
        print(f"Ошибка получения информации о боте: {response.status_code}")
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

# === Обработчики команд ===

def handle_start(chat_id, username, user_id=None):
    """Обработка команды /start - выбор роли"""
    user = get_user(chat_id)

    if user and user.get("role"):
        # Пользователь уже зарегистрирован
        if user["role"] == "volunteer":
            send_message(chat_id, "Вы уже зарегистрированы как волонтёр!")
        else:
            show_needy_menu(chat_id)
    else:
        # Новый пользователь - предлагаем выбрать роль
        buttons = [
            [{"type": "callback", "text": "Я нуждаюсь в помощи", "payload": "role_needy"}],
            [{"type": "callback", "text": "Я волонтёр", "payload": "role_volunteer"}]
        ]
        send_message_with_keyboard(
            chat_id,
            "Добро пожаловать! Выберите вашу роль:",
            buttons
        )

def show_needy_menu(chat_id):
    """Показывает главное меню для нуждающегося"""
    buttons = [
        [{"type": "callback", "text": "Запросить звонок волонтёра", "payload": "request_call"}],
        [{"type": "callback", "text": "Голосовое → Текст (скоро)", "payload": "voice_to_text"}],
        [{"type": "callback", "text": "Текст → Голосовое (скоро)", "payload": "text_to_voice"}],
        [{"type": "callback", "text": "Изображение → Текст (скоро)", "payload": "image_to_text"}],
        [{"type": "callback", "text": "SOS", "payload": "sos"}]
    ]
    send_message_with_keyboard(
        chat_id,
        "Выберите функцию:",
        buttons
    )

def handle_role_selection(chat_id, role, username, user_id=None, start_message_id=None):
    """Обработка выбора роли пользователем"""
    save_user(chat_id, role, username, user_id, start_message_id)

    if role == "volunteer":
        bot_link = get_bot_link()
        message = "✅ Вы зарегистрированы как волонтёр!\n\nВы будете получать запросы от нуждающихся в помощи."
        if bot_link:
            message += f"\n\nДелитесь ссылкой на бота с нуждающимися:\n{bot_link}"
        send_message(chat_id, message)
    else:  # needy
        send_message(chat_id, "✅ Добро пожаловать!\n\nИнструкция:\n- Вы можете запросить звонок от волонтёра\n- Использовать функции распознавания голоса и текста\n- В экстренной ситуации нажмите кнопку SOS")
        show_needy_menu(chat_id)

def handle_request_call(chat_id, username, user_id=None, message_id=None):
    """Обработка запроса на звонок от волонтёра"""
    db = load_db()

    # Создаём запрос
    request_id = str(int(time.time()))
    request = {
        "id": request_id,
        "needy_chat_id": str(chat_id),
        "needy_username": username,
        "needy_user_id": user_id,
#        "needy_message_id": message_id,  # Сохраняем ID сообщения для пересылки
        "created_at": datetime.now().isoformat(),
        "status": "pending"
    }

    db["active_requests"].append(request)
    save_db(db)

    # Отправляем запрос всем волонтёрам
    volunteers_notified = 0
    for user_chat_id, user_data in db["users"].items():
        if user_data.get("role") == "volunteer":
            buttons = [
                [{"type": "callback", "text": "✅ Принять запрос", "payload": f"accept_request_{request_id}"}]
            ]
            send_message_with_keyboard(
                user_chat_id,
                f"🆘 Новый запрос на звонок!\n\nОт: @{username or 'неизвестно'}\nВремя: {datetime.now().strftime('%H:%M')}",
                buttons
            )
            volunteers_notified += 1

    if volunteers_notified > 0:
        send_message(chat_id, f"✅ Ваш запрос отправлен {volunteers_notified} волонтёрам. Ожидайте ответа...")
    else:
        send_message(chat_id, "⚠️ К сожалению, сейчас нет доступных волонтёров. Попробуйте позже.")

def handle_accept_request(volunteer_chat_id, request_id, volunteer_username, callback_id=None):
    """Обработка принятия запроса волонтёром"""
    db = load_db()

    # Ищем запрос
    request = None
    for req in db["active_requests"]:
        if req["id"] == request_id and req["status"] == "pending":
            request = req
            break

    if not request:
        if callback_id:
            answer_callback(callback_id, "Этот запрос уже принят другим волонтёром")
        return

    # Обновляем статус запроса
    request["status"] = "accepted"
    request["volunteer_chat_id"] = str(volunteer_chat_id)
    request["volunteer_username"] = volunteer_username
    request["accepted_at"] = datetime.now().isoformat()

    # Перемещаем в завершённые
    db["active_requests"] = [r for r in db["active_requests"] if r["id"] != request_id]
    db["completed_requests"].append(request)
    save_db(db)

    # Уведомляем волонтёра
    send_message(volunteer_chat_id, "✅ Вы приняли запрос!")


    # # Пересылаем сообщение /start нуждающегося, чтобы волонтёр мог нажать на отправителя
    # needy_user_data = db["users"].get(request["needy_chat_id"])
    # print(f"DEBUG: needy_user_data = {needy_user_data}", flush=True)
    # if needy_user_data and needy_user_data.get("start_message_id"):
    #     print(f"DEBUG: Пересылаем сообщение {needy_user_data.get('start_message_id')}", flush=True)
    #     forward_message(
    #         volunteer_chat_id,
    #         needy_user_data["start_message_id"],
    #         text="Нажмите на имя отправителя, чтобы открыть профиль и написать ему"
    #     )
    # else:
    #     print(f"DEBUG: start_message_id отсутствует у пользователя {request['needy_chat_id']}", flush=True)

    # Уведомляем нуждающегося с mention волонтёра
    volunteer_user_id = db["users"].get(str(volunteer_chat_id), {}).get("user_id")

    text, markup = create_user_mention(
        "✅ Волонтёр {mention} принял ваш запрос и скоро свяжется с вами!",
        username=volunteer_username,
        user_id=volunteer_user_id
    )
    send_message(request["needy_chat_id"], text, markup=markup)

def handle_sos(chat_id, username, user_id=None):
    """Обработка кнопки SOS"""
    db = load_db()

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

    # Сохраняем в активных запросах
    db["active_requests"].append(sos_request)
    save_db(db)

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
    db = load_db()

    # Находим активный SOS запрос от этого пользователя
    sos_request = None
    for req in db["active_requests"]:
        if req.get("type") == "sos" and req.get("needy_chat_id") == str(chat_id) and req.get("status") == "sos_pending_location":
            sos_request = req
            break

    if not sos_request:
        send_message(chat_id, "⚠️ Активный SOS запрос не найден. Нажмите кнопку SOS снова.")
        return

    # Обновляем статус и сохраняем геолокацию
    sos_request["status"] = "sos_active"
    sos_request["latitude"] = location["latitude"]
    sos_request["longitude"] = location["longitude"]
    save_db(db)

    # Отправляем SOS со всеми волонтёрам с геолокацией
    volunteers_notified = 0
    for user_chat_id, user_data in db["users"].items():
        if user_data.get("role") == "volunteer":
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

    # Переносим запрос в завершённые
    db["active_requests"].remove(sos_request)
    db["completed_requests"].append(sos_request)
    save_db(db)

    send_message(chat_id, f"✅ Сигнал SOS с вашим местоположением отправлен {volunteers_notified} волонтёрам!")

def handle_switch_role(chat_id, username, user_id=None):
    """Переключение роли пользователя для тестирования"""
    user = get_user(chat_id)

    if not user or not user.get("role"):
        send_message(chat_id, "Сначала используйте /start для регистрации")
        return

    # Переключаем роль
    new_role = "volunteer" if user["role"] == "needy" else "needy"
    save_user(chat_id, new_role, username, user_id)

    if new_role == "volunteer":
        send_message(chat_id, "🔄 Роль изменена на: Волонтёр\n\nВы будете получать запросы от нуждающихся.")
    else:
        send_message(chat_id, "🔄 Роль изменена на: Нуждающийся\n\nВам доступно меню функций.")
        show_needy_menu(chat_id)

# === Обработка callback'ов ===

def handle_callback(callback_id, payload, chat_id, username, user_id=None, message_id=None):
    """Обработка нажатий на кнопки"""
    print(f"Callback: {payload} от {chat_id}", flush=True)

    if payload == "role_needy":
        # Получаем start_message_id если он был сохранён
        user = get_user(chat_id)
        start_message_id = user.get("start_message_id") if user else None
        handle_role_selection(chat_id, "needy", username, user_id, start_message_id)
        answer_callback(callback_id)

    elif payload == "role_volunteer":
        # Получаем start_message_id если он был сохранён
        user = get_user(chat_id)
        start_message_id = user.get("start_message_id") if user else None
        handle_role_selection(chat_id, "volunteer", username, user_id, start_message_id)
        answer_callback(callback_id)

    elif payload == "request_call":
        handle_request_call(chat_id, username, user_id, message_id)
        answer_callback(callback_id)

    elif payload.startswith("accept_request_"):
        request_id = payload.replace("accept_request_", "")
        handle_accept_request(chat_id, request_id, username, callback_id)
        answer_callback(callback_id)

    elif payload == "sos":
        handle_sos(chat_id, username, user_id)
        answer_callback(callback_id)

    elif payload in ["voice_to_text", "text_to_voice", "image_to_text"]:
        answer_callback(callback_id, "Эта функция скоро будет доступна!")

# === Главный цикл ===

def main():
    print("Запуск бота волонтёр-нуждающийся для Max...")

    # Создаём папку для загрузок, если её нет
    os.makedirs("downloads", exist_ok=True)

    # Получаем информацию о боте
    bot_info = get_bot_info()
    if bot_info:
        print(f"Бот запущен: {bot_info.get('name')} (@{bot_info.get('username')})")
    else:
        print("Не удалось получить информацию о боте. Проверьте токен.")
        return

    print("Ожидание сообщений...")

    marker = None
    error_count = 0
    max_errors = 5  # Максимум ошибок подряд перед перезапуском

    # Основной цикл обработки сообщений
    while True:
        try:
            response = get_updates(marker)

            # Сбрасываем счётчик ошибок при успешном запросе
            if response:
                error_count = 0

            if response:
                # Обновляем marker для следующего запроса
                if 'marker' in response:
                    marker = response['marker']

                # Обрабатываем обновления
                if 'updates' in response and response['updates']:
                    for update in response['updates']:
                        try:
                            update_type = update.get('update_type')

                            # Обрабатываем новые сообщения
                            if update_type == 'message_created':
                                message = update.get('message', {})
                                recipient = message.get('recipient', {})
                                body = message.get('body', {})
                                sender = message.get('sender', {})

                                chat_id = recipient.get('chat_id')
                                text = body.get('text', '')
                                message_id = body.get('mid')  # Получаем ID сообщения
                                # Пробуем получить username или name
                                username = sender.get('username') or sender.get('name')
                                user_id = sender.get('user_id')

                                # DEBUG: показываем что есть в sender
                                if text and text.startswith('/debug'):
                                    print(f"DEBUG sender: {sender}", flush=True)

                                # Проверяем наличие геолокации
                                attachments = body.get('attachments', [])
                                location = None
                                for attachment in attachments:
                                    if attachment.get('type') == 'location':
                                        location = {
                                            'latitude': attachment.get('latitude'),
                                            'longitude': attachment.get('longitude')
                                        }
                                        break

                                # Обрабатываем геолокацию для SOS
                                if chat_id and location:
                                    print(f"Получена геолокация из чата {chat_id}: {location['latitude']}, {location['longitude']}", flush=True)
                                    handle_sos_location(chat_id, username, user_id, location)

                                elif chat_id and text:
                                    print(f"Получено сообщение из чата {chat_id}: {text}", flush=True)

                                    # Обработка команд
                                    if text.strip().lower() in ['/start', 'start', 'старт']:
                                        # Сохраняем message_id команды /start для возможности пересылки
                                        if message_id:
                                            db = load_db()
                                            user = db["users"].get(str(chat_id), {})
                                            user["start_message_id"] = message_id
                                            db["users"][str(chat_id)] = user
                                            save_db(db)
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

                            # Обрабатываем callback'и (нажатия на кнопки)
                            elif update_type == 'message_callback':
                                callback = update.get('callback', {})
                                message = update.get('message', {})

                                callback_id = callback.get('callback_id')
                                payload = callback.get('payload')
                                user_info = callback.get('user', {})

                                chat_id = message.get('recipient', {}).get('chat_id')
                                message_id = message.get('body', {}).get('mid')  # Получаем ID сообщения
                                # Пробуем получить username или name
                                username = user_info.get('username') or user_info.get('name')
                                user_id = user_info.get('user_id')

                                if callback_id and payload and chat_id:
                                    handle_callback(callback_id, payload, chat_id, username, user_id, message_id)

                        except Exception as e:
                            print(f"⚠️  Ошибка при обработке обновления: {e}")
                            import traceback
                            traceback.print_exc()
                            # Продолжаем обработку следующих обновлений

            # Небольшая задержка перед следующим запросом
            time.sleep(1)

        except KeyboardInterrupt:
            print("\nБот остановлен")
            break
        except requests.exceptions.ConnectionError as e:
            error_count += 1
            print(f"⚠️  Ошибка соединения ({error_count}/{max_errors}): {e}")
            if error_count >= max_errors:
                print("❌ Слишком много ошибок соединения подряд. Перезапуск через 30 секунд...")
                time.sleep(30)
                error_count = 0
                marker = None  # Сбрасываем marker при перезапуске
            else:
                time.sleep(5)
        except requests.exceptions.Timeout as e:
            error_count += 1
            print(f"⚠️  Таймаут запроса ({error_count}/{max_errors}): {e}")
            if error_count >= max_errors:
                print("❌ Слишком много таймаутов подряд. Перезапуск через 30 секунд...")
                time.sleep(30)
                error_count = 0
                marker = None
            else:
                time.sleep(5)
        except json.JSONDecodeError as e:
            error_count += 1
            print(f"⚠️  Ошибка парсинга JSON ({error_count}/{max_errors}): {e}")
            time.sleep(3)
        except Exception as e:
            error_count += 1
            print(f"❌ Неожиданная ошибка ({error_count}/{max_errors}): {e}")
            import traceback
            traceback.print_exc()
            if error_count >= max_errors:
                print("❌ Слишком много ошибок подряд. Перезапуск через 30 секунд...")
                time.sleep(30)
                error_count = 0
                marker = None
            else:
                time.sleep(5)

if __name__ == "__main__":
    main()
