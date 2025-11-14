import os
import logging
from gigachat import GigaChat
import requests
from PIL import Image
import io
from bot.config import VISION_MODEL_ENABLED, GIGACHAT_API_KEY
from io import BytesIO

logger = logging.getLogger(__name__)

VISION_MODEL = "GigaChat-Pro"
vision_client = None


# ---------- ИНИЦИАЛИЗАЦИЯ GIGACHAT ----------


def convert_to_jpeg(image_path):
    """Конвертирует изображение в RGB JPEG и возвращает BytesIO с именем файла."""
    try:
        with Image.open(image_path) as img:
            logger.info(f"Формат изображения: {img.format}, Режим: {img.mode}")

            buffer = BytesIO()
            img.convert("RGB").save(buffer, format="JPEG", quality=95)
            buffer.name = "image.jpg"  # <- ВАЖНО! указываем имя файла
            buffer.seek(0)
            return buffer

    except Exception as e:
        logger.error(f"Ошибка конвертации изображения: {e}")
        raise


def init_vision_model():
    """Инициализирует GigaChat клиент."""
    global vision_client

    if not VISION_MODEL_ENABLED:
        logger.info("Vision отключён")
        return False

    if not GIGACHAT_API_KEY:
        logger.error("GIGACHAT_API_KEY отсутствует")
        return False

    try:
        vision_client = GigaChat(
            credentials=GIGACHAT_API_KEY,
            verify_ssl_certs=False,
            model=VISION_MODEL,
            scope="GIGACHAT_API_PERS",
        )
        logger.info("GigaChat Vision клиент инициализирован")
        return True

    except Exception as e:
        logger.error(f"Ошибка инициализации: {e}")
        return False


# ---------- ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ----------


def prepare_image_for_upload(image_path):
    """Проверяет формат изображения и конвертирует в RGB JPEG, если нужно."""
    try:
        with Image.open(image_path) as img:
            logger.info(f"Формат изображения: {img.format}, Режим: {img.mode}")

            # Если не JPEG или PNG или есть альфа-канал — конвертируем в RGB JPEG
            if img.format not in ["JPEG", "PNG"] or img.mode != "RGB":
                logger.info("Конвертация изображения в JPEG...")
                buffer = io.BytesIO()
                img.convert("RGB").save(buffer, format="JPEG", quality=95)
                buffer.seek(0)
                return buffer
            else:
                # Открываем обычным файлом
                buffer = open(image_path, "rb")
                return buffer

    except Exception as e:
        logger.error(f"Ошибка подготовки изображения: {e}")
        raise


# ---------- ОСНОВНАЯ ФУНКЦИЯ ----------


def describe_image(image_path: str) -> str:
    """
    Описывает изображение через GigaChat Vision.
    Автоматически конвертирует неподдерживаемый формат в JPEG.
    """
    global vision_client

    headers = {"Authorization": f"Bearer {GIGACHAT_API_KEY}"}
    url = "https://gigachat.devices.sberbank.ru/api/v1/models"

    response = requests.get(url, headers=headers, verify=False)
    if response.status_code == 200:
        models = response.json()
        for m in models:
            print(m)
    else:
        print("Ошибка запроса моделей:", response.status_code, response.text)

    if not VISION_MODEL_ENABLED:
        return "Vision отключён"

    if vision_client is None:
        if not init_vision_model():
            return "Ошибка инициализации GigaChat"

    if not os.path.exists(image_path):
        return f"Файл не найден: {image_path}"

    file_id = None
    image_file = None
    try:
        # Подготовка изображения
        logger.info("Подготовка изображения для загрузки...")
        # image_file = prepare_image_for_upload(image_path)
        jpeg_buffer = convert_to_jpeg(image_path)

        # Загружаем файл в GigaChat
        uploaded_file = vision_client.upload_file(jpeg_buffer)
        file_id = uploaded_file.id_
        logger.info(f"Файл загружен (ID={file_id})")

        # Формируем сообщение
        messages = [
            {
                "role": "user",
                "content": "Опиши подробно, что изображено на фотографии. "
                "Укажи объекты, людей, действия, фон, цвета, эмоции, детали. "
                "Ответ дай на русском языке.",
                "attachments": [file_id],
            }
        ]

        # Отправляем запрос
        logger.info("Отправка запроса к Vision...")
        response = vision_client.chat({"messages": messages, "temperature": 0.1})
        text = response.choices[0].message.content
        return text

    except Exception as e:
        logger.error(f"Ошибка Vision: {e}")
        return f"Ошибка обработки изображения: {e}"

    finally:
        # Закрываем файл, если он был открыт
        if image_file and hasattr(image_file, "close"):
            image_file.close()

        # Удаляем файл с сервера
        if file_id:
            try:
                vision_client.delete_file(file_id)
                logger.info(f"Файл {file_id} удалён с сервера GigaChat")
            except Exception as e:
                logger.warning(f"Не удалось удалить файл с сервера: {e}")


# ---------- ФУНКЦИЯ СКАЧИВАНИЯ ----------


def download_image(url, save_path):
    """Скачивает изображение по URL."""
    try:
        response = requests.get(url, timeout=30, verify=False)
        if response.status_code != 200:
            logger.error(f"Ошибка скачивания: {response.status_code}")
            return False

        if not response.headers.get("content-type", "").startswith("image/"):
            logger.error("URL не ведет к изображению")
            return False

        with open(save_path, "wb") as f:
            f.write(response.content)

        logger.info(f"Изображение сохранено: {save_path}")
        return True

    except Exception as e:
        logger.error(f"Ошибка скачивания: {e}")
        return False
