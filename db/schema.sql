-- Схема базы данных для Max.ru бота волонтёров

-- Таблица пользователей
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(100) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    link VARCHAR(200),
    role VARCHAR(20) NOT NULL CHECK (role IN ('volunteer', 'needy', 'moderator')),
    registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    tags TEXT[],
    city VARCHAR(50)
);

-- Таблица волонтёров (расширенная информация)
CREATE TABLE IF NOT EXISTS volunteers (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100) UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    rating DECIMAL(3, 2) DEFAULT 0.00,
    call_count INTEGER DEFAULT 0,
    verification_status VARCHAR(20) DEFAULT 'unverified'
        CHECK (verification_status IN ('unverified', 'pending', 'verified', 'trusted')),
    is_blocked BOOLEAN DEFAULT FALSE,
    block_reason TEXT,
    blocked_at TIMESTAMP,
    total_reviews_count INTEGER DEFAULT 0,
    completed_requests_count INTEGER DEFAULT 0
);

-- Таблица запросов
CREATE TABLE IF NOT EXISTS requests (
    id VARCHAR(100) PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    assigned_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) NOT NULL CHECK (status IN ('pending', 'active', 'completed', 'cancelled')),
    urgency VARCHAR(20) DEFAULT 'normal' CHECK (urgency IN ('normal', 'urgent')),
    completion_time TIMESTAMP,
    assigned_volunteer_id VARCHAR(100) REFERENCES users(id) ON DELETE SET NULL,
    current_wave INTEGER DEFAULT 0,
    notified_volunteers TEXT[],
    last_wave_sent_at TIMESTAMP
);

-- Таблица отзывов
CREATE TABLE IF NOT EXISTS reviews (
    id SERIAL PRIMARY KEY,
    request_id VARCHAR(100) NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
    comment VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    volunteer_id VARCHAR(100) REFERENCES users(id) ON DELETE CASCADE
);

-- Таблица заявок на верификацию
CREATE TABLE IF NOT EXISTS verification_requests (
    id SERIAL PRIMARY KEY,
    volunteer_id VARCHAR(100) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status VARCHAR(20) DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected')),
    document_urls TEXT[],
    comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP,
    reviewed_by VARCHAR(100) REFERENCES users(id) ON DELETE SET NULL,
    moderator_comment TEXT
);

-- Таблица жалоб
CREATE TABLE IF NOT EXISTS complaints (
    id SERIAL PRIMARY KEY,
    request_id VARCHAR(100) NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    complainant_id VARCHAR(100) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    accused_id VARCHAR(100) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    reason TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'pending'
        CHECK (status IN ('pending', 'reviewing', 'resolved', 'dismissed')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP,
    reviewed_by VARCHAR(100) REFERENCES users(id) ON DELETE SET NULL,
    moderator_action TEXT,
    moderator_comment TEXT
);

-- Таблица запросов на описание фото
CREATE TABLE IF NOT EXISTS photo_description_requests (
    id SERIAL PRIMARY KEY,
    needy_id VARCHAR(100) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    photo_url TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'pending'
        CHECK (status IN ('pending', 'assigned', 'completed', 'cancelled')),
    assigned_volunteer_id VARCHAR(100) REFERENCES users(id) ON DELETE SET NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    assigned_at TIMESTAMP,
    completed_at TIMESTAMP
);

-- Таблица журнала действий (audit log)
CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    action VARCHAR(50) NOT NULL,
    target_type VARCHAR(50),
    target_id VARCHAR(100),
    details JSONB,
    ip_address VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Индексы для оптимизации запросов
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(status);
CREATE INDEX IF NOT EXISTS idx_requests_user_id ON requests(user_id);
CREATE INDEX IF NOT EXISTS idx_requests_volunteer_id ON requests(assigned_volunteer_id);
CREATE INDEX IF NOT EXISTS idx_reviews_request_id ON reviews(request_id);
CREATE INDEX IF NOT EXISTS idx_volunteers_user_id ON volunteers(user_id);
CREATE INDEX IF NOT EXISTS idx_volunteers_verification_status ON volunteers(verification_status);
CREATE INDEX IF NOT EXISTS idx_volunteers_blocked ON volunteers(is_blocked);
CREATE INDEX IF NOT EXISTS idx_verification_requests_status ON verification_requests(status);
CREATE INDEX IF NOT EXISTS idx_verification_requests_volunteer ON verification_requests(volunteer_id);
CREATE INDEX IF NOT EXISTS idx_complaints_status ON complaints(status);
CREATE INDEX IF NOT EXISTS idx_complaints_accused ON complaints(accused_id);
CREATE INDEX IF NOT EXISTS idx_photo_requests_status ON photo_description_requests(status);
CREATE INDEX IF NOT EXISTS idx_audit_log_user ON audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_reviews_volunteer ON reviews(volunteer_id);

-- Функция для автоматического обновления времени завершения запроса
CREATE OR REPLACE FUNCTION update_completion_time()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'completed' AND OLD.status != 'completed' THEN
        NEW.completion_time = CURRENT_TIMESTAMP;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Триггер для автоматического обновления completion_time
DROP TRIGGER IF EXISTS trigger_update_completion_time ON requests;
CREATE TRIGGER trigger_update_completion_time
BEFORE UPDATE ON requests
FOR EACH ROW
EXECUTE FUNCTION update_completion_time();

-- Функция для автоматического обновления рейтинга волонтера
CREATE OR REPLACE FUNCTION update_volunteer_rating()
RETURNS TRIGGER AS $$
DECLARE
    v_volunteer_id VARCHAR(100);
    v_total_reviews INTEGER;
    v_sum_ratings DECIMAL;
    v_new_rating DECIMAL;
    v_avg_rating DECIMAL;
BEGIN
    -- Получаем ID волонтера из запроса
    SELECT assigned_volunteer_id INTO v_volunteer_id
    FROM requests
    WHERE id = NEW.request_id;

    IF v_volunteer_id IS NULL THEN
        RETURN NEW;
    END IF;

    -- Обновляем volunteer_id в таблице reviews
    NEW.volunteer_id = v_volunteer_id;

    -- Считаем статистику отзывов
    SELECT COUNT(*), SUM(rating)
    INTO v_total_reviews, v_sum_ratings
    FROM reviews
    WHERE volunteer_id = v_volunteer_id;

    -- Формула рейтинга с весами:
    -- - Первые 3 отзыва не влияют на блокировку (период испытания)
    -- - Используем взвешенное среднее с учетом количества отзывов
    IF v_total_reviews > 0 THEN
        v_avg_rating = v_sum_ratings / v_total_reviews;

        -- Взвешенный рейтинг: чем больше отзывов, тем ближе к среднему
        -- Формула: weighted_rating = (avg * count + 5 * 3) / (count + 3)
        -- Это дает "презумпцию невиновности" - начинаем с условной 5.0
        v_new_rating = (v_avg_rating * v_total_reviews + 5.0 * 3) / (v_total_reviews + 3);
    ELSE
        v_new_rating = 5.0;
    END IF;

    -- Обновляем рейтинг и счетчики в таблице volunteers
    UPDATE volunteers
    SET
        rating = ROUND(v_new_rating, 2),
        total_reviews_count = v_total_reviews
    WHERE user_id = v_volunteer_id;

    -- Автоблокировка если рейтинг < 3.0 И есть минимум 3 отзыва
    IF v_new_rating < 3.0 AND v_total_reviews >= 3 THEN
        UPDATE volunteers
        SET
            is_blocked = TRUE,
            block_reason = 'Автоматическая блокировка: рейтинг ниже 3.0',
            blocked_at = CURRENT_TIMESTAMP
        WHERE user_id = v_volunteer_id
        AND is_blocked = FALSE;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Триггер для автоматического обновления рейтинга при добавлении отзыва
DROP TRIGGER IF EXISTS trigger_update_volunteer_rating ON reviews;
CREATE TRIGGER trigger_update_volunteer_rating
BEFORE INSERT ON reviews
FOR EACH ROW
EXECUTE FUNCTION update_volunteer_rating();

-- Функция для повышения статуса волонтера до "trusted"
CREATE OR REPLACE FUNCTION check_trusted_status()
RETURNS TRIGGER AS $$
BEGIN
    -- Если волонтер выполнил 10+ заявок с рейтингом >= 4.5, даем статус "trusted"
    IF NEW.completed_requests_count >= 10 AND NEW.rating >= 4.5 AND NEW.verification_status = 'verified' THEN
        NEW.verification_status = 'trusted';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_check_trusted_status ON volunteers;
CREATE TRIGGER trigger_check_trusted_status
BEFORE UPDATE ON volunteers
FOR EACH ROW
EXECUTE FUNCTION check_trusted_status();

-- Функция для обновления счетчика выполненных заявок
CREATE OR REPLACE FUNCTION update_completed_requests_count()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'completed' AND OLD.status != 'completed' AND NEW.assigned_volunteer_id IS NOT NULL THEN
        UPDATE volunteers
        SET completed_requests_count = completed_requests_count + 1
        WHERE user_id = NEW.assigned_volunteer_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_completed_count ON requests;
CREATE TRIGGER trigger_update_completed_count
AFTER UPDATE ON requests
FOR EACH ROW
EXECUTE FUNCTION update_completed_requests_count();

-- Комментарии к таблицам
COMMENT ON TABLE verification_requests IS 'Заявки волонтеров на верификацию';
COMMENT ON TABLE complaints IS 'Жалобы на волонтеров от нуждающихся';
COMMENT ON TABLE photo_description_requests IS 'Запросы на описание фото волонтерами';
COMMENT ON TABLE audit_log IS 'Журнал действий пользователей для безопасности';
COMMENT ON COLUMN volunteers.verification_status IS 'unverified - новичок, pending - на проверке, verified - проверен, trusted - доверенный (10+ заявок, рейтинг 4.5+)';
