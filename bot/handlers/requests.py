"""
Обработчики запросов на звонки от волонтёров
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

import requests
from database import (
    get_user,
    create_request,
    get_request,
    assign_volunteer_to_request,
    complete_request,
    get_all_users_by_role,
    get_volunteer_stats,
    create_review,
    add_tags_to_user,
    get_volunteer_info,
    create_complaint,
    log_action,
)
from bot.utils import send_message, send_message_with_keyboard
from bot.config import MAX_TOKEN

logger = logging.getLogger(__name__)

# ID чата поддержки (будет установлен автоматически)
SUPPORT_CHAT_ID = None

# Кэш для хранения активных запросов
active_requests = {}
# Словарь для хранения состояний жалоб
complaint_states = {}


def get_all_chats() -> Optional[List[Dict]]:
    """Получает список всех чатов, где есть бот"""
    try:
        response = requests.get(
            f"https://platform-api.max.ru/chats?access_token={MAX_TOKEN}&count=100"
        )

        if response.status_code == 200:
            data = response.json()
            chats = data.get("chats", [])
            logger.info(f"Получено {len(chats)} чатов")
            return chats
        else:
            logger.error(f"Ошибка при получении списка чатов: {response.text}")
            return None

    except Exception as e:
        logger.error(f"Ошибка при получении списка чатов: {e}")
        return None


def find_support_chat() -> Optional[int]:
    """Находит чат поддержки по названию или создает новый"""
    chats = get_all_chats()

    if not chats:
        logger.error("Не удалось получить список чатов")
        return None

    # Ищем чат с определенным названием (например, "Поддержка" или "Support")
    support_keywords = ["поддержка", "support", "помощь", "help", "чат поддержки"]

    for chat in chats:
        title = chat.get("title", "").lower()
        if any(keyword in title for keyword in support_keywords):
            chat_id = chat.get("chat_id")
            logger.info(f"Найден чат поддержки: {title} (ID: {chat_id})")
            return chat_id

    # Если не нашли подходящий чат, используем первый доступный
    if chats:
        first_chat = chats[0]
        chat_id = first_chat.get("chat_id")
        title = first_chat.get("title", "Без названия")
        logger.info(f"Используем чат: {title} (ID: {chat_id})")
        return chat_id

    logger.error("Не найдено ни одного чата с ботом")
    return None


def initialize_support_chat():
    """Инициализирует ID чата поддержки при запуске бота"""
    global SUPPORT_CHAT_ID
    SUPPORT_CHAT_ID = find_support_chat()

    if SUPPORT_CHAT_ID:
        logger.info(f"Чат поддержки инициализирован: ID={SUPPORT_CHAT_ID}")
    else:
        logger.error("Не удалось инициализировать чат поддержки")


def get_support_chat_id() -> int:
    """Возвращает ID чата поддержки, инициализируя его при необходимости"""
    global SUPPORT_CHAT_ID
    if SUPPORT_CHAT_ID is None:
        initialize_support_chat()
    return SUPPORT_CHAT_ID


def add_users_to_chat(user_ids: List[int]) -> bool:
    """Добавляет пользователей в чат поддержки"""
    chat_id = get_support_chat_id()
    if not chat_id:
        logger.error("Не удалось получить ID чата поддержки")
        return False

    try:
        payload = {"user_ids": user_ids}

        response = requests.post(
            f"https://platform-api.max.ru/chats/{chat_id}/members?access_token={MAX_TOKEN}",
            json=payload,
        )

        if response.status_code == 200:
            logger.info(f"Пользователи {user_ids} добавлены в чат {chat_id}")
            return True
        else:
            logger.error(f"Ошибка при добавлении пользователей: {response.text}")
            return False

    except Exception as e:
        logger.error(f"Ошибка при добавлении пользователей в чат {chat_id}: {e}")
        return False


def remove_user_from_chat(user_id: int) -> bool:
    """Удаляет пользователя из чата поддержки"""
    chat_id = get_support_chat_id()
    if not chat_id:
        logger.error("Не удалось получить ID чата поддержки")
        return False

    try:
        response = requests.delete(
            f"https://platform-api.max.ru/chats/{chat_id}/members?access_token={MAX_TOKEN}&user_id={user_id}"
        )

        if response.status_code == 200:
            logger.info(f"Пользователь {user_id} удален из чата {chat_id}")
            return True
        else:
            logger.error(f"Ошибка при удалении пользователя: {response.text}")
            return False

    except Exception as e:
        logger.error(
            f"Ошибка при удалении пользователя {user_id} из чата {chat_id}: {e}"
        )
        return False


def send_message_to_chat(text: str, attachments: List[Dict] = None):
    """Отправляет сообщение в чат поддержки"""
    chat_id = get_support_chat_id()
    if not chat_id:
        logger.error("Не удалось получить ID чата поддержки")
        return False

    try:
        message_data = {"chat_id": chat_id, "text": text}

        if attachments:
            message_data["attachments"] = attachments

        response = requests.post(
            f"https://platform-api.max.ru/messages?access_token={MAX_TOKEN}",
            json=message_data,
        )

        if response.status_code == 200:
            logger.info(f"Сообщение отправлено в чат {chat_id}")
            return True
        else:
            logger.error(f"Ошибка при отправке сообщения: {response.text}")
            return False

    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения в чат {chat_id}: {e}")
        return False


def handle_chat_selection(chat_id: int):
    """Позволяет администратору выбрать чат для поддержки"""
    global SUPPORT_CHAT_ID

    # Проверяем, что чат существует и бот в нем
    chats = get_all_chats()
    if chats:
        for chat in chats:
            if chat.get("chat_id") == chat_id:
                SUPPORT_CHAT_ID = chat_id
                title = chat.get("title", "Без названия")
                logger.info(f"Выбран чат поддержки: {title} (ID: {chat_id})")

                # Уведомляем администратора
                send_message(
                    chat_id,
                    f"✅ Этот чат установлен как основной для поддержки!\n\n"
                    f"Название: {title}\n"
                    f"ID: {chat_id}",
                )
                return True

    logger.error(f"Чат с ID {chat_id} не найден или бот не является участником")
    return False


def show_available_chats(admin_chat_id: int):
    """Показывает администратору список доступных чатов"""
    chats = get_all_chats()

    if not chats:
        send_message(admin_chat_id, "❌ Бот не участвует ни в одном чате")
        return

    message = "📋 Доступные чаты:\n\n"
    buttons = []

    for i, chat in enumerate(chats[:10]):  # Ограничиваем 10 чатами
        chat_id = chat.get("chat_id")
        title = chat.get("title", "Без названия")
        participants_count = chat.get("participants_count", 0)

        message += f"{i+1}. {title}\n"
        message += f"   👥 Участников: {participants_count}\n"
        message += f"   🆔 ID: {chat_id}\n\n"

        buttons.append(
            [
                {
                    "type": "callback",
                    "text": f"✅ Выбрать '{title[:20]}...'",
                    "payload": f"select_chat_{chat_id}",
                }
            ]
        )

    send_message_with_keyboard(admin_chat_id, message, buttons)


def handle_request_call(chat_id, username, user_id, message_id=None):
    """Обработка запроса на звонок от пользователя"""
    if get_support_chat_id() is None:
        send_message(
            chat_id, "❌ Система поддержки временно недоступна. Попробуйте позже."
        )
        return

    # Создаём запрос, теперь с user_id
    request_id = create_request(user_id=user_id, urgency="normal")

    # Получаем теги пользователя
    user = get_user(user_id)
    tags_text = ""
    if user and user.get("tags"):
        tags_text = f"\nТеги: {', '.join(user['tags'])}"

    # Получаем всех волонтёров
    volunteers = get_all_users_by_role("volunteer")

    volunteers_notified = 0
    for volunteer_chat_id, user_data in volunteers.items():
        buttons = [
            [
                {
                    "type": "callback",
                    "text": "✅ Принять запрос",
                    "payload": f"accept_request_{request_id}",
                }
            ]
        ]
        send_message_with_keyboard(
            volunteer_chat_id,
            f"🆘 Новый запрос на звонок!\n\nОт: @{username or 'неизвестно'}\nВремя: {datetime.now().strftime('%H:%M')}{tags_text}",
            buttons,
        )
        volunteers_notified += 1

    if volunteers_notified > 0:
        send_message(
            chat_id,
            f"✅ Ваш запрос отправлен {volunteers_notified} волонтёрам. Ожидайте ответа...",
        )
    else:
        send_message(
            chat_id, "⚠️ К сожалению, сейчас нет доступных волонтёров. Попробуйте позже."
        )


def handle_accept_request(
    volunteer_chat_id, request_id, volunteer_username, user_id, callback_id=None
):
    """Обработка принятия запроса волонтёром"""
    # Проверяем, что чат поддержки инициализирован
    if get_support_chat_id() is None:
        send_message(
            volunteer_chat_id,
            "❌ Система поддержки временно недоступна. Попробуйте позже.",
        )
        return False

    # Проверяем статус верификации волонтера
    volunteer_info = get_volunteer_info(volunteer_chat_id)
    if not volunteer_info:
        send_message(volunteer_chat_id, "❌ Ошибка загрузки данных волонтёра.")
        return False
    if volunteer_info.get("is_blocked", False):
        send_message(
            volunteer_chat_id, "🚫 Вы заблокированы и не можете принимать запросы."
        )
        return False

    # Получаем запрос из PostgreSQL
    # request = get_request(request_id)
    # if not request or request["status"] != "pending":
    #     send_message(volunteer_chat_id, "❌ Запрос не найден или уже обработан.")
    #     return False

    # Сохраняем информацию о запросе
    active_requests[request_id] = {
        "volunteer_id": user_id,
        "needy_id": user_id,
        "status": "accepted",
    }

    # Логируем действие
    log_action(volunteer_chat_id, "accept_request", "request", request_id)

    # Обновляем статус запроса в PostgreSQL
    assign_volunteer_to_request(request_id, volunteer_chat_id)

    print(volunteer_chat_id, user_id)
    # Добавляем обоих пользователей в общий чат поддержки
    if add_users_to_chat([volunteer_chat_id, user_id]):
        # Уведомляем в чате о начале сессии поддержки
        session_message = f"🎯 Начата сессия поддержки #{request_id}\n\n👤 Нуждающийся: {user_id}\n🦸 Волонтёр: {volunteer_username or 'Аноним'}"
        send_message_to_chat(session_message)

        # Уведомляем волонтёра
        message_text = f"✅ Вы приняли запрос #{request_id}!\n\nВы добавлены в чат поддержки с пользователем."
        stats = get_volunteer_stats(volunteer_chat_id)
        if stats:
            message_text += f"\n\n📊 Ваша статистика:\nРейтинг: {stats['rating']:.1f} ⭐\nВсего звонков: {stats['call_count']}"
        send_message(volunteer_chat_id, message_text)

        # Кнопка завершения диалога
        complete_buttons = [
            [
                {
                    "type": "callback",
                    "text": "✅ Завершить диалог",
                    "payload": f"complete_request_{request_id}",
                }
            ]
        ]
        send_message_with_keyboard(
            volunteer_chat_id,
            "После завершения общения нажмите кнопку ниже:",
            complete_buttons,
        )

        # Уведомляем нуждающегося
        display_name = volunteer_username or "волонтёр"
        send_message(
            user_id,
            f"✅ Волонтёр {display_name} принял ваш запрос! Вы добавлены в чат поддержки.",
        )

        return True
    else:
        send_message(volunteer_chat_id, "❌ Ошибка при добавлении в чат поддержки.")
        return False


def handle_complete_request(volunteer_chat_id, request_id):
    """Обработка завершения диалога волонтёром"""
    # Проверяем, что чат поддержки инициализирован
    if get_support_chat_id() is None:
        send_message(volunteer_chat_id, "❌ Система поддержки временно недоступна.")
        return

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

    # Удаляем участников из чата
    success1 = remove_user_from_chat(volunteer_chat_id)
    success2 = remove_user_from_chat(needy_user_id)

    if success1 and success2:
        # Уведомляем в чате о завершении сессии
        completion_message = f"✅ Сессия поддержки #{request_id} завершена\n\n👤 Нуждающийся: {needy_user_id}\n🦸 Волонтер: {volunteer_chat_id}"
        send_message_to_chat(completion_message)

        send_message(volunteer_chat_id, "🔚 Вы покинули чат поддержки.")
        send_message(needy_user_id, "🔚 Чат поддержки завершен.")
    else:
        send_message(
            volunteer_chat_id,
            "⚠️ Диалог завершен, но возникли проблемы с выходом из чата.",
        )

    # Удаляем запись о запросе
    if request_id in active_requests:
        del active_requests[request_id]

    # Предлагаем волонтёру добавить теги о нуждающемся
    show_tag_selection(volunteer_chat_id, request_id)

    # Отправляем запрос на оценку нуждающемуся
    show_rating_selection(needy_user_id, request_id)


def show_tag_selection(volunteer_chat_id, request_id):
    """Показывает меню выбора тегов"""
    buttons = [
        [
            {
                "type": "callback",
                "text": "👵 Бабушка/Дедушка",
                "payload": f"add_tag_{request_id}_elderly",
            }
        ],
        [
            {
                "type": "callback",
                "text": "👁️ Незрячий",
                "payload": f"add_tag_{request_id}_blind",
            }
        ],
        [
            {
                "type": "callback",
                "text": "📷 Плохая камера",
                "payload": f"add_tag_{request_id}_bad_camera",
            }
        ],
        [
            {
                "type": "callback",
                "text": "🎤 Плохой микрофон",
                "payload": f"add_tag_{request_id}_bad_mic",
            }
        ],
        [
            {
                "type": "callback",
                "text": "🦻 Плохо слышит",
                "payload": f"add_tag_{request_id}_hearing",
            }
        ],
        [
            {
                "type": "callback",
                "text": "✅ Пропустить",
                "payload": f"skip_tags_{request_id}",
            }
        ],
    ]

    send_message_with_keyboard(
        volunteer_chat_id,
        "✅ Диалог завершён!\n\nЕсли хотите, добавьте теги о пользователе (это поможет другим волонтёрам):",
        buttons,
    )


def show_rating_selection(needy_user_id, request_id):
    """Показывает меню оценки волонтера"""
    buttons_rating = [
        [
            {
                "type": "callback",
                "text": "⭐",
                "payload": f"rate_volunteer_{request_id}_1",
            },
            {
                "type": "callback",
                "text": "⭐⭐",
                "payload": f"rate_volunteer_{request_id}_2",
            },
            {
                "type": "callback",
                "text": "⭐⭐⭐",
                "payload": f"rate_volunteer_{request_id}_3",
            },
        ],
        [
            {
                "type": "callback",
                "text": "⭐⭐⭐⭐",
                "payload": f"rate_volunteer_{request_id}_4",
            },
            {
                "type": "callback",
                "text": "⭐⭐⭐⭐⭐",
                "payload": f"rate_volunteer_{request_id}_5",
            },
        ],
    ]

    send_message_with_keyboard(
        needy_user_id,
        "✅ Диалог с волонтёром завершён!\n\nПожалуйста, оцените работу волонтёра:",
        buttons_rating,
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
        "hearing": "Плохо слышит",
    }

    tag_name = tag_names.get(tag, tag)
    add_tags_to_user(needy_user_id, [tag_name])

    send_message(volunteer_chat_id, f"✅ Тег '{tag_name}' добавлен!")

    # Показываем снова меню с тегами, но убираем добавленный тег
    buttons = []
    for tag_key, tag_label in tag_names.items():
        if tag_key != tag:
            buttons.append(
                [
                    {
                        "type": "callback",
                        "text": f"{tag_label}",
                        "payload": f"add_tag_{request_id}_{tag_key}",
                    }
                ]
            )

    buttons.append(
        [
            {
                "type": "callback",
                "text": "✅ Готово",
                "payload": f"skip_tags_{request_id}",
            }
        ]
    )

    send_message_with_keyboard(volunteer_chat_id, "Хотите добавить ещё теги?", buttons)


def handle_skip_tags(volunteer_chat_id, request_id):
    """Обработка пропуска добавления тегов"""
    send_message(
        volunteer_chat_id,
        "✅ Спасибо за помощь!\n\nВозвращайтесь, когда будете готовы помочь ещё.",
    )


def handle_rate_volunteer(needy_chat_id, request_id, rating):
    """Обработка оценки волонтёра нуждающимся"""
    # Создаём отзыв
    review_id = create_review(request_id, rating, "")

    if review_id:
        # Логируем действие
        log_action(
            needy_chat_id,
            "rate_volunteer",
            "review",
            review_id,
            details={"rating": rating},
        )

        # Добавляем кнопку жалобы если рейтинг низкий
        if rating <= 2:
            text = f"✅ Спасибо за оценку ({rating} ⭐)!\n\nЕсли у вас были проблемы с волонтером, вы можете пожаловаться модераторам."
            buttons = [
                [
                    {
                        "type": "callback",
                        "text": "⚠️ Пожаловаться на волонтера",
                        "payload": f"complaint_{request_id}",
                    }
                ],
                [{"type": "callback", "text": "🔙 В меню", "payload": "menu"}],
            ]
            send_message_with_keyboard(needy_chat_id, text, buttons)
        else:
            # Предлагаем оставить комментарий (опционально)
            send_message(
                needy_chat_id,
                f"✅ Спасибо за оценку ({rating} ⭐)!\n\nЕсли хотите, можете написать комментарий волонтёру (просто отправьте сообщение).\n\nИли выберите функцию из меню:",
            )
            from .menu import show_needy_menu

            show_needy_menu(needy_chat_id)

        # Уведомляем волонтёра о полученном рейтинге
        request = get_request(request_id)
        if request and request.get("assigned_volunteer_id"):
            volunteer_id = request["assigned_volunteer_id"]
            stats = get_volunteer_stats(volunteer_id)

            stats_text = ""
            if stats:
                stats_text = f"\n\n📊 Ваша статистика:\nРейтинг: {stats['rating']:.1f} ⭐\nВсего звонков: {stats['call_count']}"

            send_message(
                volunteer_id, f"⭐ Вы получили оценку {rating} звёзд!{stats_text}"
            )
    else:
        send_message(needy_chat_id, "❌ Не удалось сохранить оценку. Попробуйте позже.")


def handle_complaint(needy_chat_id, request_id):
    """Обработка жалобы на волонтера"""
    user = get_user(needy_chat_id)
    if not user or user["role"] != "needy":
        send_message(needy_chat_id, "Только нуждающиеся могут подавать жалобы.")
        return

    request = get_request(request_id)
    if not request:
        send_message(needy_chat_id, "❌ Запрос не найден.")
        return

    volunteer_id = request.get("assigned_volunteer_id")
    if not volunteer_id:
        send_message(needy_chat_id, "❌ Не удалось найти волонтера.")
        return

    text = """
⚠️ **Жалоба на волонтера**

Опишите причину жалобы в следующем сообщении.

Модераторы рассмотрят вашу жалобу и примут необходимые меры.
"""

    complaint_states[needy_chat_id] = {
        "request_id": request_id,
        "volunteer_id": volunteer_id,
    }

    send_message(needy_chat_id, text)


def handle_complaint_reason(needy_chat_id, reason):
    """Обработка причины жалобы"""
    if needy_chat_id not in complaint_states:
        return False

    state = complaint_states[needy_chat_id]
    request_id = state["request_id"]
    volunteer_id = state["volunteer_id"]

    # Создаем жалобу
    complaint_id = create_complaint(request_id, needy_chat_id, volunteer_id, reason)

    if complaint_id:
        # Логируем действие
        log_action(needy_chat_id, "create_complaint", "complaint", complaint_id)

        send_message(
            needy_chat_id,
            f"✅ Жалоба #{complaint_id} отправлена модераторам!\n\n"
            "Спасибо за обратную связь. Модераторы рассмотрят вашу жалобу.",
        )

        # Уведомляем модераторов
        moderators = get_all_users_by_role("moderator")

        notification_text = f"""
⚠️ **Новая жалоба #{complaint_id}**

На волонтера: {volunteer_id}
От нуждающегося: {needy_chat_id}
Заявка: #{request_id}

Причина: {reason}
"""

        for moderator_id in moderators:
            try:
                buttons = [
                    [
                        {
                            "type": "callback",
                            "text": "🛡️ Открыть панель модератора",
                            "payload": "moderator_menu",
                        }
                    ]
                ]
                send_message_with_keyboard(moderator_id, notification_text, buttons)
            except Exception as e:
                logger.error(
                    f"Ошибка отправки уведомления модератору {moderator_id}: {e}"
                )

        del complaint_states[needy_chat_id]
    else:
        send_message(needy_chat_id, "❌ Ошибка при отправке жалобы. Попробуйте позже.")
        del complaint_states[needy_chat_id]

    return True


def handle_webhook_update(update_data: Dict):
    """Обрабатывает входящие WebHook обновления"""
    update_type = update_data.get("update_type")

    if update_type == "message_callback":
        # Обрабатываем нажатия на кнопки
        callback_data = update_data.get("callback", {})
        payload = callback_data.get("payload", "")
        user_id = callback_data.get("user", {}).get("user_id")

        if payload.startswith("accept_request_"):
            request_id = int(payload.split("_")[2])
            username = callback_data.get("user", {}).get("username")
            handle_accept_request(user_id, request_id, username, user_id)
        elif payload.startswith("complete_request_"):
            request_id = int(payload.split("_")[2])
            handle_complete_request(user_id, request_id)
        elif payload.startswith("add_tag_"):
            # Обработка добавления тегов
            parts = payload.split("_")
            if len(parts) >= 4:
                request_id = int(parts[2])
                tag = parts[3]
                handle_add_tag(user_id, request_id, tag)
        elif payload.startswith("skip_tags_"):
            request_id = int(payload.split("_")[2])
            handle_skip_tags(user_id, request_id)
        elif payload.startswith("rate_volunteer_"):
            parts = payload.split("_")
            if len(parts) >= 4:
                request_id = int(parts[2])
                rating = int(parts[3])
                handle_rate_volunteer(user_id, request_id, rating)
        elif payload.startswith("complaint_"):
            request_id = int(payload.split("_")[1])
            handle_complaint(user_id, request_id)
        elif payload.startswith("select_chat_"):
            # Обработка выбора чата администратором
            chat_id = int(payload.split("_")[2])
            handle_chat_selection(chat_id)


# Инициализируем чат при импорте модуля
initialize_support_chat()
