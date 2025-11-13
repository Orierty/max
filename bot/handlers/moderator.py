"""
Обработчики для панели модератора
"""
import logging
from bot.utils import send_message, send_message_with_keyboard, forward_message
from database import (
    get_user,
    get_pending_verification_requests,
    approve_verification_request,
    reject_verification_request,
    get_pending_complaints,
    resolve_complaint,
    log_action
)

logger = logging.getLogger(__name__)

def show_moderator_menu(chat_id):
    """Показывает меню модератора"""
    user = get_user(chat_id)

    if not user or user['role'] != 'moderator':
        send_message(chat_id, "У вас нет доступа к панели модератора.")
        return

    text = """
🛡️ **Панель модератора**

Выберите раздел для управления:
"""

    buttons = [
        [
            {"type": "callback", "text": "📋 Заявки на верификацию", "payload": "mod_verifications"},
            {"type": "callback", "text": "⚠️ Жалобы", "payload": "mod_complaints"}
        ],
        [
            {"type": "callback", "text": "🔙 Назад", "payload": "menu"}
        ]
    ]

    send_message_with_keyboard(chat_id, text, buttons)

def show_verification_requests(chat_id):
    """Показывает список заявок на верификацию"""
    user = get_user(chat_id)
    if not user or user['role'] != 'moderator':
        send_message(chat_id, "У вас нет доступа к этому разделу.")
        return

    requests = get_pending_verification_requests()

    if not requests:
        text = "📋 **Заявки на верификацию**\n\nНет заявок ожидающих проверки."
        buttons = [[{"type": "callback", "text": "🔙 Назад", "payload": "moderator_menu"}]]
        send_message_with_keyboard(chat_id, text, buttons)
        return

    text = f"📋 **Заявки на верификацию** ({len(requests)} шт.)\n\nВыберите заявку для проверки:"

    buttons = []
    for req in requests:
        volunteer_name = req['volunteer_name'] or "Без имени"
        created = req['created_at'].strftime("%d.%m %H:%M")
        buttons.append([{
            "type": "callback",
            "text": f"👤 {volunteer_name} ({created})",
            "payload": f"mod_verify_{req['id']}"
        }])

    buttons.append([{"type": "callback", "text": "🔙 Назад", "payload": "moderator_menu"}])

    send_message_with_keyboard(chat_id, text, buttons)

def show_verification_request_details(chat_id, request_id):
    """Показывает детали заявки на верификацию"""
    user = get_user(chat_id)
    if not user or user['role'] != 'moderator':
        return

    requests = get_pending_verification_requests()
    request = next((r for r in requests if r['id'] == request_id), None)

    if not request:
        send_message(chat_id, "Заявка не найдена или уже обработана.")
        return

    volunteer_name = request['volunteer_name'] or "Без имени"
    volunteer_link = request.get('volunteer_link', '')
    comment = request.get('comment', 'Нет комментария')
    created = request['created_at'].strftime("%d.%m.%Y %H:%M")

    text = f"""
📋 **Заявка на верификацию #{request_id}**

👤 Волонтер: {volunteer_name}
🔗 Ссылка: {volunteer_link if volunteer_link else 'Нет'}
📅 Создана: {created}

💬 Комментарий волонтера:
{comment}

📎 Документы: {len(request.get('document_urls', []))} шт.
"""

    buttons = [
        [
            {"type": "callback", "text": "✅ Одобрить", "payload": f"mod_approve_{request_id}"},
            {"type": "callback", "text": "❌ Отклонить", "payload": f"mod_reject_{request_id}"}
        ],
        [{"type": "callback", "text": "🔙 Назад", "payload": "mod_verifications"}]
    ]

    send_message_with_keyboard(chat_id, text, buttons)

    # Пересылаем документы
    if request.get('document_urls'):
        for url in request['document_urls']:
            send_message(chat_id, f"📎 Документ: {url}")

def approve_verification(chat_id, request_id):
    """Одобряет заявку на верификацию"""
    user = get_user(chat_id)
    if not user or user['role'] != 'moderator':
        return

    if approve_verification_request(request_id, chat_id):
        # Логируем действие
        log_action(chat_id, "approve_verification", "verification_request", request_id)

        send_message(chat_id, "✅ Заявка одобрена! Волонтер получил статус 'verified'.")

        # Уведомляем волонтера
        requests = get_pending_verification_requests()
        # Пытаемся найти в истории (заявка уже approved)
        from database import get_connection, release_connection
        from psycopg2.extras import RealDictCursor

        conn = get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT volunteer_id FROM verification_requests WHERE id = %s
                """, (request_id,))
                result = cur.fetchone()
                if result:
                    volunteer_id = result['volunteer_id']
                    send_message(
                        volunteer_id,
                        "🎉 Поздравляем! Ваша заявка на верификацию одобрена!\n\n"
                        "Теперь вы можете принимать заявки от нуждающихся."
                    )
        finally:
            release_connection(conn)

        show_verification_requests(chat_id)
    else:
        send_message(chat_id, "❌ Ошибка при одобрении заявки.")

def reject_verification(chat_id, request_id):
    """Отклоняет заявку на верификацию"""
    user = get_user(chat_id)
    if not user or user['role'] != 'moderator':
        return

    if reject_verification_request(request_id, chat_id, "Не соответствует требованиям"):
        # Логируем действие
        log_action(chat_id, "reject_verification", "verification_request", request_id)

        send_message(chat_id, "❌ Заявка отклонена.")

        # Уведомляем волонтера
        from database import get_connection, release_connection
        from psycopg2.extras import RealDictCursor

        conn = get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT volunteer_id FROM verification_requests WHERE id = %s
                """, (request_id,))
                result = cur.fetchone()
                if result:
                    volunteer_id = result['volunteer_id']
                    send_message(
                        volunteer_id,
                        "❌ К сожалению, ваша заявка на верификацию отклонена.\n\n"
                        "Причина: Не соответствует требованиям.\n\n"
                        "Вы можете подать новую заявку позже."
                    )
        finally:
            release_connection(conn)

        show_verification_requests(chat_id)
    else:
        send_message(chat_id, "❌ Ошибка при отклонении заявки.")

def show_complaints(chat_id):
    """Показывает список жалоб"""
    user = get_user(chat_id)
    if not user or user['role'] != 'moderator':
        return

    complaints = get_pending_complaints()

    if not complaints:
        text = "⚠️ **Жалобы**\n\nНет жалоб ожидающих проверки."
        buttons = [[{"type": "callback", "text": "🔙 Назад", "payload": "moderator_menu"}]]
        send_message_with_keyboard(chat_id, text, buttons)
        return

    text = f"⚠️ **Жалобы** ({len(complaints)} шт.)\n\nВыберите жалобу для проверки:"

    buttons = []
    for complaint in complaints:
        complainant = complaint['complainant_name'] or "Без имени"
        accused = complaint['accused_name'] or "Без имени"
        created = complaint['created_at'].strftime("%d.%m %H:%M")
        buttons.append([{
            "type": "callback",
            "text": f"⚠️ {complainant} → {accused} ({created})",
            "payload": f"mod_complaint_{complaint['id']}"
        }])

    buttons.append([{"type": "callback", "text": "🔙 Назад", "payload": "moderator_menu"}])

    send_message_with_keyboard(chat_id, text, buttons)

def show_complaint_details(chat_id, complaint_id):
    """Показывает детали жалобы"""
    user = get_user(chat_id)
    if not user or user['role'] != 'moderator':
        return

    complaints = get_pending_complaints()
    complaint = next((c for c in complaints if c['id'] == complaint_id), None)

    if not complaint:
        send_message(chat_id, "Жалоба не найдена или уже обработана.")
        return

    complainant = complaint['complainant_name'] or "Без имени"
    accused = complaint['accused_name'] or "Без имени"
    reason = complaint['reason']
    created = complaint['created_at'].strftime("%d.%m.%Y %H:%M")
    request_id = complaint['request_id']

    text = f"""
⚠️ **Жалоба #{complaint_id}**

От кого: {complainant}
На кого: {accused}
📅 Дата: {created}
🆔 Заявка: #{request_id}

📝 Причина жалобы:
{reason}
"""

    buttons = [
        [
            {"type": "callback", "text": "🔨 Заблокировать волонтера", "payload": f"mod_block_{complaint_id}"},
        ],
        [
            {"type": "callback", "text": "✅ Отклонить жалобу", "payload": f"mod_dismiss_{complaint_id}"}
        ],
        [{"type": "callback", "text": "🔙 Назад", "payload": "mod_complaints"}]
    ]

    send_message_with_keyboard(chat_id, text, buttons)

def block_volunteer(chat_id, complaint_id):
    """Блокирует волонтера по жалобе"""
    user = get_user(chat_id)
    if not user or user['role'] != 'moderator':
        return

    if resolve_complaint(complaint_id, chat_id, "block", "Заблокирован по жалобе"):
        # Логируем действие
        log_action(chat_id, "block_volunteer", "complaint", complaint_id)

        send_message(chat_id, "🔨 Волонтер заблокирован.")

        # Уведомляем волонтера
        complaints = get_pending_complaints()
        # Получаем accused_id из БД
        from database import get_connection, release_connection
        from psycopg2.extras import RealDictCursor

        conn = get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT accused_id FROM complaints WHERE id = %s
                """, (complaint_id,))
                result = cur.fetchone()
                if result:
                    accused_id = result['accused_id']
                    send_message(
                        accused_id,
                        "🔨 Вы были заблокированы модератором.\n\n"
                        "Причина: Жалоба от нуждающегося.\n\n"
                        "Для разблокировки обратитесь к администрации."
                    )
        finally:
            release_connection(conn)

        show_complaints(chat_id)
    else:
        send_message(chat_id, "❌ Ошибка при блокировке волонтера.")

def dismiss_complaint(chat_id, complaint_id):
    """Отклоняет жалобу"""
    user = get_user(chat_id)
    if not user or user['role'] != 'moderator':
        return

    if resolve_complaint(complaint_id, chat_id, "dismiss", "Жалоба необоснована"):
        # Логируем действие
        log_action(chat_id, "dismiss_complaint", "complaint", complaint_id)

        send_message(chat_id, "✅ Жалоба отклонена как необоснованная.")
        show_complaints(chat_id)
    else:
        send_message(chat_id, "❌ Ошибка при отклонении жалобы.")
