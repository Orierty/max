"""
Фоновое задание для отправки волн уведомлений волонтёрам
"""
import logging
import time
import threading
from datetime import datetime, timedelta
from database import (
    get_connection, release_connection,
    get_available_volunteers_for_wave,
    update_request_wave,
    get_request_notified_volunteers,
    get_user
)
from bot.utils import send_message_with_keyboard
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

# Глобальный флаг для остановки потока
_stop_flag = False
_wave_thread = None

def start_wave_sender():
    """Запускает фоновый поток для отправки волн"""
    global _wave_thread, _stop_flag

    if _wave_thread and _wave_thread.is_alive():
        logger.warning("Wave sender уже запущен")
        return

    _stop_flag = False
    _wave_thread = threading.Thread(target=_wave_sender_loop, daemon=True)
    _wave_thread.start()
    logger.info("Wave sender запущен")

def stop_wave_sender():
    """Останавливает фоновый поток"""
    global _stop_flag
    _stop_flag = True
    logger.info("Wave sender остановлен")

def _wave_sender_loop():
    """Основной цикл отправки волн"""
    while not _stop_flag:
        try:
            _process_pending_requests()
        except Exception as e:
            logger.error(f"Ошибка в wave sender: {e}")

        # Проверяем каждые 5 секунд
        time.sleep(5)

def _process_pending_requests():
    """Обрабатывает заявки, ожидающие следующей волны"""
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Ищем заявки которые pending и прошло 15+ секунд с последней волны
            cur.execute("""
                SELECT id, user_id, notified_volunteers, current_wave, last_wave_sent_at
                FROM requests
                WHERE status = 'pending'
                AND last_wave_sent_at IS NOT NULL
                AND last_wave_sent_at < NOW() - INTERVAL '15 seconds'
                AND current_wave < 5
            """)
            pending_requests = cur.fetchall()

            for request in pending_requests:
                request_id = request['id']
                needy_id = request['user_id']
                notified_volunteers = request['notified_volunteers'] or []
                current_wave = request['current_wave']

                logger.info(f"Отправка волны {current_wave + 1} для заявки {request_id}")

                # Получаем следующую партию волонтёров (исключая тех, кому уже отправили)
                next_volunteers = get_available_volunteers_for_wave(
                    exclude_volunteer_ids=notified_volunteers,
                    limit=15
                )

                if not next_volunteers:
                    # Нет больше доступных волонтёров
                    logger.warning(f"Нет доступных волонтёров для заявки {request_id}")
                    cur.execute("""
                        UPDATE requests
                        SET current_wave = 99
                        WHERE id = %s
                    """, (request_id,))
                    conn.commit()

                    # Уведомляем нуждающегося
                    from bot.utils import send_message
                    send_message(
                        needy_id,
                        "⚠️ К сожалению, все доступные волонтёры заняты.\n\n"
                        "Попробуйте создать заявку позже."
                    )
                    continue

                # Отправляем уведомления
                volunteers_notified = 0
                needy_user = get_user(needy_id)
                needy_name = needy_user.get('name', 'неизвестно') if needy_user else 'неизвестно'

                tags_text = ""
                if needy_user and needy_user.get("tags"):
                    tags_text = f"\nТеги: {', '.join(needy_user['tags'])}"

                for volunteer_id in next_volunteers:
                    try:
                        buttons = [
                            [{"type": "callback", "text": "✅ Принять запрос", "payload": f"accept_request_{request_id}"}]
                        ]
                        send_message_with_keyboard(
                            volunteer_id,
                            f"🆘 Новый запрос на звонок!\n\nОт: @{needy_name}\nВремя: {datetime.now().strftime('%H:%M')}{tags_text}",
                            buttons
                        )
                        volunteers_notified += 1
                    except Exception as e:
                        logger.error(f"Ошибка отправки уведомления волонтёру {volunteer_id}: {e}")

                # Обновляем информацию о волне
                if volunteers_notified > 0:
                    update_request_wave(request_id, next_volunteers)
                    logger.info(f"Отправлено {volunteers_notified} уведомлений для заявки {request_id}")

    except Exception as e:
        logger.error(f"Ошибка обработки pending requests: {e}")
    finally:
        if conn:
            release_connection(conn)
