-- ----------------------------
-- 1. Создание основных таблиц
-- ----------------------------

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

-- Таблица волонтёров
CREATE TABLE IF NOT EXISTS volunteers (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(100) UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    rating DECIMAL(3,2) DEFAULT 0.00,
    call_count INTEGER DEFAULT 0,
    verification_status VARCHAR(20) DEFAULT 'unverified'
        CHECK (verification_status IN ('unverified', 'pending', 'verified', 'trusted')),
    is_blocked BOOLEAN DEFAULT FALSE,
    block_reason TEXT,
    blocked_at TIMESTAMP,
    total_reviews_count INTEGER DEFAULT 0,
    completed_requests_count INTEGER DEFAULT 0
);

-- Таблица chat_rooms (без ссылки на requests)
CREATE TABLE IF NOT EXISTS chat_rooms (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT UNIQUE NOT NULL,
    chat_title VARCHAR(200),
    is_occupied BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Таблица requests (без ссылки на chat_rooms)
CREATE TABLE IF NOT EXISTS requests (
    id VARCHAR(100) PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    assigned_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) NOT NULL CHECK (status IN ('pending','active','completed','cancelled')),
    urgency VARCHAR(20) DEFAULT 'normal' CHECK (urgency IN ('normal','urgent')),
    completion_time TIMESTAMP,
    assigned_volunteer_id VARCHAR(100) REFERENCES users(id) ON DELETE SET NULL,
    current_wave INTEGER DEFAULT 0,
    notified_volunteers TEXT[],
    last_wave_sent_at TIMESTAMP,
    chat_room_id INTEGER -- добавим FK позже
);

-- Таблица reviews
CREATE TABLE IF NOT EXISTS reviews (
    id SERIAL PRIMARY KEY,
    request_id VARCHAR(100) NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
    comment VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    volunteer_id VARCHAR(100) REFERENCES users(id) ON DELETE CASCADE
);

-- Таблица verification_requests
CREATE TABLE IF NOT EXISTS verification_requests (
    id SERIAL PRIMARY KEY,
    volunteer_id VARCHAR(100) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
    document_urls TEXT[],
    comment TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP,
    reviewed_by VARCHAR(100) REFERENCES users(id) ON DELETE SET NULL,
    moderator_comment TEXT
);

-- Таблица complaints
CREATE TABLE IF NOT EXISTS complaints (
    id SERIAL PRIMARY KEY,
    request_id VARCHAR(100) NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    complainant_id VARCHAR(100) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    accused_id VARCHAR(100) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    reason TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending','reviewing','resolved','dismissed')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP,
    reviewed_by VARCHAR(100) REFERENCES users(id) ON DELETE SET NULL,
    moderator_action TEXT,
    moderator_comment TEXT
);

-- Таблица photo_description_requests
CREATE TABLE IF NOT EXISTS photo_description_requests (
    id SERIAL PRIMARY KEY,
    needy_id VARCHAR(100) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    photo_url TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending','assigned','completed','cancelled')),
    assigned_volunteer_id VARCHAR(100) REFERENCES users(id) ON DELETE SET NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    assigned_at TIMESTAMP,
    completed_at TIMESTAMP
);

-- Таблица audit_log
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

-- ----------------------------
-- 2. Добавляем внешние ключи после создания таблиц
-- ----------------------------
ALTER TABLE requests
ADD CONSTRAINT fk_requests_chat_room
FOREIGN KEY (chat_room_id) REFERENCES chat_rooms(id) ON DELETE SET NULL;

ALTER TABLE chat_rooms
ADD COLUMN current_request_id VARCHAR(100);

ALTER TABLE chat_rooms
ADD CONSTRAINT fk_chat_rooms_request
FOREIGN KEY (current_request_id) REFERENCES requests(id) ON DELETE SET NULL;

-- ----------------------------
-- 3. Индексы
-- ----------------------------
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
CREATE INDEX IF NOT EXISTS idx_chat_rooms_occupied ON chat_rooms(is_occupied);
CREATE INDEX IF NOT EXISTS idx_chat_rooms_request ON chat_rooms(current_request_id);
CREATE INDEX IF NOT EXISTS idx_requests_chat_room ON requests(chat_room_id);
