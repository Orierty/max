import requests
import time
import sys
import os
import json
import logging
from datetime import datetime
from dotenv import load_dotenv
from PIL import Image
from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
from qwen_vl_utils import process_vision_info
import torch

# Импортируем функции для работы с PostgreSQL
from database import (
    init_db_pool, close_db_pool,
    get_user, save_user,
    create_request, assign_volunteer_to_request, complete_request,
    get_request, get_active_requests,
    create_review, add_tags_to_user, get_volunteer_stats,
    get_all_users_by_role
)

# Загружаем переменные окружения из .env файла
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Получаем токен из переменных окружения
MAX_TOKEN = os.getenv("MAX_TOKEN")
if not MAX_TOKEN:
    logger.error("MAX_TOKEN не найден в переменных окружения!")
    logger.error("Создайте файл .env и добавьте туда MAX_TOKEN=ваш_токен")
    sys.exit(1)

# Параметр включения/выключения нейронки
VISION_MODEL_ENABLED = os.getenv("VISION_MODEL_ENABLED", "false").lower() == "true"
logger.info(f"Vision Model: {'ENABLED' if VISION_MODEL_ENABLED else 'DISABLED (using stubs)'}")

BASE_URL = "https://platform-api.max.ru"

HEADERS = {
    "Authorization": MAX_TOKEN,
    "Content-Type": "application/json"
}

# Глобальные переменные для модели Qwen2-VL
vision_model = None
vision_processor = None

def init_vision_model():
    """Инициализирует модель Qwen2-VL для распознавания изображений"""
    global vision_model, vision_processor

    try:
        # Путь к папке с моделями в рабочей директории
        models_dir = os.path.join(os.path.dirname(__file__), "models")
        os.makedirs(models_dir, exist_ok=True)


        # Если auto-gptq не установлен, используем обычную модель
        model_name = "Qwen/Qwen2-VL-2B-Instruct"
        local_model_path = os.path.join(models_dir, "Qwen2-VL-2B-Instruct")
        logger.info("auto-gptq не установлен, используем стандартную модель Qwen2-VL-2B-Instruct...")
        logger.warning("Для экономии памяти рекомендуется установить: pip install auto-gptq")

        # Проверяем, есть ли уже локальная модель
        if os.path.exists(local_model_path) and os.path.isdir(local_model_path):
            logger.info(f"Используем локальную модель из {local_model_path}")
            model_source = local_model_path
        else:
            logger.info(f"Модель будет скачана из HuggingFace и сохранена в {local_model_path}")
            model_source = model_name

        # Загружаем процессор
        vision_processor = AutoProcessor.from_pretrained(
            model_source,
            trust_remote_code=True,
            cache_dir=models_dir if model_source == model_name else None
        )

        # Загружаем модель
        # Используем float16 если доступна GPU, иначе float32 для CPU
        dtype = torch.float16 if torch.cuda.is_available() else torch.float32

        vision_model = Qwen2VLForConditionalGeneration.from_pretrained(
            model_source,
            torch_dtype=dtype,
            device_map="auto",
            trust_remote_code=True,
            cache_dir=models_dir if model_source == model_name else None
        )

        # Сохраняем модель локально, если она была скачана из HuggingFace
        if model_source == model_name:
            logger.info(f"Сохраняем модель локально в {local_model_path}...")
            vision_model.save_pretrained(local_model_path)
            vision_processor.save_pretrained(local_model_path)
            logger.info("Модель успешно сохранена локально")

        device = next(vision_model.parameters()).device
        logger.info(f"Модель Qwen2-VL успешно загружена на устройство: {device}")
        return True

    except Exception as e:
        logger.error(f"Ошибка при загрузке модели Qwen2-VL: {e}", exc_info=True)
        return False

def describe_image(image_path):
    """Описывает изображение на русском языке с помощью Qwen2-VL"""
    global vision_model, vision_processor

    # Если нейронка выключена, возвращаем заглушку
    if not VISION_MODEL_ENABLED:
        logger.info("Vision Model отключена")
        return ("Режим заглушки)\n\n"
                "На изображении видно: [здесь было бы описание от нейронки]\n\n"
                "Для включения нейронки установите VISION_MODEL_ENABLED=true в файле .env")

    # Если модель ещё не загружена, загружаем её
    if vision_model is None or vision_processor is None:
        logger.info("Модель не загружена, инициализируем...")
        if not init_vision_model():
            return "Ошибка: не удалось загрузить модель для распознавания изображений."

    try:
        # Открываем изображение
        image = Image.open(image_path).convert('RGB')

        # Формируем запрос на русском языке
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "image": image_path,
                    },
                    {
                        "type": "text",
                        "text": "Опиши подробно что изображено на этой фотографии на русском языке. Будь максимально детальным и точным в описании."
                    },
                ],
            }
        ]

        # Подготавливаем текст для модели
        text = vision_processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )

        # Обрабатываем изображения
        image_inputs, video_inputs = process_vision_info(messages)

        # Подготавливаем входные данные
        inputs = vision_processor(
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        )
        inputs = inputs.to(vision_model.device)

        # Генерируем описание
        logger.info("Генерация описания изображения...")
        with torch.no_grad():
            generated_ids = vision_model.generate(
                **inputs,
                max_new_tokens=512,
                temperature=0.7,
                do_sample=True
            )

        # Обрезаем входную часть и декодируем
        generated_ids_trimmed = [
            out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        output_text = vision_processor.batch_decode(
            generated_ids_trimmed,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False
        )[0]

        logger.info(f"Описание сгенерировано: {output_text[:100]}...")
        return output_text

    except Exception as e:
        logger.error(f"Ошибка при обработке изображения: {e}", exc_info=True)
        return f"Ошибка при обработке изображения: {str(e)}"

def download_image(url, save_path):
    """Скачивает изображение по URL"""
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            with open(save_path, 'wb') as f:
                f.write(response.content)
            logger.info(f"Изображение скачано: {save_path}")
            return True
        else:
            logger.error(f"Ошибка скачивания изображения: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"Ошибка при скачивании изображения: {e}")
        return False

# === Все функции для работы с БД теперь импортируются из database.py ===
# Эти функции используют PostgreSQL вместо JSON

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

    logger.debug(f"DEBUG forward: chat_id={chat_id}, message_id={message_id}, text={text}")
    logger.debug(f"DEBUG forward data: {data}")

    response = requests.post(f"{BASE_URL}/messages", headers=HEADERS, params=params, json=data)

    if response.status_code == 200:
        logger.info(f"Сообщение переслано в чат {chat_id}")
        return response.json()
    else:
        logger.error(f"Ошибка пересылки сообщения: {response.status_code}, {response.text}")
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
        logger.info("Ответ на callback отправлен")
        return response.json()
    else:
        logger.error(f"Ошибка ответа на callback: {response.status_code}, {response.text}")
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
    # Изменяем текст кнопки в зависимости от статуса нейронки
    image_button_text = "Изображение → Текст"
    if not VISION_MODEL_ENABLED:
        image_button_text += " (заглушка)"

    buttons = [
        [{"type": "callback", "text": "Запросить звонок волонтёра", "payload": "request_call"}],
        [{"type": "callback", "text": "Голосовое → Текст (скоро)", "payload": "voice_to_text"}],
        [{"type": "callback", "text": "Текст → Голосовое (скоро)", "payload": "text_to_voice"}],
        [{"type": "callback", "text": image_button_text, "payload": "image_to_text"}],
        [{"type": "callback", "text": "SOS", "payload": "sos"}]
    ]

    menu_text = "Выберите функцию:"
    if not VISION_MODEL_ENABLED:
        menu_text += "\n\n⚠️ Vision Model работает в режиме заглушек"

    send_message_with_keyboard(
        chat_id,
        menu_text,
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
    # Создаём запрос в PostgreSQL
    request_id = create_request(chat_id, urgency="normal")

    # Получаем теги пользователя для отображения волонтёрам
    user = get_user(chat_id)
    tags_text = ""
    if user and user.get("tags"):
        tags_text = f"\nТеги: {', '.join(user['tags'])}"

    # Получаем всех волонтёров из PostgreSQL
    volunteers = get_all_users_by_role("volunteer")

    # Отправляем запрос всем волонтёрам
    volunteers_notified = 0
    for user_chat_id, user_data in volunteers.items():
        buttons = [
            [{"type": "callback", "text": "✅ Принять запрос", "payload": f"accept_request_{request_id}"}]
        ]
        send_message_with_keyboard(
            user_chat_id,
            f"🆘 Новый запрос на звонок!\n\nОт: @{username or 'неизвестно'}\nВремя: {datetime.now().strftime('%H:%M')}{tags_text}",
            buttons
        )
        volunteers_notified += 1

    if volunteers_notified > 0:
        send_message(chat_id, f"✅ Ваш запрос отправлен {volunteers_notified} волонтёрам. Ожидайте ответа...")
    else:
        send_message(chat_id, "⚠️ К сожалению, сейчас нет доступных волонтёров. Попробуйте позже.")

def handle_accept_request(volunteer_chat_id, request_id, volunteer_username, callback_id=None):
    """Обработка принятия запроса волонтёром"""
    # Получаем запрос из PostgreSQL
    request = get_request(request_id)

    if not request or request["status"] != "pending":
        if callback_id:
            answer_callback(callback_id, "Этот запрос уже принят другим волонтёром")
        return

    # Обновляем статус запроса в PostgreSQL
    assign_volunteer_to_request(request_id, volunteer_chat_id)

    # Уведомляем волонтёра с кнопкой завершения диалога
    buttons = [
        [{"type": "callback", "text": "✅ Завершить диалог", "payload": f"complete_request_{request_id}"}]
    ]

    # Получаем статистику волонтёра
    stats = get_volunteer_stats(volunteer_chat_id)
    stats_text = ""
    if stats:
        stats_text = f"\n\n📊 Ваша статистика:\nРейтинг: {stats['rating']:.1f} ⭐\nВсего звонков: {stats['call_count']}"

    send_message_with_keyboard(
        volunteer_chat_id,
        f"✅ Вы приняли запрос!{stats_text}\n\nПосле завершения диалога нажмите кнопку ниже.",
        buttons
    )

    # Уведомляем нуждающегося с mention волонтёра
    volunteer = get_user(volunteer_chat_id)
    volunteer_user_id = volunteer.get("id") if volunteer else None

    # Получаем user_id нуждающегося
    needy_user_id = request.get("user_id")

    text, markup = create_user_mention(
        "✅ Волонтёр {mention} принял ваш запрос и скоро свяжется с вами!",
        username=volunteer_username,
        user_id=volunteer_user_id
    )
    send_message(needy_user_id, text, markup=markup)

def handle_complete_request(volunteer_chat_id, request_id):
    """Обработка завершения диалога волонтёром"""
    # Завершаем запрос
    complete_request(request_id)

    # Получаем информацию о запросе
    request = get_request(request_id)
    if not request:
        send_message(volunteer_chat_id, "❌ Запрос не найден")
        return

    needy_user_id = request.get("user_id")
    if not needy_user_id:
        send_message(volunteer_chat_id, "❌ Не удалось найти пользователя")
        return

    # Предлагаем волонтёру добавить теги о нуждающемся
    buttons = [
        [{"type": "callback", "text": "👵 Бабушка/Дедушка", "payload": f"add_tag_{request_id}_elderly"}],
        [{"type": "callback", "text": "👁️ Незрячий", "payload": f"add_tag_{request_id}_blind"}],
        [{"type": "callback", "text": "📷 Плохая камера", "payload": f"add_tag_{request_id}_bad_camera"}],
        [{"type": "callback", "text": "🎤 Плохой микрофон", "payload": f"add_tag_{request_id}_bad_mic"}],
        [{"type": "callback", "text": "🦻 Плохо слышит", "payload": f"add_tag_{request_id}_hearing"}],
        [{"type": "callback", "text": "✅ Пропустить", "payload": f"skip_tags_{request_id}"}]
    ]

    send_message_with_keyboard(
        volunteer_chat_id,
        "✅ Диалог завершён!\n\nЕсли хотите, добавьте теги о пользователе (это поможет другим волонтёрам):",
        buttons
    )

    # Отправляем запрос на оценку нуждающемуся
    buttons_rating = [
        [
            {"type": "callback", "text": "⭐", "payload": f"rate_volunteer_{request_id}_1"},
            {"type": "callback", "text": "⭐⭐", "payload": f"rate_volunteer_{request_id}_2"},
            {"type": "callback", "text": "⭐⭐⭐", "payload": f"rate_volunteer_{request_id}_3"}
        ],
        [
            {"type": "callback", "text": "⭐⭐⭐⭐", "payload": f"rate_volunteer_{request_id}_4"},
            {"type": "callback", "text": "⭐⭐⭐⭐⭐", "payload": f"rate_volunteer_{request_id}_5"}
        ]
    ]

    send_message_with_keyboard(
        needy_user_id,
        "✅ Диалог с волонтёром завершён!\n\nПожалуйста, оцените работу волонтёра:",
        buttons_rating
    )

def handle_add_tag(volunteer_chat_id, request_id, tag):
    """Обработка добавления тега к нуждающемуся"""
    request = get_request(request_id)
    if not request:
        send_message(volunteer_chat_id, "❌ Запрос не найден")
        return

    needy_user_id = request.get("user_id")

    # Словарь тегов
    tag_names = {
        "elderly": "Бабушка/Дедушка",
        "blind": "Незрячий",
        "bad_camera": "Плохая камера",
        "bad_mic": "Плохой микрофон",
        "hearing": "Плохо слышит"
    }

    tag_name = tag_names.get(tag, tag)
    add_tags_to_user(needy_user_id, [tag_name])

    send_message(volunteer_chat_id, f"✅ Тег '{tag_name}' добавлен!")

    # Показываем снова меню с тегами, но убираем добавленный тег
    buttons = []
    for tag_key, tag_label in tag_names.items():
        if tag_key != tag:
            buttons.append([{"type": "callback", "text": f"{tag_label}", "payload": f"add_tag_{request_id}_{tag_key}"}])

    buttons.append([{"type": "callback", "text": "✅ Готово", "payload": f"skip_tags_{request_id}"}])

    send_message_with_keyboard(
        volunteer_chat_id,
        "Хотите добавить ещё теги?",
        buttons
    )

def handle_skip_tags(volunteer_chat_id, request_id):
    """Обработка пропуска добавления тегов"""
    send_message(volunteer_chat_id, "✅ Спасибо за помощь!\n\nВозвращайтесь, когда будете готовы помочь ещё.")

def handle_rate_volunteer(needy_chat_id, request_id, rating):
    """Обработка оценки волонтёра нуждающимся"""
    # Создаём отзыв
    review_id = create_review(request_id, rating, "")

    if review_id:
        # Предлагаем оставить комментарий (опционально)
        send_message(needy_chat_id, f"✅ Спасибо за оценку ({rating} ⭐)!\n\nЕсли хотите, можете написать комментарий волонтёру (просто отправьте сообщение).\n\nИли выберите функцию из меню:")
        show_needy_menu(needy_chat_id)

        # Уведомляем волонтёра о полученном рейтинге
        request = get_request(request_id)
        if request and request.get("assigned_volunteer_id"):
            volunteer_id = request["assigned_volunteer_id"]
            stats = get_volunteer_stats(volunteer_id)

            stats_text = ""
            if stats:
                stats_text = f"\n\n📊 Ваша статистика:\nРейтинг: {stats['rating']:.1f} ⭐\nВсего звонков: {stats['call_count']}"

            send_message(volunteer_id, f"⭐ Вы получили оценку {rating} звёзд!{stats_text}")
    else:
        send_message(needy_chat_id, "❌ Не удалось сохранить оценку. Попробуйте позже.")

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

def handle_image_to_text_request(chat_id):
    """Обработка запроса на распознавание изображения"""
    db = load_db()

    # Создаём запрос на ожидание фото
    request_id = str(int(time.time()))
    image_request = {
        "id": request_id,
        "chat_id": str(chat_id),
        "created_at": datetime.now().isoformat(),
        "status": "waiting_for_image",
        "type": "image_to_text"
    }

    db["active_requests"].append(image_request)
    save_db(db)

    send_message(chat_id, "📷 Отправьте мне фотографию, и я опишу что на ней изображено.\n\nПросто прикрепите фото к следующему сообщению.")

def handle_image_processing(chat_id, image_url):
    """Обработка полученного изображения"""
    db = load_db()

    # Проверяем, есть ли активный запрос на распознавание от этого пользователя
    image_request = None
    for req in db["active_requests"]:
        if (req.get("type") == "image_to_text" and
            req.get("chat_id") == str(chat_id) and
            req.get("status") == "waiting_for_image"):
            image_request = req
            break

    if not image_request:
        # Если запроса нет, всё равно обрабатываем (для удобства)
        logger.info(f"Нет активного запроса на распознавание, но обрабатываем фото от {chat_id}")

    try:
        # Отправляем сообщение о начале обработки
        send_message(chat_id, "⏳ Обрабатываю изображение, подождите немного...")

        # Скачиваем изображение
        image_filename = f"image_{chat_id}_{int(time.time())}.jpg"
        image_path = os.path.join("downloads", image_filename)

        if not download_image(image_url, image_path):
            send_message(chat_id, "❌ Ошибка при скачивании изображения. Попробуйте ещё раз.")
            return

        # Распознаём изображение
        description = describe_image(image_path)

        # Отправляем результат
        send_message(chat_id, f"📝 Описание изображения:\n\n{description}")

        # Удаляем запрос из активных
        if image_request:
            db["active_requests"] = [r for r in db["active_requests"] if r["id"] != image_request["id"]]
            image_request["status"] = "completed"
            image_request["completed_at"] = datetime.now().isoformat()
            db["completed_requests"].append(image_request)
            save_db(db)

        # Удаляем временный файл изображения
        try:
            os.remove(image_path)
            logger.info(f"Временный файл {image_path} удалён")
        except:
            pass

    except Exception as e:
        logger.error(f"Ошибка при обработке изображения: {e}", exc_info=True)
        send_message(chat_id, f"❌ Произошла ошибка при обработке изображения: {str(e)}")

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
    logger.info(f"Callback: {payload} от {chat_id}")

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

    elif payload == "sos":
        handle_sos(chat_id, username, user_id)
        answer_callback(callback_id)

    elif payload == "image_to_text":
        handle_image_to_text_request(chat_id)
        answer_callback(callback_id)

    elif payload in ["voice_to_text", "text_to_voice"]:
        answer_callback(callback_id, "Эта функция скоро будет доступна!")

# === Главный цикл ===

def main():
    logger.info("Запуск бота волонтёр-нуждающийся для Max...")

    # Инициализируем подключение к PostgreSQL
    if not init_db_pool():
        logger.error("Не удалось подключиться к PostgreSQL. Проверьте настройки в .env")
        return

    # Создаём папку для загрузок, если её нет
    os.makedirs("downloads", exist_ok=True)

    # Получаем информацию о боте
    bot_info = get_bot_info()
    if bot_info:
        logger.info(f"Бот запущен: {bot_info.get('name')} (@{bot_info.get('username')})")
    else:
        logger.error("Не удалось получить информацию о боте. Проверьте токен.")
        close_db_pool()
        return

    logger.info("Ожидание сообщений...")

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
                                    logger.debug(f"DEBUG sender: {sender}")

                                # Проверяем наличие вложений (геолокация, изображения и т.д.)
                                attachments = body.get('attachments', [])
                                location = None
                                image_url = None

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

                                # Обрабатываем геолокацию для SOS
                                if chat_id and location:
                                    logger.info(f"Получена геолокация из чата {chat_id}: {location['latitude']}, {location['longitude']}")
                                    handle_sos_location(chat_id, username, user_id, location)

                                # Обрабатываем изображения
                                elif chat_id and image_url:
                                    logger.info(f"Получено изображение из чата {chat_id}: {image_url}")
                                    handle_image_processing(chat_id, image_url)

                                elif chat_id and text:
                                    logger.info(f"Получено сообщение из чата {chat_id}: {text}")

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
                            logger.error(f"Ошибка при обработке обновления: {e}", exc_info=True)
                            # Продолжаем обработку следующих обновлений

            # Небольшая задержка перед следующим запросом
            time.sleep(1)

        except KeyboardInterrupt:
            logger.info("Бот остановлен")
            break
        except requests.exceptions.ConnectionError as e:
            error_count += 1
            logger.warning(f"Ошибка соединения ({error_count}/{max_errors}): {e}")
            if error_count >= max_errors:
                logger.error("Слишком много ошибок соединения подряд. Перезапуск через 30 секунд...")
                time.sleep(30)
                error_count = 0
                marker = None  # Сбрасываем marker при перезапуске
            else:
                time.sleep(5)
        except requests.exceptions.Timeout as e:
            error_count += 1
            logger.warning(f"Таймаут запроса ({error_count}/{max_errors}): {e}")
            if error_count >= max_errors:
                logger.error("Слишком много таймаутов подряд. Перезапуск через 30 секунд...")
                time.sleep(30)
                error_count = 0
                marker = None
            else:
                time.sleep(5)
        except json.JSONDecodeError as e:
            error_count += 1
            logger.warning(f"Ошибка парсинга JSON ({error_count}/{max_errors}): {e}")
            time.sleep(3)
        except Exception as e:
            error_count += 1
            logger.error(f"Неожиданная ошибка ({error_count}/{max_errors}): {e}", exc_info=True)
            if error_count >= max_errors:
                logger.error("Слишком много ошибок подряд. Перезапуск через 30 секунд...")
                time.sleep(30)
                error_count = 0
                marker = None
            else:
                time.sleep(5)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    finally:
        close_db_pool()
        logger.info("Завершение работы бота")
