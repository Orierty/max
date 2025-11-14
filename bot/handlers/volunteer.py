"""
Обработчики для волонтеров
"""
import logging
from database import get_connection, release_connection
from bot.utils import send_message, send_message_with_keyboard

logger = logging.getLogger(__name__)


def show_volunteer_stats(chat_id):
    """Показывает статистику волонтера"""
    conn = get_connection()
    if not conn:
        send_message(chat_id, "❌ Ошибка подключения к базе данных")
        return

    try:
        with conn.cursor() as cur:
            # Получаем статистику волонтера
            cur.execute("""
                SELECT
                    v.rating,
                    v.completed_requests_count,
                    v.total_reviews_count,
                    v.verification_status,
                    u.name,
                    u.registration_date
                FROM volunteers v
                JOIN users u ON v.user_id = u.id
                WHERE u.id = %s
            """, (str(chat_id),))

            stats = cur.fetchone()

            if not stats:
                send_message(chat_id, "❌ Статистика не найдена")
                return

            rating, completed, reviews, status, name, reg_date = stats

            # Форматируем статус
            status_emoji = {
                'unverified': '🆕',
                'pending': '⏳',
                'verified': '✅',
                'trusted': '⭐'
            }

            status_text = {
                'unverified': 'Новичок',
                'pending': 'На проверке',
                'verified': 'Верифицирован',
                'trusted': 'Доверенный'
            }

            # Получаем текущие активные заявки
            cur.execute("""
                SELECT COUNT(*)
                FROM requests
                WHERE assigned_volunteer_id = %s AND status = 'active'
            """, (str(chat_id),))
            active_count = cur.fetchone()[0]

            # Формируем сообщение
            stats_message = f"""
📊 **Ваша статистика**

👤 Имя: {name}
{status_emoji.get(status, '❓')} Статус: {status_text.get(status, 'Неизвестен')}
⭐ Рейтинг: {rating:.2f}/5.00
✅ Выполнено заявок: {completed}
💬 Получено отзывов: {reviews}
📅 В системе с: {reg_date.strftime('%d.%m.%Y')}

📋 Активных заявок сейчас: {active_count}
"""

            # Кнопка возврата в меню
            buttons = [
                [{"type": "callback", "text": "🔙 Назад в меню", "payload": "menu"}]
            ]

            send_message_with_keyboard(chat_id, stats_message, buttons)

    except Exception as e:
        logger.error(f"Ошибка получения статистики для {chat_id}: {e}")
        send_message(chat_id, "❌ Произошла ошибка при получении статистики")
    finally:
        release_connection(conn)


def show_active_requests_list(chat_id):
    """Показывает список активных заявок волонтера"""
    conn = get_connection()
    if not conn:
        send_message(chat_id, "❌ Ошибка подключения к базе данных")
        return

    try:
        with conn.cursor() as cur:
            # Получаем активные заявки
            cur.execute("""
                SELECT
                    r.id,
                    r.assigned_time,
                    r.urgency,
                    u.name as needy_name,
                    u.tags
                FROM requests r
                JOIN users u ON r.user_id = u.id
                WHERE r.assigned_volunteer_id = %s AND r.status = 'active'
                ORDER BY r.assigned_time DESC
            """, (str(chat_id),))

            requests_list = cur.fetchall()

            if not requests_list:
                message = "📋 **Активные заявки**\n\nУ вас нет активных заявок.\n\nЗаявки будут приходить вам автоматически волнами."
                buttons = [
                    [{"type": "callback", "text": "🔙 Назад в меню", "payload": "menu"}]
                ]
                send_message_with_keyboard(chat_id, message, buttons)
                return

            # Формируем список заявок
            message = "📋 **Ваши активные заявки:**\n\n"

            buttons = []
            for req in requests_list:
                req_id, assigned_time, urgency, needy_name, tags = req

                # Эмодзи для срочности
                urgency_emoji = "🔴" if urgency == "urgent" else "🟢"

                # Форматируем теги
                tags_str = ""
                if tags:
                    tags_emoji = {
                        'elderly': '👵',
                        'blind': '👁️',
                        'bad_camera': '📷',
                        'bad_mic': '🎤',
                        'hearing': '🦻'
                    }
                    tags_str = " " + " ".join([tags_emoji.get(tag, tag) for tag in tags])

                # Время с момента принятия
                time_str = assigned_time.strftime('%H:%M')

                message += f"{urgency_emoji} Заявка от {needy_name}{tags_str}\n"
                message += f"   Принята в {time_str}\n\n"

                # Кнопка завершения для каждой заявки
                buttons.append([{
                    "type": "callback",
                    "text": f"✅ Завершить: {needy_name[:20]}",
                    "payload": f"complete_request_{req_id}"
                }])

            # Кнопка возврата
            buttons.append([{"type": "callback", "text": "🔙 Назад в меню", "payload": "menu"}])

            send_message_with_keyboard(chat_id, message, buttons)

    except Exception as e:
        logger.error(f"Ошибка получения активных заявок для {chat_id}: {e}")
        send_message(chat_id, "❌ Произошла ошибка при получении списка заявок")
    finally:
        release_connection(conn)
