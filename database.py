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
            # Читаем schema.sql из папки db
            schema_path = os.path.join(os.path.dirname(__file__), "db", "schema.sql")
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

# === Функции для работы с верификацией ===

def get_volunteer_info(user_id):
    """Получает полную информацию о волонтере включая статус верификации"""
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT v.*, u.name, u.link
                FROM volunteers v
                JOIN users u ON u.id = v.user_id
                WHERE v.user_id = %s
            """, (str(user_id),))
            info = cur.fetchone()
            return dict(info) if info else None
    except Exception as e:
        logger.error(f"Ошибка получения информации о волонтере {user_id}: {e}")
        return None
    finally:
        if conn:
            release_connection(conn)

def create_verification_request(volunteer_id, document_urls, comment=""):
    """Создаёт заявку на верификацию волонтера"""
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            # Проверяем есть ли уже активная заявка
            cur.execute("""
                SELECT id FROM verification_requests
                WHERE volunteer_id = %s AND status = 'pending'
            """, (str(volunteer_id),))

            if cur.fetchone():
                logger.warning(f"У волонтера {volunteer_id} уже есть активная заявка")
                return None

            # Обновляем статус в volunteers
            cur.execute("""
                UPDATE volunteers
                SET verification_status = 'pending'
                WHERE user_id = %s
            """, (str(volunteer_id),))

            # Создаём заявку
            cur.execute("""
                INSERT INTO verification_requests (volunteer_id, document_urls, comment, status)
                VALUES (%s, %s, %s, 'pending')
                RETURNING id
            """, (str(volunteer_id), document_urls, comment))

            request_id = cur.fetchone()[0]
            conn.commit()
            logger.info(f"Создана заявка на верификацию {request_id} для волонтера {volunteer_id}")
            return request_id

    except Exception as e:
        logger.error(f"Ошибка создания заявки на верификацию: {e}")
        if conn:
            conn.rollback()
        return None
    finally:
        if conn:
            release_connection(conn)

def get_pending_verification_requests():
    """Получает список заявок на верификацию ожидающих проверки"""
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT vr.*, u.name as volunteer_name, u.link as volunteer_link
                FROM verification_requests vr
                JOIN users u ON u.id = vr.volunteer_id
                WHERE vr.status = 'pending'
                ORDER BY vr.created_at ASC
            """)
            requests = cur.fetchall()
            return [dict(r) for r in requests]
    except Exception as e:
        logger.error(f"Ошибка получения заявок на верификацию: {e}")
        return []
    finally:
        if conn:
            release_connection(conn)

def approve_verification_request(request_id, moderator_id, comment=""):
    """Одобряет заявку на верификацию"""
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            # Получаем ID волонтера
            cur.execute("""
                SELECT volunteer_id FROM verification_requests WHERE id = %s
            """, (request_id,))
            result = cur.fetchone()
            if not result:
                return False

            volunteer_id = result[0]

            # Обновляем заявку
            cur.execute("""
                UPDATE verification_requests
                SET status = 'approved',
                    reviewed_at = CURRENT_TIMESTAMP,
                    reviewed_by = %s,
                    moderator_comment = %s
                WHERE id = %s
            """, (str(moderator_id), comment, request_id))

            # Обновляем статус волонтера
            cur.execute("""
                UPDATE volunteers
                SET verification_status = 'verified'
                WHERE user_id = %s
            """, (volunteer_id,))

            conn.commit()
            logger.info(f"Заявка {request_id} одобрена модератором {moderator_id}")
            return True

    except Exception as e:
        logger.error(f"Ошибка одобрения заявки: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            release_connection(conn)

def reject_verification_request(request_id, moderator_id, comment=""):
    """Отклоняет заявку на верификацию"""
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            # Получаем ID волонтера
            cur.execute("""
                SELECT volunteer_id FROM verification_requests WHERE id = %s
            """, (request_id,))
            result = cur.fetchone()
            if not result:
                return False

            volunteer_id = result[0]

            # Обновляем заявку
            cur.execute("""
                UPDATE verification_requests
                SET status = 'rejected',
                    reviewed_at = CURRENT_TIMESTAMP,
                    reviewed_by = %s,
                    moderator_comment = %s
                WHERE id = %s
            """, (str(moderator_id), comment, request_id))

            # Возвращаем статус волонтера на unverified
            cur.execute("""
                UPDATE volunteers
                SET verification_status = 'unverified'
                WHERE user_id = %s
            """, (volunteer_id,))

            conn.commit()
            logger.info(f"Заявка {request_id} отклонена модератором {moderator_id}")
            return True

    except Exception as e:
        logger.error(f"Ошибка отклонения заявки: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            release_connection(conn)

# === Функции для работы с жалобами ===

def create_complaint(request_id, complainant_id, accused_id, reason):
    """Создаёт жалобу на волонтера"""
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO complaints (request_id, complainant_id, accused_id, reason, status)
                VALUES (%s, %s, %s, %s, 'pending')
                RETURNING id
            """, (str(request_id), str(complainant_id), str(accused_id), reason))

            complaint_id = cur.fetchone()[0]
            conn.commit()
            logger.info(f"Создана жалоба {complaint_id} от {complainant_id} на {accused_id}")
            return complaint_id

    except Exception as e:
        logger.error(f"Ошибка создания жалобы: {e}")
        if conn:
            conn.rollback()
        return None
    finally:
        if conn:
            release_connection(conn)

def get_pending_complaints():
    """Получает список жалоб ожидающих проверки"""
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT c.*,
                    u1.name as complainant_name,
                    u2.name as accused_name,
                    r.id as request_id
                FROM complaints c
                JOIN users u1 ON u1.id = c.complainant_id
                JOIN users u2 ON u2.id = c.accused_id
                JOIN requests r ON r.id = c.request_id
                WHERE c.status = 'pending'
                ORDER BY c.created_at ASC
            """)
            complaints = cur.fetchall()
            return [dict(c) for c in complaints]
    except Exception as e:
        logger.error(f"Ошибка получения жалоб: {e}")
        return []
    finally:
        if conn:
            release_connection(conn)

def resolve_complaint(complaint_id, moderator_id, action, comment=""):
    """Разрешает жалобу (блокирует пользователя или отклоняет жалобу)"""
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            # Обновляем жалобу
            cur.execute("""
                UPDATE complaints
                SET status = 'resolved',
                    reviewed_at = CURRENT_TIMESTAMP,
                    reviewed_by = %s,
                    moderator_action = %s,
                    moderator_comment = %s
                WHERE id = %s
            """, (str(moderator_id), action, comment, complaint_id))

            # Если действие = блокировка, блокируем волонтера
            if action == "block":
                cur.execute("""
                    UPDATE volunteers v
                    SET is_blocked = TRUE,
                        block_reason = %s,
                        blocked_at = CURRENT_TIMESTAMP
                    FROM complaints c
                    WHERE c.id = %s AND v.user_id = c.accused_id
                """, (f"Жалоба #{complaint_id}: {comment}", complaint_id))

            conn.commit()
            logger.info(f"Жалоба {complaint_id} разрешена модератором {moderator_id}")
            return True

    except Exception as e:
        logger.error(f"Ошибка разрешения жалобы: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            release_connection(conn)

# === Функции для работы с запросами на описание фото ===

def create_photo_description_request(needy_id, photo_url):
    """Создаёт запрос на описание фото"""
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO photo_description_requests (needy_id, photo_url, status)
                VALUES (%s, %s, 'pending')
                RETURNING id
            """, (str(needy_id), photo_url))

            request_id = cur.fetchone()[0]
            conn.commit()
            logger.info(f"Создан запрос на описание фото {request_id}")
            return request_id

    except Exception as e:
        logger.error(f"Ошибка создания запроса на описание фото: {e}")
        if conn:
            conn.rollback()
        return None
    finally:
        if conn:
            release_connection(conn)

def get_pending_photo_requests():
    """Получает список запросов на описание фото ожидающих обработки"""
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT p.*, u.name as needy_name
                FROM photo_description_requests p
                JOIN users u ON u.id = p.needy_id
                WHERE p.status = 'pending'
                ORDER BY p.created_at ASC
            """)
            requests = cur.fetchall()
            return [dict(r) for r in requests]
    except Exception as e:
        logger.error(f"Ошибка получения запросов на описание фото: {e}")
        return []
    finally:
        if conn:
            release_connection(conn)

def assign_photo_request(request_id, volunteer_id):
    """Назначает волонтера на запрос описания фото"""
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE photo_description_requests
                SET assigned_volunteer_id = %s,
                    status = 'assigned',
                    assigned_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (str(volunteer_id), request_id))

            conn.commit()
            logger.info(f"Волонтер {volunteer_id} назначен на описание фото {request_id}")
            return True

    except Exception as e:
        logger.error(f"Ошибка назначения волонтера на описание фото: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            release_connection(conn)

def complete_photo_request(request_id, description):
    """Завершает запрос на описание фото"""
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE photo_description_requests
                SET description = %s,
                    status = 'completed',
                    completed_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (description, request_id))

            conn.commit()
            logger.info(f"Запрос на описание фото {request_id} завершён")
            return True

    except Exception as e:
        logger.error(f"Ошибка завершения описания фото: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            release_connection(conn)

def get_photo_request(request_id):
    """Получает информацию о запросе на описание фото"""
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT p.*, u.name as needy_name
                FROM photo_description_requests p
                JOIN users u ON u.id = p.needy_id
                WHERE p.id = %s
            """, (request_id,))
            request = cur.fetchone()
            return dict(request) if request else None
    except Exception as e:
        logger.error(f"Ошибка получения запроса на описание фото: {e}")
        return None
    finally:
        if conn:
            release_connection(conn)

# === Функции для журнала действий ===

def log_action(user_id, action, target_type=None, target_id=None, details=None, ip_address=None):
    """Записывает действие пользователя в журнал"""
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO audit_log (user_id, action, target_type, target_id, details, ip_address)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (str(user_id), action, target_type, str(target_id) if target_id else None, details, ip_address))

            conn.commit()
            logger.debug(f"Действие {action} пользователя {user_id} записано в журнал")
            return True

    except Exception as e:
        logger.error(f"Ошибка записи в журнал: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            release_connection(conn)

def get_user_audit_log(user_id, limit=50):
    """Получает журнал действий пользователя"""
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM audit_log
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s
            """, (str(user_id), limit))
            logs = cur.fetchall()
            return [dict(log) for log in logs]
    except Exception as e:
        logger.error(f"Ошибка получения журнала пользователя: {e}")
        return []
    finally:
        if conn:
            release_connection(conn)

def close_db_pool():
    """Закрывает пул подключений"""
    global connection_pool
    if connection_pool:
        connection_pool.closeall()
        logger.info("Пул подключений закрыт")
