"""
Обработчики запросов на звонки от волонтёров
"""
import logging
from datetime import datetime
from database import (
    get_user, create_request, get_request,
    assign_volunteer_to_request, complete_request,
    get_all_users_by_role, get_volunteer_stats,
    create_review, add_tags_to_user,
    get_volunteer_info, create_complaint, log_action
)
from bot.utils import send_message, send_message_with_keyboard, create_user_mention

logger = logging.getLogger(__name__)

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
    # Проверяем статус верификации волонтера
    volunteer_info = get_volunteer_info(volunteer_chat_id)

    if not volunteer_info:
        send_message(volunteer_chat_id, "❌ Ошибка загрузки данных волонтера.")
        return False

    # Проверяем блокировку
    if volunteer_info.get('is_blocked', False):
        send_message(volunteer_chat_id, "🚫 Вы заблокированы и не можете принимать запросы.")
        return False

    # Проверяем верификацию - только верифицированные могут принимать заявки
    verification_status = volunteer_info.get('verification_status', 'unverified')
    if verification_status not in ['verified', 'trusted']:
        send_message(
            volunteer_chat_id,
            "⚠️ Для приема заявок необходимо пройти верификацию.\n\n"
            "Вы можете только описывать фото для нуждающихся."
        )
        return False

    # Получаем запрос из PostgreSQL
    request = get_request(request_id)

    if not request or request["status"] != "pending":
        return False

    # Логируем действие
    log_action(volunteer_chat_id, "accept_request", "request", request_id)

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

    return True

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
        # Логируем действие
        log_action(needy_chat_id, "rate_volunteer", "review", review_id, details={"rating": rating})

        # Добавляем кнопку жалобы если рейтинг низкий
        if rating <= 2:
            text = f"✅ Спасибо за оценку ({rating} ⭐)!\n\nЕсли у вас были проблемы с волонтером, вы можете пожаловаться модераторам."
            buttons = [
                [{"type": "callback", "text": "⚠️ Пожаловаться на волонтера", "payload": f"complaint_{request_id}"}],
                [{"type": "callback", "text": "🔙 В меню", "payload": "menu"}]
            ]
            send_message_with_keyboard(needy_chat_id, text, buttons)
        else:
            # Предлагаем оставить комментарий (опционально)
            send_message(needy_chat_id, f"✅ Спасибо за оценку ({rating} ⭐)!\n\nЕсли хотите, можете написать комментарий волонтёру (просто отправьте сообщение).\n\nИли выберите функцию из меню:")
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

            send_message(volunteer_id, f"⭐ Вы получили оценку {rating} звёзд!{stats_text}")
    else:
        send_message(needy_chat_id, "❌ Не удалось сохранить оценку. Попробуйте позже.")

# Словарь для хранения состояний жалоб
complaint_states = {}

def handle_complaint(needy_chat_id, request_id):
    """Обработка жалобы на волонтера"""
    user = get_user(needy_chat_id)
    if not user or user['role'] != 'needy':
        send_message(needy_chat_id, "Только нуждающиеся могут подавать жалобы.")
        return

    request = get_request(request_id)
    if not request:
        send_message(needy_chat_id, "❌ Запрос не найден.")
        return

    volunteer_id = request.get('assigned_volunteer_id')
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
        "volunteer_id": volunteer_id
    }

    send_message(needy_chat_id, text)

def handle_complaint_reason(needy_chat_id, reason):
    """Обработка причины жалобы"""
    if needy_chat_id not in complaint_states:
        return False

    state = complaint_states[needy_chat_id]
    request_id = state['request_id']
    volunteer_id = state['volunteer_id']

    # Создаем жалобу
    complaint_id = create_complaint(request_id, needy_chat_id, volunteer_id, reason)

    if complaint_id:
        # Логируем действие
        log_action(needy_chat_id, "create_complaint", "complaint", complaint_id)

        send_message(
            needy_chat_id,
            f"✅ Жалоба #{complaint_id} отправлена модераторам!\n\n"
            "Спасибо за обратную связь. Модераторы рассмотрят вашу жалобу."
        )

        # Уведомляем модераторов
        from database import get_all_users_by_role
        moderators = get_all_users_by_role('moderator')

        notification_text = f"""
⚠️ **Новая жалоба #{complaint_id}**

На волонтера: {volunteer_id}
От нуждающегося: {needy_chat_id}
Заявка: #{request_id}

Причина: {reason}
"""

        for moderator_id in moderators:
            try:
                buttons = [[{"text": "🛡️ Открыть панель модератора", "payload": "moderator_menu"}]]
                send_message_with_keyboard(moderator_id, notification_text, buttons)
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления модератору {moderator_id}: {e}")

        del complaint_states[needy_chat_id]
    else:
        send_message(needy_chat_id, "❌ Ошибка при отправке жалобы. Попробуйте позже.")
        del complaint_states[needy_chat_id]

    return True
