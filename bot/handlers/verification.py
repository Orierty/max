"""
Обработчики для системы верификации и запросов на описание фото
"""
import logging
from bot.utils import send_message, send_message_with_keyboard, send_message_with_menu_button, send_message_with_keyboard_and_menu
from database import (
    get_user,
    get_volunteer_info,
    create_verification_request,
    create_photo_description_request,
    get_pending_photo_requests,
    assign_photo_request,
    complete_photo_request,
    get_photo_request,
    log_action
)

logger = logging.getLogger(__name__)

# Словарь для отслеживания состояний
verification_states = {}
photo_description_states = {}

def handle_verification_request(chat_id):
    """Обрабатывает запрос на верификацию"""
    user = get_user(chat_id)
    if not user or user['role'] != 'volunteer':
        send_message(chat_id, "Только волонтеры могут подавать заявки на верификацию.")
        return

    volunteer_info = get_volunteer_info(chat_id)
    if not volunteer_info:
        send_message(chat_id, "Ошибка загрузки данных волонтера.")
        return

    verification_status = volunteer_info.get('verification_status', 'unverified')

    if verification_status == 'pending':
        send_message(chat_id, "⏳ У вас уже есть заявка на верификацию, которая рассматривается.")
        return
    elif verification_status in ['verified', 'trusted']:
        send_message(chat_id, "✅ Вы уже верифицированы!")
        return

    text = """
✅ **Заявка на верификацию**

Для верификации необходимо предоставить:
1. Фото документа (паспорт, ID)
2. Справка о несудимости (опционально)

Отправьте ссылки на документы или их фото в следующем сообщении.

Также можете написать комментарий о себе.
"""

    verification_states[chat_id] = "waiting_for_documents"
    send_message(chat_id, text)

def handle_verification_documents(chat_id, message_text, attachments):
    """Обрабатывает отправку документов для верификации"""
    if chat_id not in verification_states:
        return False

    if verification_states[chat_id] != "waiting_for_documents":
        return False

    # Собираем ссылки на документы
    document_urls = []

    if attachments:
        for attachment in attachments:
            if attachment.get('type') == 'image':
                document_urls.append(attachment.get('payload', {}).get('url', ''))
            elif attachment.get('type') == 'file':
                document_urls.append(attachment.get('payload', {}).get('url', ''))

    if not document_urls:
        send_message(chat_id, "❌ Не найдено документов. Отправьте фото или файлы документов.")
        return True

    # Создаем заявку
    request_id = create_verification_request(chat_id, document_urls, message_text or "")

    if request_id:
        # Логируем действие
        log_action(chat_id, "request_verification", "verification_request", request_id)

        send_message(
            chat_id,
            f"✅ Заявка на верификацию #{request_id} отправлена модераторам!\n\n"
            "⏳ Ожидайте проверки. Вы получите уведомление о результате."
        )
        del verification_states[chat_id]
    else:
        send_message(chat_id, "❌ Ошибка при создании заявки. Попробуйте позже.")
        del verification_states[chat_id]

    return True

# === Запросы на описание фото ===

def handle_photo_description_request(chat_id):
    """Обрабатывает запрос нуждающегося на описание фото"""
    user = get_user(chat_id)
    if not user or user['role'] != 'needy':
        send_message(chat_id, "Эта функция доступна только для нуждающихся.")
        return

    text = """
👁️ **Описание фото волонтером**

Отправьте фото, которое хотите описать.

Волонтер-человек посмотрит на фото и опишет его вам текстом или голосом.
"""

    photo_description_states[chat_id] = "waiting_for_photo"
    send_message_with_menu_button(chat_id, text)

def handle_photo_for_description(chat_id, attachments):
    """Обрабатывает отправку фото для описания - использует волновую систему"""
    if chat_id not in photo_description_states:
        return False

    if photo_description_states[chat_id] != "waiting_for_photo":
        return False

    # Ищем фото в attachments
    photo_url = None
    if attachments:
        for attachment in attachments:
            if attachment.get('type') == 'image':
                photo_url = attachment.get('payload', {}).get('url', '')
                break

    if not photo_url:
        send_message_with_menu_button(chat_id, "❌ Фото не найдено. Отправьте изображение.")
        return True

    # Создаем запрос
    request_id = create_photo_description_request(chat_id, photo_url)

    if request_id:
        # Логируем действие
        log_action(chat_id, "request_photo_description", "photo_request", request_id)

        # Отправляем первую волну волонтёрам (15 человек)
        from database import get_available_volunteers_for_photo_wave, update_photo_request_wave
        volunteers = get_available_volunteers_for_photo_wave(limit=15)

        if volunteers:
            notification_text = f"""👁️ Новый запрос на описание фото

Нуждающийся просит описать фото.

Запрос #{request_id}"""

            sent_count = 0
            for volunteer_id in volunteers:
                try:
                    buttons = [[{"type": "callback", "text": "👁️ Взять запрос", "payload": f"take_photo_{request_id}"}]]
                    send_message_with_keyboard(volunteer_id, notification_text, buttons)
                    sent_count += 1
                except Exception as e:
                    logger.error(f"Ошибка отправки уведомления волонтеру {volunteer_id}: {e}")

            # Обновляем информацию о волне
            update_photo_request_wave(request_id, volunteers)

            send_message_with_menu_button(
                chat_id,
                f"✅ Запрос на описание фото создан!\n\n"
                f"📤 Отправлено {sent_count} волонтёрам.\n"
                "⏳ Ожидайте ответа..."
            )
        else:
            send_message_with_menu_button(
                chat_id,
                "✅ Запрос создан, но сейчас нет доступных волонтёров.\n\n"
                "⏳ Ожидайте, скоро волонтёр возьмёт ваш запрос."
            )

        del photo_description_states[chat_id]
    else:
        send_message_with_menu_button(chat_id, "❌ Ошибка при создании запроса. Попробуйте позже.")
        del photo_description_states[chat_id]

    return True

def show_photo_requests_for_volunteer(chat_id):
    """Показывает список запросов на описание фото для волонтера"""
    user = get_user(chat_id)
    if not user or user['role'] != 'volunteer':
        send_message(chat_id, "Эта функция доступна только для волонтеров.")
        return

    requests = get_pending_photo_requests()

    if not requests:
        text = "👁️ **Запросы на описание фото**\n\nНет доступных запросов."
        buttons = [[{"text": "🔙 Назад в меню", "payload": "menu"}]]
        send_message_with_keyboard(chat_id, text, buttons)
        return

    text = f"👁️ **Запросы на описание фото** ({len(requests)} шт.)\n\nВыберите запрос:"

    buttons = []
    for req in requests:
        needy_name = req['needy_name'] or "Без имени"
        created = req['created_at'].strftime("%d.%m %H:%M")
        buttons.append([{
            "text": f"👤 {needy_name} ({created})",
            "payload": f"view_photo_{req['id']}"
        }])

    buttons.append([{"text": "🔙 Назад в меню", "payload": "menu"}])

    send_message_with_keyboard(chat_id, text, buttons)

def handle_take_photo_request(chat_id, request_id):
    """Волонтер берет запрос на описание фото"""
    user = get_user(chat_id)
    if not user or user['role'] != 'volunteer':
        return

    volunteer_info = get_volunteer_info(chat_id)
    if not volunteer_info:
        return

    # Неверифицированные могут описывать фото
    # Блокированные не могут
    if volunteer_info.get('is_blocked', False):
        send_message(chat_id, "🚫 Вы заблокированы и не можете брать запросы.")
        return

    # Назначаем волонтера
    if assign_photo_request(request_id, chat_id):
        # Логируем действие
        log_action(chat_id, "take_photo_request", "photo_request", request_id)

        # Получаем детали запроса
        request = get_photo_request(request_id)
        if request:
            photo_url = request['photo_url']
            needy_id = request['needy_id']
            needy_name = request['needy_name']

            text = f"""
✅ Вы взяли запрос на описание фото #{request_id}

От: {needy_name}

Фото: {photo_url}

📝 Опишите фото текстом или отправьте голосовое описание в следующем сообщении.
"""

            send_message_with_menu_button(chat_id, text)

            # Сохраняем состояние
            photo_description_states[chat_id] = f"describing_{request_id}"

            # Уведомляем нуждающегося
            send_message_with_menu_button(
                needy_id,
                f"👁️ Волонтер взял ваш запрос на описание фото!\n\nОжидайте описание..."
            )
        else:
            send_message(chat_id, "❌ Ошибка загрузки запроса.")
    else:
        send_message(chat_id, "❌ Не удалось взять запрос. Возможно, его уже взял другой волонтер.")

def handle_photo_description(chat_id, message_text):
    """Обрабатывает описание фото от волонтера"""
    if chat_id not in photo_description_states:
        return False

    state = photo_description_states[chat_id]
    if not state.startswith("describing_"):
        return False

    request_id = int(state.split("_")[1])

    # Завершаем запрос
    if complete_photo_request(request_id, message_text):
        # Увеличиваем счётчик ответов
        from database import increment_photo_response_count
        response_count = increment_photo_response_count(request_id)

        # Логируем действие
        log_action(chat_id, "complete_photo_description", "photo_request", request_id,
                  details={"response_count": response_count})

        send_message(chat_id, f"✅ Спасибо! Описание отправлено нуждающемуся.\n\n📊 Это описание #{response_count} для данного запроса.")

        # Получаем детали запроса и отправляем нуждающемуся с кнопками оценки
        request = get_photo_request(request_id)
        if request:
            needy_id = request['needy_id']

            # Кнопки для оценки описания (с кнопкой меню)
            buttons = [
                [
                    {"type": "callback", "text": "✅ Помогло", "payload": f"photo_helpful_{request_id}"},
                    {"type": "callback", "text": "❌ Не помогло", "payload": f"photo_not_helpful_{request_id}"}
                ]
            ]

            send_message_with_keyboard_and_menu(
                needy_id,
                f"👁️ **Описание вашего фото:**\n\n{message_text}\n\n"
                f"📊 Получено описаний: {response_count}\n\n"
                "Помогло ли вам это описание?",
                buttons
            )

        del photo_description_states[chat_id]
    else:
        send_message(chat_id, "❌ Ошибка при отправке описания.")
        del photo_description_states[chat_id]

    return True

def handle_photo_helpful(chat_id, request_id):
    """Обрабатывает оценку 'Помогло' для описания фото"""
    from database import get_photo_request
    request = get_photo_request(request_id)

    if not request or request['needy_id'] != str(chat_id):
        send_message_with_menu_button(chat_id, "❌ Запрос не найден")
        return

    # Отмечаем запрос как полностью завершённый
    from database import get_connection, release_connection
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE photo_description_requests
                SET status = 'completed'
                WHERE id = %s
            """, (request_id,))
            conn.commit()

        logger.info(f"Описание фото #{request_id} отмечено как помогшее")

        # Логируем действие
        log_action(chat_id, "photo_helpful", "photo_request", request_id)

        send_message_with_menu_button(
            chat_id,
            "✅ Спасибо за оценку!\n\n"
            "Рады, что волонтёр смог вам помочь! ❤️"
        )

        # Благодарим волонтёра
        volunteer_id = request.get('assigned_volunteer_id')
        if volunteer_id:
            send_message(
                volunteer_id,
                f"🎉 Нуждающийся отметил, что ваше описание фото #{request_id} помогло!\n\n"
                "Спасибо за помощь! ❤️"
            )

    except Exception as e:
        logger.error(f"Ошибка при обработке оценки 'Помогло': {e}")
        send_message_with_menu_button(chat_id, "❌ Произошла ошибка")
    finally:
        if conn:
            release_connection(conn)

def handle_photo_not_helpful(chat_id, request_id):
    """Обрабатывает оценку 'Не помогло' для описания фото - отправляет следующую волну"""
    from database import get_photo_request, mark_photo_description_failed, \
                         get_photo_request_notified_volunteers, get_available_volunteers_for_photo_wave, \
                         update_photo_request_wave

    request = get_photo_request(request_id)

    if not request or request['needy_id'] != str(chat_id):
        send_message_with_menu_button(chat_id, "❌ Запрос не найден")
        return

    volunteer_id = request.get('assigned_volunteer_id')

    # Отмечаем волонтёра как неудачного
    if volunteer_id:
        mark_photo_description_failed(request_id, volunteer_id)
        logger.info(f"Волонтёр {volunteer_id} отмечен как неудачный для запроса #{request_id}")

    # Логируем действие
    log_action(chat_id, "photo_not_helpful", "photo_request", request_id,
              details={"failed_volunteer": volunteer_id})

    # Получаем информацию о волнах
    wave_info = get_photo_request_notified_volunteers(request_id)
    if not wave_info:
        send_message_with_menu_button(chat_id, "❌ Ошибка получения информации о запросе")
        return

    # Исключаем уже уведомлённых и неудачных волонтёров
    notified = wave_info['notified_volunteers']
    failed = wave_info['failed_volunteers']
    exclude_list = list(set(notified + failed))

    # Отправляем следующую волну (15 новых волонтёров)
    volunteers = get_available_volunteers_for_photo_wave(exclude_volunteer_ids=exclude_list, limit=15)

    if volunteers:
        notification_text = f"""👁️ Новый запрос на описание фото

Нуждающийся просит описать фото.

Запрос #{request_id}
Волна #{wave_info['current_wave'] + 1}"""

        sent_count = 0
        for vol_id in volunteers:
            try:
                buttons = [[{"type": "callback", "text": "👁️ Взять запрос", "payload": f"take_photo_{request_id}"}]]
                send_message_with_keyboard(vol_id, notification_text, buttons)
                sent_count += 1
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления волонтеру {vol_id}: {e}")

        # Обновляем информацию о волне
        update_photo_request_wave(request_id, volunteers)

        send_message_with_menu_button(
            chat_id,
            f"👁️ Отправляем запрос следующим волонтёрам...\n\n"
            f"📤 Отправлено ещё {sent_count} волонтёрам.\n"
            "⏳ Ожидайте новые описания..."
        )
    else:
        send_message_with_menu_button(
            chat_id,
            "⚠️ К сожалению, больше нет доступных волонтёров.\n\n"
            "Попробуйте создать новый запрос позже."
        )
