"""
Менеджер пула групповых чатов для связи волонтёров и нуждающихся
"""
import logging
import requests
from bot.config import MAX_TOKEN, MAX_API_URL

logger = logging.getLogger(__name__)


def add_users_to_chat(chat_id, user_ids):
    """
    Добавляет пользователей в групповой чат

    Args:
        chat_id: ID группового чата
        user_ids: список ID пользователей для добавления

    Returns:
        bool: True если успешно, False если ошибка
    """
    try:
        url = f"{MAX_API_URL}/chats/{chat_id}/members"
        headers = {
            'Content-Type': 'application/json'
        }
        params = {
            'access_token': MAX_TOKEN
        }

        # Добавляем пользователей по одному, чтобы избежать проблем с теми, кто уже в чате
        success_count = 0
        for user_id in user_ids:
            data = {
                'user_ids': [user_id]
            }

            logger.info(f"Добавление пользователя {user_id} в чат {chat_id}")

            response = requests.post(url, headers=headers, params=params, json=data, timeout=10)
            response_data = response.json() if response.status_code == 200 else {}

            if response.status_code == 200 and response_data.get('success', False):
                logger.info(f"✓ Пользователь {user_id} успешно добавлен в чат {chat_id}")
                success_count += 1
            else:
                error_msg = response_data.get('message', 'Неизвестная ошибка')
                # Если пользователь уже в чате или другая ошибка - логируем как warning, но продолжаем
                if 'already' in error_msg.lower() or 'member' in error_msg.lower():
                    logger.warning(f"⚠ Пользователь {user_id} уже в чате {chat_id} или является участником")
                    success_count += 1  # Считаем успешным, т.к. пользователь в чате
                elif 'приватности' in error_msg.lower() or 'privacy' in error_msg.lower():
                    logger.error(f"✗ Пользователь {user_id} не разрешает добавление в групповые чаты (настройки приватности)")
                    logger.error(f"Response: {response.text}")
                elif 'rights' in error_msg.lower() or 'права' in error_msg.lower():
                    logger.error(f"✗ У бота нет прав администратора в чате {chat_id}")
                    logger.error(f"Response: {response.text}")
                else:
                    logger.error(f"✗ Ошибка добавления {user_id}: {error_msg}")
                    logger.error(f"Response: {response.text}")

        # Считаем успешным, если хотя бы один пользователь добавлен/уже в чате
        if success_count > 0:
            logger.info(f"Операция завершена: {success_count}/{len(user_ids)} пользователей в чате {chat_id}")
            return True
        else:
            logger.error(f"Не удалось добавить ни одного пользователя в чат {chat_id}")
            return False

    except Exception as e:
        logger.error(f"Исключение при добавлении в чат {chat_id}: {e}")
        return False


def remove_users_from_chat(chat_id, user_ids):
    """
    Удаляет пользователей из группового чата

    Args:
        chat_id: ID группового чата
        user_ids: список ID пользователей для удаления

    Returns:
        bool: True если успешно, False если ошибка
    """
    try:
        url = f"{MAX_API_URL}/chats/{chat_id}/members"
        headers = {
            'Content-Type': 'application/json'
        }

        success = True
        for user_id in user_ids:
            params = {
                'user_id': user_id,
                'access_token': MAX_TOKEN
            }
            response = requests.delete(url, headers=headers, params=params, timeout=10)

            if response.status_code == 200:
                logger.info(f"Пользователь {user_id} удалён из чата {chat_id}")
            else:
                logger.error(f"Ошибка удаления {user_id} из чата {chat_id}: {response.status_code}")
                success = False

        return success

    except Exception as e:
        logger.error(f"Исключение при удалении из чата {chat_id}: {e}")
        return False


def get_free_chat_room(conn):
    """
    Находит свободный чат из пула

    Args:
        conn: подключение к БД

    Returns:
        dict: информация о свободном чате или None
    """
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, chat_id, chat_title
                FROM chat_rooms
                WHERE is_occupied = FALSE
                ORDER BY id
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            """)
            result = cur.fetchone()

            if result:
                return {
                    'id': result[0],
                    'chat_id': result[1],
                    'chat_title': result[2]
                }
            return None

    except Exception as e:
        logger.error(f"Ошибка поиска свободного чата: {e}")
        return None


def occupy_chat_room(conn, room_id, request_id):
    """
    Помечает чат как занятый

    Args:
        conn: подключение к БД
        room_id: ID записи в chat_rooms
        request_id: ID заявки

    Returns:
        bool: True если успешно
    """
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE chat_rooms
                SET is_occupied = TRUE,
                    current_request_id = %s,
                    occupied_at = NOW()
                WHERE id = %s
            """, (request_id, room_id))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Ошибка занятия чата {room_id}: {e}")
        conn.rollback()
        return False


def release_chat_room(conn, room_id, chat_id, user_ids):
    """
    Освобождает чат: удаляет участников и помечает как свободный

    Args:
        conn: подключение к БД
        room_id: ID записи в chat_rooms
        chat_id: ID группового чата Max
        user_ids: список ID пользователей для удаления

    Returns:
        bool: True если успешно
    """
    try:
        # Удаляем пользователей из чата
        remove_users_from_chat(chat_id, user_ids)

        # Помечаем чат как свободный
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE chat_rooms
                SET is_occupied = FALSE,
                    current_request_id = NULL,
                    occupied_at = NULL
                WHERE id = %s
            """, (room_id,))
            conn.commit()

        logger.info(f"Чат {room_id} освобождён")
        return True

    except Exception as e:
        logger.error(f"Ошибка освобождения чата {room_id}: {e}")
        conn.rollback()
        return False


def assign_chat_room_to_request(conn, request_id, needy_user_id, volunteer_user_id):
    """
    Назначает свободный чат для заявки и добавляет в него участников

    Args:
        conn: подключение к БД
        request_id: ID заявки
        needy_user_id: ID нуждающегося (числовой)
        volunteer_user_id: ID волонтёра (числовой)

    Returns:
        dict: {'success': bool, 'room_id': int, 'chat_id': int} или None
    """
    try:
        # Находим свободный чат
        room = get_free_chat_room(conn)
        if not room:
            logger.error("Нет свободных чатов в пуле!")
            return None

        room_id = room['id']
        chat_id = room['chat_id']

        # Добавляем участников в чат
        user_ids = [int(needy_user_id), int(volunteer_user_id)]
        success = add_users_to_chat(chat_id, user_ids)

        if not success:
            logger.error(f"Не удалось добавить участников в чат {chat_id}")
            return None

        # Помечаем чат как занятый
        occupy_chat_room(conn, room_id, request_id)

        # Обновляем заявку - связываем с чатом
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE requests
                SET chat_room_id = %s
                WHERE id = %s
            """, (room_id, request_id))
            conn.commit()

        logger.info(f"Чат {chat_id} назначен для заявки {request_id}")

        return {
            'success': True,
            'room_id': room_id,
            'chat_id': chat_id
        }

    except Exception as e:
        logger.error(f"Ошибка назначения чата для заявки {request_id}: {e}")
        conn.rollback()
        return None
