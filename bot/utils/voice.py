"""
Модуль для работы с голосовыми сообщениями
- Распознавание речи (Speech-to-Text) с помощью Vosk (офлайн, без OpenAI!)
- Определение команды из текста
"""
import os
import json
import logging
import requests
import wave
from bot.config import VOICE_ENABLED, MODELS_DIR

logger = logging.getLogger(__name__)

# Глобальная переменная для модели Vosk
vosk_model = None
vosk_recognizer = None

# Импортируем библиотеки только если голосовое управление включено
if VOICE_ENABLED:
    try:
        from vosk import Model, KaldiRecognizer
        from pydub import AudioSegment
        logger.info("Vosk библиотека успешно загружена")
    except ImportError as e:
        logger.error(f"Ошибка импорта Vosk: {e}")
        logger.error("Установите: pip install vosk pydub")
else:
    logger.info("Voice control отключено (VOICE_ENABLED=false)")

def init_vosk_model():
    """Инициализирует модель Vosk для распознавания речи"""
    global vosk_model

    if not VOICE_ENABLED:
        return False

    try:
        # Путь к модели Vosk для русского языка
        models_dir = os.path.join(os.path.dirname(__file__), "..", MODELS_DIR)
        os.makedirs(models_dir, exist_ok=True)

        model_path = os.path.join(models_dir, "vosk-model-small-ru-0.22")

        # Проверяем есть ли модель локально
        if not os.path.exists(model_path):
            logger.error(f"Модель Vosk не найдена в {model_path}")
            logger.info("Скачайте модель: https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip")
            logger.info("Распакуйте в папку models/")
            return False

        logger.info(f"Загружаем модель Vosk из {model_path}...")
        vosk_model = Model(model_path)
        logger.info("Модель Vosk успешно загружена")
        return True

    except Exception as e:
        logger.error(f"Ошибка загрузки модели Vosk: {e}", exc_info=True)
        return False

def convert_to_wav(input_path, output_path):
    """Конвертирует аудио в WAV формат для Vosk"""
    try:
        # Загружаем аудио (поддерживает ogg, mp3, m4a и т.д.)
        audio = AudioSegment.from_file(input_path)

        # Конвертируем в mono 16kHz WAV (требование Vosk)
        audio = audio.set_channels(1)  # Mono
        audio = audio.set_frame_rate(16000)  # 16kHz

        # Экспортируем в WAV
        audio.export(output_path, format="wav")
        logger.info(f"Аудио сконвертировано в WAV: {output_path}")
        return True

    except Exception as e:
        logger.error(f"Ошибка конвертации аудио: {e}")
        return False

def transcribe_voice(audio_path):
    """
    Распознаёт речь из аудио файла

    Args:
        audio_path: путь к аудио файлу

    Returns:
        str: распознанный текст или None при ошибке
    """
    global vosk_model

    if not VOICE_ENABLED:
        logger.info("Voice control отключено")
        return "🔧 Голосовое управление отключено. Включите VOICE_ENABLED=true в .env"

    # Загружаем модель если ещё не загружена
    if vosk_model is None:
        logger.info("Модель не загружена, инициализируем...")
        if not init_vosk_model():
            return None

    try:
        logger.info(f"Распознаём речь из файла: {audio_path}")

        # Конвертируем в WAV если нужно
        wav_path = audio_path
        if not audio_path.endswith('.wav'):
            wav_path = audio_path.rsplit('.', 1)[0] + '_converted.wav'
            if not convert_to_wav(audio_path, wav_path):
                return None

        # Открываем WAV файл
        wf = wave.open(wav_path, "rb")

        # Проверяем формат
        if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getframerate() not in [8000, 16000, 32000, 48000]:
            logger.error("Аудио файл должен быть mono PCM WAV")
            return None

        # Создаём распознаватель
        rec = KaldiRecognizer(vosk_model, wf.getframerate())
        rec.SetWords(True)

        # Распознаём речь
        results = []
        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                if 'text' in result:
                    results.append(result['text'])

        # Получаем финальный результат
        final_result = json.loads(rec.FinalResult())
        if 'text' in final_result:
            results.append(final_result['text'])

        # Объединяем весь текст
        text = ' '.join(results).strip()

        # Удаляем временный WAV файл если создавали
        if wav_path != audio_path:
            try:
                os.remove(wav_path)
            except:
                pass

        logger.info(f"Распознанный текст: {text}")
        return text if text else None

    except Exception as e:
        logger.error(f"Ошибка распознавания речи: {e}", exc_info=True)
        return None

def parse_voice_command(text):
    """
    Определяет команду из распознанного текста

    Args:
        text: распознанный текст

    Returns:
        dict: {"command": "название_команды", "confidence": 0.0-1.0}
    """
    if not text:
        return {"command": None, "confidence": 0.0}

    text_lower = text.lower()

    # Словарь команд и ключевых слов
    commands = {
        "request_call": [
            "позвони", "звонок", "волонтёр", "волонтер", "помощь", "нужна помощь",
            "свяжитесь", "связаться", "позвоните", "нужен звонок"
        ],
        "image_to_text": [
            "изображение", "картинка", "фото", "распознай", "что на фото",
            "опиши картинку", "что на картинке", "что изображено"
        ],
        "sos": [
            "sos", "сос", "срочно", "экстренно", "помогите", "спасите",
            "чрезвычайная", "авария", "беда"
        ],
        "menu": [
            "меню", "функции", "возможности", "что умеешь", "команды",
            "покажи меню", "открой меню"
        ]
    }

    # Ищем совпадения
    best_match = None
    max_matches = 0

    for command, keywords in commands.items():
        matches = sum(1 for keyword in keywords if keyword in text_lower)
        if matches > max_matches:
            max_matches = matches
            best_match = command

    # Вычисляем уверенность (confidence)
    if best_match and max_matches > 0:
        # Чем больше совпадений, тем выше уверенность
        confidence = min(1.0, max_matches / 2)  # Максимум 1.0
        return {"command": best_match, "confidence": confidence, "text": text}

    # Если ничего не нашли
    return {"command": None, "confidence": 0.0, "text": text}

def download_voice(url, save_path):
    """Скачивает голосовое сообщение по URL"""
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            with open(save_path, 'wb') as f:
                f.write(response.content)
            logger.info(f"Голосовое сообщение сохранено: {save_path}")
            return True
        else:
            logger.error(f"Ошибка скачивания голосового: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"Ошибка при скачивании голосового: {e}")
        return False
