"""
Автоматическая инициализация пула групповых чатов

Автоматически находит все чаты, в которых состоит бот,
и добавляет их в пул при запуске бота.
"""
import logging
import requests
from bot.config import MAX_TOKEN, MAX_API_URL
from database import get_connection, release_connection

logger = logging.getLogger(__name__)


def get_bot_chats():
    """
    Получает список всех чатов, в которых состоит бот

    Returns:
        list: список чатов [{'chat_id': int, 'chat_title': str}, ...]
    """
    try:
        url = f"{MAX_API_URL}/chats"
        headers = {
            'Content-Type': 'application/json'
        }

        chats = []
        marker = None

        while True:
            params = {'count': 100, 'access_token': MAX_TOKEN}
            if marker:
                params['marker'] = marker

            response = requests.get(url, headers=headers, params=params, timeout=10)

            if response.status_code != 200:
                logger.error(f"Ошибка получения списка чатов: {response.status_code} - {response.text}")
                break

            data = response.json()
            chat_list = data.get('chats', [])

            for chat in chat_list:
                # Берём только групповые чаты с активным статусом
                # type = 'chat' означает групповой чат
                # status = 'active' означает что бот активен в чате
                chat_type = chat.get('type')
                chat_status = chat.get('status')

                if chat_type == 'chat' and chat_status == 'active':
                    chats.append({
                        'chat_id': chat.get('chat_id'),
                        'chat_title': chat.get('title', 'Без названия')
                    })

            # Проверяем, есть ли ещё страницы
            marker = data.get('marker')
            if not marker:
                break

        logger.info(f"Найдено {len(chats)} групповых чатов")
        return chats

    except Exception as e:
        logger.error(f"Исключение при получении списка чатов: {e}")
        return []


def sync_chat_pool():
    """
    Синхронизирует пул чатов с реальным списком чатов бота
    Добавляет новые чаты и удаляет те, из которых бот был удалён
    """
    try:
        logger.info("🔄 Синхронизация пула групповых чатов...")

        # Получаем список чатов из Max.ru
        bot_chats = get_bot_chats()
        if not bot_chats:
            logger.warning("⚠️  Не найдено ни одного группового чата")
            return

        bot_chat_ids = {chat['chat_id'] for chat in bot_chats}

        conn = get_connection()
        if not conn:
            logger.error("Не удалось подключиться к БД для синхронизации чатов")
            return

        try:
            with conn.cursor() as cur:
                # Получаем список чатов из БД
                cur.execute("SELECT id, chat_id, chat_title FROM chat_rooms")
                db_chats = cur.fetchall()
                db_chat_ids = {row[1] for row in db_chats}

                # Находим новые чаты (есть в Max.ru, но нет в БД)
                new_chat_ids = bot_chat_ids - db_chat_ids

                # Находим удалённые чаты (есть в БД, но нет в Max.ru)
                removed_chat_ids = db_chat_ids - bot_chat_ids

                # Добавляем новые чаты
                added_count = 0
                for chat in bot_chats:
                    if chat['chat_id'] in new_chat_ids:
                        cur.execute("""
                            INSERT INTO chat_rooms (chat_id, chat_title, is_occupied)
                            VALUES (%s, %s, FALSE)
                            ON CONFLICT (chat_id) DO NOTHING
                        """, (chat['chat_id'], chat['chat_title']))
                        added_count += 1
                        logger.info(f"➕ Добавлен чат: {chat['chat_title']} (ID: {chat['chat_id']})")

                # Удаляем чаты, из которых бот был удалён (только свободные)
                removed_count = 0
                for chat_id in removed_chat_ids:
                    # Удаляем только свободные чаты (не занятые заявками)
                    cur.execute("""
                        DELETE FROM chat_rooms
                        WHERE chat_id = %s AND is_occupied = FALSE
                    """, (chat_id,))
                    if cur.rowcount > 0:
                        removed_count += 1
                        logger.info(f"➖ Удалён чат ID: {chat_id} (бот больше не в чате)")

                # Предупреждаем о занятых чатах, из которых бот был удалён
                for chat_id in removed_chat_ids:
                    cur.execute("""
                        SELECT is_occupied, current_request_id
                        FROM chat_rooms
                        WHERE chat_id = %s AND is_occupied = TRUE
                    """, (chat_id,))
                    occupied = cur.fetchone()
                    if occupied:
                        logger.warning(
                            f"⚠️  Чат {chat_id} занят заявкой {occupied[1]}, "
                            "но бот больше не в чате!"
                        )

                conn.commit()

                # Показываем статистику
                cur.execute("SELECT COUNT(*) FROM chat_rooms WHERE is_occupied = FALSE")
                free_count = cur.fetchone()[0]

                cur.execute("SELECT COUNT(*) FROM chat_rooms WHERE is_occupied = TRUE")
                occupied_count = cur.fetchone()[0]

                logger.info("✅ Синхронизация завершена:")
                logger.info(f"   ➕ Добавлено: {added_count}")
                logger.info(f"   ➖ Удалено: {removed_count}")
                logger.info(f"   🟢 Свободных чатов: {free_count}")
                logger.info(f"   🔴 Занятых чатов: {occupied_count}")

        finally:
            release_connection(conn)

    except Exception as e:
        logger.error(f"Ошибка синхронизации пула чатов: {e}", exc_info=True)
        if conn:
            conn.rollback()
