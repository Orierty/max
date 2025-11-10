-- Схема базы данных для Max.ru бота волонтёров

-- Таблица пользователей
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(100) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    link VARCHAR(200),
    role VARCHAR(20) NOT NULL CHECK (role IN ('volunteer', 'needy')),
    registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    tags TEXT[],
    city VARCHAR(50)
);

-- Таблица волонтёров (расширенная информация)
CREATE TABLE IF NOT EXISTS volunteers (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100) UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    rating DECIMAL(3, 2) DEFAULT 0.00,
    call_count INTEGER DEFAULT 0
);

-- Таблица запросов
CREATE TABLE IF NOT EXISTS requests (
    id VARCHAR(100) PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    assigned_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) NOT NULL CHECK (status IN ('pending', 'active', 'completed', 'cancelled')),
    urgency VARCHAR(20) DEFAULT 'normal' CHECK (urgency IN ('normal', 'urgent')),
    completion_time TIMESTAMP,
    assigned_volunteer_id VARCHAR(100) REFERENCES users(id) ON DELETE SET NULL
);

-- Таблица отзывов
CREATE TABLE IF NOT EXISTS reviews (
    id SERIAL PRIMARY KEY,
    request_id VARCHAR(100) NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
    comment VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Индексы для оптимизации запросов
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(status);
CREATE INDEX IF NOT EXISTS idx_requests_user_id ON requests(user_id);
CREATE INDEX IF NOT EXISTS idx_requests_volunteer_id ON requests(assigned_volunteer_id);
CREATE INDEX IF NOT EXISTS idx_reviews_request_id ON reviews(request_id);
CREATE INDEX IF NOT EXISTS idx_volunteers_user_id ON volunteers(user_id);

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
