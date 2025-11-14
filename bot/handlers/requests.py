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
    get_volunteer_info, create_complaint, log_action,
    get_available_volunteers_for_wave, update_request_wave,
    volunteer_has_active_request, get_connection, release_connection,
    get_active_request_for_user
)
from bot.utils import send_message, send_message_with_keyboard, create_user_mention, send_message_with_keyboard_and_menu
from bot.chat_room_manager import assign_chat_room_to_request, release_chat_room

logger = logging.getLogger(__name__)

def handle_request_call(chat_id, username, user_id=None, message_id=None):
    """Обработка запроса на звонок от волонтёра"""
    # Проверяем, зарегистрирован ли пользователь
    user = get_user(chat_id)
    if not user:
        # Регистрируем пользователя как needy
        from database import save_user
        save_user(chat_id, "needy", username, user_id=user_id)
        user = get_user(chat_id)

    # Проверяем, нет ли уже активной заявки
    active_request = get_active_request_for_user(chat_id)
    if active_request:
        buttons = [
            [{"type": "callback", "text": "❌ Отменить заявку", "payload": f"cancel_request_{active_request['id']}"}]
        ]
        send_message_with_keyboard_and_menu(
            chat_id,
            f"⚠️ У вас уже есть активная заявка #{active_request['id']}.\n\n"
            "Дождитесь ответа волонтёра или отмените её.",
            buttons
        )
        return

    # Создаём запрос в PostgreSQL
    request_id = create_request(chat_id, urgency="normal")

    if not request_id:
        send_message(chat_id, "❌ Не удалось создать запрос. Попробуйте позже.")
        return

    # Получаем теги пользователя для отображения волонтёрам
    tags_text = ""
    if user and user.get("tags"):
        tags_text = f"\nТеги: {', '.join(user['tags'])}"

    # Получаем 15 случайных доступных волонтёров для первой волны
    volunteers = get_available_volunteers_for_wave(exclude_volunteer_ids=None, limit=15)

    if not volunteers:
        send_message(chat_id, "⚠️ К сожалению, сейчас нет доступных волонтёров. Попробуйте позже.")
        return

    # Отправляем запрос выбранным волонтёрам
    volunteers_notified = 0
    for volunteer_id in volunteers:
        try:
            buttons = [
                [{"type": "callback", "text": "✅ Принять запрос", "payload": f"accept_request_{request_id}"}]
            ]
            send_message_with_keyboard(
                volunteer_id,
                f"🆘 Новый запрос на звонок!\n\nОт: @{username or 'неизвестно'}\nВремя: {datetime.now().strftime('%H:%M')}{tags_text}",
                buttons
            )
            volunteers_notified += 1
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления волонтёру {volunteer_id}: {e}")

    # Обновляем информацию о волне
    update_request_wave(request_id, volunteers)

    # Добавляем кнопку "Назад в меню"
    menu_button = [[{"type": "callback", "text": "🔙 Назад в меню", "payload": "menu"}]]

    if volunteers_notified > 0:
        send_message_with_keyboard(
            chat_id,
            f"✅ Ваш запрос отправлен {volunteers_notified} волонтёрам. Ожидайте ответа...",
            menu_button
        )
    else:
        send_message_with_keyboard(
            chat_id,
            "⚠️ К сожалению, сейчас нет доступных волонтёров. Попробуйте позже.",
            menu_button
        )

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

    # Проверяем, нет ли у волонтёра уже активной заявки
    if volunteer_has_active_request(volunteer_chat_id):
        send_message(
            volunteer_chat_id,
            "⚠️ У вас уже есть активная заявка.\n\n"
            "Завершите текущую заявку прежде чем принимать новую."
        )
        return False

    # Получаем запрос из PostgreSQL
    request = get_request(request_id)

    if not request or request["status"] != "pending":
        send_message(volunteer_chat_id, "⚠️ Этот запрос уже принят другим волонтёром.")
        return False

    # Логируем действие
    log_action(volunteer_chat_id, "accept_request", "request", request_id)

    # Обновляем статус запроса в PostgreSQL
    assign_volunteer_to_request(request_id, volunteer_chat_id)

    # Получаем user_id нуждающегося и волонтёра (числовые ID)
    needy_chat_id = request.get("user_id")
    logger.info(f"Needy chat_id: {needy_chat_id}")

    needy = get_user(needy_chat_id)
    logger.info(f"Needy user data: {needy}")
    needy_user_id = needy.get("user_id") if needy else None

    logger.info(f"Volunteer chat_id: {volunteer_chat_id}")
    volunteer = get_user(volunteer_chat_id)
    logger.info(f"Volunteer user data: {volunteer}")
    volunteer_user_id = volunteer.get("user_id") if volunteer else None

    logger.info(f"Final IDs - needy_user_id: {needy_user_id}, volunteer_user_id: {volunteer_user_id}")

    # Проверяем, что у обоих пользователей есть user_id
    if not needy_user_id or not volunteer_user_id:
        logger.error(f"Отсутствует user_id: needy={needy_user_id}, volunteer={volunteer_user_id}")
        send_message(volunteer_chat_id, "⚠️ Ошибка: не удалось получить ID пользователей. Попробуйте позже.")
        return False

    # Назначаем групповой чат для общения
    conn = get_connection()
    if conn:
        try:
            chat_result = assign_chat_room_to_request(
                conn,
                request_id,
                needy_user_id,
                volunteer_user_id
            )

            if chat_result and chat_result['success']:
                logger.info(f"Участники добавлены в групповой чат {chat_result['chat_id']}")
            else:
                logger.error(f"Не удалось назначить групповой чат для заявки {request_id}")

                # Отправляем сообщения обоим пользователям о проблеме
                send_message(volunteer_chat_id,
                    "⚠️ Не удалось создать групповой чат.\n\n"
                    "Возможные причины:\n"
                    "• У нуждающегося настройки приватности запрещают добавление в группы\n"
                    "• Технические проблемы\n\n"
                    "Пожалуйста, свяжитесь с нуждающимся напрямую или обратитесь к администратору."
                )

                send_message(needy_chat_id,
                    "⚠️ Волонтёр принял ваш запрос, но не удалось создать групповой чат.\n\n"
                    "Пожалуйста, проверьте настройки приватности в Max.ru:\n"
                    "Настройки → Приватность → Групповые чаты → Разрешить добавление\n\n"
                    "Или попробуйте создать новый запрос позже."
                )
                return False

        except Exception as e:
            logger.error(f"Ошибка при назначении чата: {e}")
            send_message(volunteer_chat_id, "⚠️ Произошла ошибка при создании чата.")
            return False
        finally:
            release_connection(conn)
    else:
        logger.error("Не удалось получить подключение к БД")
        return False

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
        f"✅ Вы приняли запрос!{stats_text}\n\nВы добавлены в групповой чат для общения с нуждающимся.\nПосле завершения диалога нажмите кнопку ниже.",
        buttons
    )

    # Уведомляем нуждающегося с mention волонтёра и кнопкой завершения
    text, markup = create_user_mention(
        "✅ Волонтёр {mention} принял ваш запрос!\n\nВы добавлены в групповой чат для общения.\nПосле завершения диалога нажмите кнопку ниже.",
        username=volunteer_username,
        user_id=volunteer_user_id
    )

    # Добавляем кнопку завершения для нуждающегося
    needy_buttons = [
        [{"type": "callback", "text": "✅ Завершить диалог", "payload": f"complete_request_{request_id}"}]
    ]
    send_message_with_keyboard(needy_chat_id, text, needy_buttons, markup=markup)

    return True

def handle_complete_request(chat_id, request_id):
    """Обработка завершения диалога (может быть вызвано волонтёром или нуждающимся)"""
    # Получаем информацию о запросе ДО завершения
    request = get_request(request_id)
    if not request:
        send_message(chat_id, "❌ Запрос не найден")
        return

    needy_chat_id = request.get("user_id")
    volunteer_chat_id_req = request.get("assigned_volunteer_id")
    chat_room_id = request.get("chat_room_id")

    if not needy_chat_id or not volunteer_chat_id_req:
        send_message(chat_id, "❌ Не удалось найти пользователей")
        return

    # Проверяем, кто закрывает заявку
    is_volunteer = (str(chat_id) == str(volunteer_chat_id_req))
    is_needy = (str(chat_id) == str(needy_chat_id))

    if not is_volunteer and not is_needy:
        send_message(chat_id, "❌ Вы не участвуете в этой заявке")
        return

    # Получаем числовые user_id для удаления из чата
    needy = get_user(needy_chat_id)
    volunteer = get_user(volunteer_chat_id_req)

    needy_user_id = needy.get("user_id") if needy else None
    volunteer_user_id = volunteer.get("user_id") if volunteer else None

    # Освобождаем чат, если был назначен
    if chat_room_id and needy_user_id and volunteer_user_id:
        conn = get_connection()
        try:
            # Получаем информацию о чате
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT chat_id FROM chat_rooms WHERE id = %s
                """, (chat_room_id,))
                result = cur.fetchone()

                if result:
                    chat_id = result[0]
                    # Освобождаем чат (удаляем участников и помечаем как свободный)
                    user_ids = [needy_user_id, volunteer_user_id]
                    from bot.chat_room_manager import release_chat_room
                    release_chat_room(conn, chat_room_id, chat_id, user_ids)
                    logger.info(f"Чат {chat_id} освобождён для заявки {request_id}")
        except Exception as e:
            logger.error(f"Ошибка при освобождении чата: {e}")
        finally:
            release_connection(conn)

    # Завершаем запрос
    complete_request(request_id)

    # Логируем действие
    log_action(chat_id, "complete_request", "request", request_id,
               details={"completed_by": "volunteer" if is_volunteer else "needy"})

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
        volunteer_chat_id_req,
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
        needy_chat_id,
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

def handle_cancel_request(chat_id, request_id):
    """Обработка отмены заявки нуждающимся"""
    from database import cancel_request
    from bot.utils import send_message_with_menu_button

    # Проверяем, что заявка принадлежит этому пользователю
    request = get_request(request_id)
    if not request:
        send_message_with_menu_button(chat_id, "❌ Заявка не найдена")
        return

    if request['needy_id'] != str(chat_id):
        send_message_with_menu_button(chat_id, "❌ Это не ваша заявка")
        return

    # Отменяем заявку
    success, message = cancel_request(request_id, cancelled_by_needy=True)

    if success:
        # Логируем действие
        log_action(chat_id, "cancel_request", "request", request_id)

        send_message_with_menu_button(
            chat_id,
            f"✅ Заявка #{request_id} отменена.\n\n"
            "Вы можете создать новую заявку в любое время."
        )
    else:
        send_message_with_menu_button(chat_id, f"❌ {message}")
