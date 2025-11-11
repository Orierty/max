"""
Обработчик голосовых сообщений
"""
import logging
import os
import time
from bot.utils.voice import transcribe_voice, parse_voice_command, download_voice
from bot.utils import send_message
from bot.config import DOWNLOADS_DIR
from .requests import handle_request_call
from .image import handle_image_to_text_request
from .sos import handle_sos
from .menu import show_needy_menu

logger = logging.getLogger(__name__)

# Словарь для хранения режима обработки голоса: {chat_id: "text_only" | "commands"}
voice_mode = {}

def handle_voice_to_text_request(chat_id):
    """
    Запрос на преобразование голоса в текст (без выполнения команд)
    Просто просим пользователя отправить голосовое сообщение
    """
    # Устанавливаем режим "только текст"
    voice_mode[chat_id] = "text_only"

    send_message(
        chat_id,
        "🎤 Отправьте мне голосовое сообщение, и я преобразую его в текст.\n\n"
        "Эта функция только распознаёт речь, но не выполняет команды."
    )

def handle_voice_to_text_only(chat_id, voice_url):
    """
    Обработка голосового сообщения ТОЛЬКО для преобразования в текст
    (без распознавания и выполнения команд)

    Args:
        chat_id: ID чата
        voice_url: URL голосового сообщения
    """
    try:
        # Уведомляем пользователя
        send_message(chat_id, "🎤 Распознаю речь...")

        # Скачиваем аудио файл
        voice_filename = f"voice_{chat_id}_{int(time.time())}.ogg"
        voice_path = os.path.join(DOWNLOADS_DIR, voice_filename)

        if not download_voice(voice_url, voice_path):
            send_message(chat_id, "❌ Ошибка при скачивании голосового сообщения")
            return

        # Распознаём речь
        logger.info(f"Распознаём голосовое для текста от {chat_id}")
        text = transcribe_voice(voice_path)

        if not text:
            send_message(chat_id, "❌ Не удалось распознать речь. Попробуйте ещё раз.")
        else:
            # Отправляем только текст, без команд
            send_message(chat_id, f"📝 Распознанный текст:\n\n\"{text}\"")

        # Сбрасываем режим обработки голоса
        if chat_id in voice_mode:
            del voice_mode[chat_id]

        # Удаляем временный файл
        try:
            os.remove(voice_path)
            logger.info(f"Временный файл {voice_path} удалён")
        except:
            pass

    except Exception as e:
        logger.error(f"Ошибка обработки голосового для текста: {e}", exc_info=True)
        send_message(chat_id, "❌ Произошла ошибка при обработке голосового сообщения")

def handle_voice_message(chat_id, voice_url, username, user_id):
    """
    Обработка голосового сообщения

    1. Скачивает аудио
    2. Распознаёт речь с помощью Whisper
    3. Определяет команду
    4. Выполняет команду
    """
    try:
        # Уведомляем пользователя
        send_message(chat_id, "🎤 Обрабатываю голосовое сообщение...")

        # Скачиваем аудио файл
        voice_filename = f"voice_{chat_id}_{int(time.time())}.ogg"
        voice_path = os.path.join(DOWNLOADS_DIR, voice_filename)

        if not download_voice(voice_url, voice_path):
            send_message(chat_id, "❌ Ошибка при скачивании голосового сообщения")
            return

        # Распознаём речь
        logger.info(f"Распознаём голосовое сообщение от {chat_id}")
        text = transcribe_voice(voice_path)

        if not text:
            send_message(chat_id, "❌ Не удалось распознать речь. Попробуйте ещё раз.")
            # Удаляем временный файл
            try:
                os.remove(voice_path)
            except:
                pass
            return

        # Показываем распознанный текст
        send_message(chat_id, f"📝 Вы сказали:\n\"{text}\"")

        # Определяем команду
        result = parse_voice_command(text)
        command = result.get("command")
        confidence = result.get("confidence", 0.0)

        logger.info(f"Распознана команда: {command} (уверенность: {confidence:.2f})")

        # Выполняем команду
        if command and confidence >= 0.3:  # Порог уверенности 30%
            execute_voice_command(chat_id, command, username, user_id, confidence)
        else:
            # Не распознали команду
            send_message(
                chat_id,
                "🤔 Не смог распознать команду.\n\n"
                "Попробуйте сказать:\n"
                "• \"Позвоните мне волонтёр\"\n"
                "• \"Покажи меню\"\n"
                "• \"SOS помогите\"\n"
                "• \"Опиши картинку\""
            )

        # Удаляем временный файл
        try:
            os.remove(voice_path)
            logger.info(f"Временный файл {voice_path} удалён")
        except:
            pass

    except Exception as e:
        logger.error(f"Ошибка обработки голосового сообщения: {e}", exc_info=True)
        send_message(chat_id, f"❌ Произошла ошибка при обработке голосового сообщения")

def execute_voice_command(chat_id, command, username, user_id, confidence):
    """
    Выполняет распознанную команду

    Args:
        chat_id: ID чата
        command: название команды
        username: имя пользователя
        user_id: ID пользователя
        confidence: уверенность в распознавании (0.0-1.0)
    """
    logger.info(f"Выполняем команду: {command} (confidence: {confidence:.2f})")

    # Эмодзи уверенности
    confidence_emoji = "✅" if confidence >= 0.7 else "⚠️"

    if command == "request_call":
        send_message(chat_id, f"{confidence_emoji} Запрашиваю звонок от волонтёра...")
        handle_request_call(chat_id, username, user_id, None)

    elif command == "image_to_text":
        send_message(chat_id, f"{confidence_emoji} Активирую распознавание изображений...")
        handle_image_to_text_request(chat_id)

    elif command == "sos":
        send_message(chat_id, f"{confidence_emoji} Активирую сигнал SOS...")
        handle_sos(chat_id, username, user_id)

    elif command == "menu":
        send_message(chat_id, f"{confidence_emoji} Показываю меню...")
        show_needy_menu(chat_id)

    else:
        logger.warning(f"Неизвестная команда: {command}")
        send_message(chat_id, "❌ Неизвестная команда")
