# Структура проекта Max.ru бота

## Обзор

Проект реорганизован на модульную архитектуру для улучшения поддержки и масштабируемости.

## Структура папок

```
max/
├── bot/                      # Основной пакет бота
│   ├── config.py            # Конфигурация (токены, настройки)
│   ├── handlers/            # Обработчики событий
│   │   ├── __init__.py
│   │   ├── messages.py      # Обработка текстовых сообщений
│   │   ├── callbacks.py     # Обработка callback'ов
│   │   ├── menu.py          # Меню и навигация
│   │   ├── requests.py      # Обработка запросов на помощь
│   │   ├── reviews.py       # Система отзывов и рейтингов
│   │   └── image.py         # Обработка изображений
│   ├── utils/               # Утилиты
│   │   ├── __init__.py
│   │   ├── max_api.py       # Функции Max.ru API
│   │   └── vision.py        # Работа с моделью Qwen2-VL
│   └── models/              # (зарезервировано для будущих моделей)
├── database.py              # Работа с PostgreSQL
├── schema.sql               # SQL схема базы данных
├── migrate_to_postgres.py   # Миграция из JSON в PostgreSQL
├── main.py                  # Точка входа (новый главный файл)
├── max_echo_bot.py          # Старый главный файл (deprecated)
├── requirements.txt         # Зависимости Python
├── .env                     # Переменные окружения
├── .env.example             # Пример переменных окружения
├── .gitignore              # Git ignore правила
├── downloads/               # Временные файлы (изображения)
├── models/                  # Локальные AI модели
└── docs/                    # Документация
    ├── PROJECT_STRUCTURE.md
    └── POSTGRES_SETUP.md
```

## Основные модули

### `bot/config.py`
Централизованная конфигурация:
- Токены и API ключи
- Настройки базы данных
- Параметры моделей AI
- Константы приложения

### `bot/utils/max_api.py`
Функции для работы с Max.ru API:
- `get_updates()` - получение обновлений
- `send_message()` - отправка сообщений
- `send_message_with_keyboard()` - сообщения с кнопками
- `answer_callback()` - ответы на callback'и
- `get_bot_info()` - информация о боте
- `create_user_mention()` - упоминания пользователей

### `bot/utils/vision.py`
Работа с моделью распознавания изображений:
- `init_vision_model()` - инициализация модели
- `describe_image()` - описание изображения
- `download_image()` - скачивание изображений

### `bot/handlers/`
Обработчики событий:
- `menu.py` - меню и навигация
- `messages.py` - текстовые сообщения
- `callbacks.py` - callback запросы
- `requests.py` - запросы на помощь
- `reviews.py` - отзывы и рейтинги
- `image.py` - обработка изображений

### `database.py`
Работа с PostgreSQL:
- Connection pool
- CRUD операции для всех таблиц
- Функции для работы с пользователями
- Функции для работы с запросами
- Функции для работы с отзывами
- Функции для работы с тегами

## Преимущества новой структуры

✅ **Модульность** - каждый компонент в отдельном файле
✅ **Переиспользуемость** - легко использовать функции в разных частях кода
✅ **Тестируемость** - проще писать unit-тесты
✅ **Масштабируемость** - легко добавлять новые функции
✅ **Читаемость** - код организован логически
✅ **Поддержка** - проще находить и исправлять баги

## Как использовать

### Запуск бота

Вариант 1 (новый):
```bash
python main.py
```

Вариант 2 (старый, пока работает):
```bash
python max_echo_bot.py
```

### Импорт модулей

```python
# Конфигурация
from bot.config import MAX_TOKEN, VISION_MODEL_ENABLED

# API функции
from bot.utils import send_message, get_updates

# Vision функции
from bot.utils import describe_image, init_vision_model

# Обработчики
from bot.handlers import handle_message, handle_callback

# База данных
from database import get_user, create_request, create_review
```

## Миграция старого кода

Старый файл `max_echo_bot.py` будет постепенно переписан используя новую структуру.

Текущий статус:
- ✅ Конфигурация вынесена в `bot/config.py`
- ✅ API функции в `bot/utils/max_api.py`
- ✅ Vision функции в `bot/utils/vision.py`
- ⏳ Обработчики переносятся в `bot/handlers/`
- ⏳ Создание нового `main.py`

## Следующие шаги

1. Завершить перенос обработчиков в `bot/handlers/`
2. Создать новый `main.py` с чистой архитектурой
3. Добавить unit-тесты
4. Обновить документацию
5. Удалить старый `max_echo_bot.py` (после проверки)
