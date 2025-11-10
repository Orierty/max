"""
Модуль для работы с PostgreSQL базой данных
"""
import os
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Connection pool для эффективной работы с БД
connection_pool = None

def init_db_pool():
    """Инициализирует пул подключений к базе данных"""
    global connection_pool

    try:
        connection_pool = psycopg2.pool.SimpleConnectionPool(
            1, 10,  # минимум 1, максимум 10 подключений
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5432"),
            database=os.getenv("DB_NAME", "max_bot"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "")
        )

        if connection_pool:
            logger.info("PostgreSQL connection pool создан успешно")
            # Создаём таблицы при первом подключении
            create_tables()
            return True
    except Exception as e:
        logger.error(f"Ошибка создания пула подключений: {e}")
        return False

def get_connection():
    """Получает подключение из пула"""
    if connection_pool:
        return connection_pool.getconn()
    return None

def release_connection(conn):
    """Возвращает подключение в пул"""
    if connection_pool and conn:
        connection_pool.putconn(conn)

def create_tables():
    """Создаёт таблицы из schema.sql"""
    conn = None
    try:
        conn = get_connection()
        if not conn:
            logger.error("Не удалось получить подключение к БД")
            return False

        with conn.cursor() as cur:
            # Читаем schema.sql
            schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
            with open(schema_path, 'r', encoding='utf-8') as f:
                schema_sql = f.read()

            # Выполняем SQL
            cur.execute(schema_sql)
            conn.commit()
            logger.info("Таблицы успешно созданы/обновлены")
            return True

    except Exception as e:
        logger.error(f"Ошибка создания таблиц: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            release_connection(conn)

# === Функции для работы с пользователями ===

def get_user(user_id):
    """Получает данные пользователя"""
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE id = %s", (str(user_id),))
            user = cur.fetchone()
            return dict(user) if user else None
    except Exception as e:
        logger.error(f"Ошибка получения пользователя {user_id}: {e}")
        return None
    finally:
        if conn:
            release_connection(conn)

def save_user(user_id, role, username=None, **kwargs):
    """Сохраняет или обновляет пользователя"""
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            # Проверяем существует ли пользователь
            cur.execute("SELECT id FROM users WHERE id = %s", (str(user_id),))
            exists = cur.fetchone()

            if exists:
                # Обновляем существующего
                cur.execute("""
                    UPDATE users
                    SET name = COALESCE(%s, name), role = %s
                    WHERE id = %s
                """, (username or "Аноним", role, str(user_id)))
            else:
                # Создаём нового
                cur.execute("""
                    INSERT INTO users (id, name, role, link, city, tags)
                    VALUES (%s, %s, %s, NULL, NULL, ARRAY[]::TEXT[])
                """, (str(user_id), username or "Аноним", role))

            # Если это волонтёр, создаём запись в volunteers
            if role == "volunteer":
                cur.execute("""
                    INSERT INTO volunteers (user_id, rating, call_count)
                    VALUES (%s, 0, 0)
                    ON CONFLICT (user_id) DO NOTHING
                """, (str(user_id),))

            conn.commit()
            logger.debug(f"Пользователь {user_id} сохранён")
            return True

    except Exception as e:
        logger.error(f"Ошибка сохранения пользователя {user_id}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            release_connection(conn)

# === Функции для работы с запросами ===

def create_request(user_id, urgency="normal"):
    """Создаёт новый запрос"""
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            request_id = str(int(datetime.now().timestamp() * 1000))

            cur.execute("""
                INSERT INTO requests (id, user_id, status, urgency)
                VALUES (%s, %s, 'pending', %s)
                RETURNING id
            """, (request_id, str(user_id), urgency))

            conn.commit()
            logger.debug(f"Запрос {request_id} создан")
            return request_id

    except Exception as e:
        logger.error(f"Ошибка создания запроса: {e}")
        if conn:
            conn.rollback()
        return None
    finally:
        if conn:
            release_connection(conn)

def assign_volunteer_to_request(request_id, volunteer_id):
    """Назначает волонтёра на запрос"""
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE requests
                SET assigned_volunteer_id = %s, status = 'active', assigned_time = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (str(volunteer_id), str(request_id)))

            conn.commit()
            logger.debug(f"Волонтёр {volunteer_id} назначен на запрос {request_id}")
            return True

    except Exception as e:
        logger.error(f"Ошибка назначения волонтёра: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            release_connection(conn)

def complete_request(request_id):
    """Завершает запрос"""
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE requests
                SET status = 'completed'
                WHERE id = %s
            """, (str(request_id),))

            conn.commit()
            logger.debug(f"Запрос {request_id} завершён")
            return True

    except Exception as e:
        logger.error(f"Ошибка завершения запроса: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            release_connection(conn)

def get_request(request_id):
    """Получает данные запроса"""
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM requests WHERE id = %s", (str(request_id),))
            request = cur.fetchone()
            return dict(request) if request else None
    except Exception as e:
        logger.error(f"Ошибка получения запроса {request_id}: {e}")
        return None
    finally:
        if conn:
            release_connection(conn)

def get_active_requests():
    """Получает список активных запросов"""
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM requests
                WHERE status IN ('pending', 'active')
                ORDER BY assigned_time DESC
            """)
            requests = cur.fetchall()
            return {str(r['id']): dict(r) for r in requests}
    except Exception as e:
        logger.error(f"Ошибка получения активных запросов: {e}")
        return {}
    finally:
        if conn:
            release_connection(conn)

# === Функции для работы с отзывами ===

def create_review(request_id, rating, comment=""):
    """Создаёт отзыв"""
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            # Создаём отзыв
            cur.execute("""
                INSERT INTO reviews (request_id, rating, comment)
                VALUES (%s, %s, %s)
                RETURNING id
            """, (str(request_id), rating, comment))

            review_id = cur.fetchone()[0]

            # Обновляем рейтинг волонтёра
            cur.execute("""
                WITH request_info AS (
                    SELECT assigned_volunteer_id
                    FROM requests
                    WHERE id = %s
                )
                UPDATE volunteers v
                SET
                    call_count = call_count + 1,
                    rating = ROUND(
                        ((rating * call_count) + %s::DECIMAL) / (call_count + 1),
                        2
                    )
                FROM request_info ri
                WHERE v.user_id = ri.assigned_volunteer_id
            """, (str(request_id), rating))

            conn.commit()
            logger.debug(f"Отзыв {review_id} создан для запроса {request_id}")
            return review_id

    except Exception as e:
        logger.error(f"Ошибка создания отзыва: {e}")
        if conn:
            conn.rollback()
        return None
    finally:
        if conn:
            release_connection(conn)

def add_tags_to_user(user_id, tags):
    """Добавляет теги к пользователю"""
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            # Получаем существующие теги
            cur.execute("SELECT tags FROM users WHERE id = %s", (str(user_id),))
            result = cur.fetchone()
            existing_tags = result[0] if result and result[0] else []

            # Добавляем новые теги
            new_tags = list(set(existing_tags + tags))

            cur.execute("""
                UPDATE users
                SET tags = %s
                WHERE id = %s
            """, (new_tags, str(user_id)))

            conn.commit()
            logger.debug(f"Теги добавлены пользователю {user_id}: {tags}")
            return True

    except Exception as e:
        logger.error(f"Ошибка добавления тегов: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            release_connection(conn)

def get_volunteer_stats(volunteer_id):
    """Получает статистику волонтёра"""
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT rating, call_count, user_id
                FROM volunteers
                WHERE user_id = %s
            """, (str(volunteer_id),))
            stats = cur.fetchone()
            return dict(stats) if stats else None
    except Exception as e:
        logger.error(f"Ошибка получения статистики волонтёра {volunteer_id}: {e}")
        return None
    finally:
        if conn:
            release_connection(conn)

def get_all_users_by_role(role):
    """Получает всех пользователей по роли"""
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE role = %s", (role,))
            users = cur.fetchall()
            return {str(u['id']): dict(u) for u in users}
    except Exception as e:
        logger.error(f"Ошибка получения пользователей по роли {role}: {e}")
        return {}
    finally:
        if conn:
            release_connection(conn)

def close_db_pool():
    """Закрывает пул подключений"""
    global connection_pool
    if connection_pool:
        connection_pool.closeall()
        logger.info("Пул подключений закрыт")
