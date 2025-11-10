"""
Функции для работы с моделью распознавания изображений Qwen2-VL
"""
import os
import logging
import requests

from bot.config import VISION_MODEL_ENABLED, MODELS_DIR

logger = logging.getLogger(__name__)

# Глобальные переменные для модели
vision_model = None
vision_processor = None

# Импортируем AI библиотеки только если нейронка включена
if VISION_MODEL_ENABLED:
    try:
        import torch
        from PIL import Image
        from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
        from qwen_vl_utils import process_vision_info
        logger.info("AI библиотеки успешно загружены")
    except ImportError as e:
        logger.error(f"Ошибка импорта AI библиотек: {e}")
        logger.error("Установите зависимости: pip install torch transformers pillow qwen-vl-utils")
else:
    logger.info("Vision Model отключена (VISION_MODEL_ENABLED=false), AI библиотеки не загружаются")

def init_vision_model():
    """Инициализирует модель Qwen2-VL для распознавания изображений"""
    global vision_model, vision_processor

    try:
        # Путь к папке с моделями в рабочей директории
        models_dir = os.path.join(os.path.dirname(__file__), "..", "..", MODELS_DIR)
        os.makedirs(models_dir, exist_ok=True)

        # Пробуем использовать GPTQ модель, если установлен auto-gptq
        try:
            import auto_gptq
            model_name = "Qwen/Qwen2-VL-2B-Instruct-GPTQ-Int4"
            local_model_path = os.path.join(models_dir, "Qwen2-VL-2B-Instruct-GPTQ-Int4")
            logger.info("Загрузка GPTQ модели Qwen2-VL-2B-Instruct-GPTQ-Int4...")
        except ImportError:
            # Если auto-gptq не установлен, используем обычную модель
            model_name = "Qwen/Qwen2-VL-2B-Instruct"
            local_model_path = os.path.join(models_dir, "Qwen2-VL-2B-Instruct")
            logger.info("auto-gptq не установлен, используем стандартную модель Qwen2-VL-2B-Instruct...")
            logger.warning("Для экономии памяти рекомендуется установить: pip install auto-gptq")

        # Проверяем, есть ли уже локальная модель
        if os.path.exists(local_model_path) and os.path.isdir(local_model_path):
            logger.info(f"Используем локальную модель из {local_model_path}")
            model_source = local_model_path
        else:
            logger.info(f"Модель будет скачана из HuggingFace и сохранена в {local_model_path}")
            model_source = model_name

        # Загружаем процессор
        vision_processor = AutoProcessor.from_pretrained(
            model_source,
            trust_remote_code=True,
            cache_dir=models_dir if model_source == model_name else None
        )

        # Загружаем модель
        # Используем float16 если доступна GPU, иначе float32 для CPU
        dtype = torch.float16 if torch.cuda.is_available() else torch.float32

        vision_model = Qwen2VLForConditionalGeneration.from_pretrained(
            model_source,
            torch_dtype=dtype,
            device_map="auto",
            trust_remote_code=True,
            cache_dir=models_dir if model_source == model_name else None
        )

        # Сохраняем модель локально, если она была скачана из HuggingFace
        if model_source == model_name:
            logger.info(f"Сохраняем модель локально в {local_model_path}...")
            vision_model.save_pretrained(local_model_path)
            vision_processor.save_pretrained(local_model_path)
            logger.info("Модель успешно сохранена локально")

        device = next(vision_model.parameters()).device
        logger.info(f"Модель Qwen2-VL успешно загружена на устройство: {device}")
        return True

    except Exception as e:
        logger.error(f"Ошибка при загрузке модели Qwen2-VL: {e}", exc_info=True)
        return False

def describe_image(image_path):
    """Описывает изображение на русском языке с помощью Qwen2-VL"""
    global vision_model, vision_processor

    # Если нейронка выключена, возвращаем заглушку
    if not VISION_MODEL_ENABLED:
        logger.info("Vision Model отключена, возвращаем заглушку")
        return ("🔧 Режим заглушки (Vision Model отключена)\n\n"
                "На изображении видно: [здесь было бы описание от нейронки]\n\n"
                "Для включения нейронки установите VISION_MODEL_ENABLED=true в файле .env")

    # Если модель ещё не загружена, загружаем её
    if vision_model is None or vision_processor is None:
        logger.info("Модель не загружена, инициализируем...")
        if not init_vision_model():
            return "Ошибка: не удалось загрузить модель для распознавания изображений."

    try:
        # Открываем изображение
        image = Image.open(image_path).convert('RGB')

        # Формируем запрос на русском языке
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "image": image_path,
                    },
                    {
                        "type": "text",
                        "text": "Опиши подробно что изображено на этой фотографии на русском языке. Будь максимально детальным и точным в описании."
                    },
                ],
            }
        ]

        # Подготавливаем текст
        text = vision_processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )

        # Обрабатываем изображение
        image_inputs, video_inputs = process_vision_info(messages)

        # Подготавливаем входные данные
        inputs = vision_processor(
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        )

        device = next(vision_model.parameters()).device
        inputs = inputs.to(device)

        # Генерируем описание
        logger.info("Генерация описания изображения...")
        with torch.no_grad():
            generated_ids = vision_model.generate(
                **inputs,
                max_new_tokens=512,
                temperature=0.7,
                do_sample=True
            )

        # Декодируем результат
        generated_ids_trimmed = [
            out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        output_text = vision_processor.batch_decode(
            generated_ids_trimmed,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False
        )[0]

        logger.info("Описание изображения успешно сгенерировано")
        return output_text

    except Exception as e:
        logger.error(f"Ошибка при обработке изображения: {e}", exc_info=True)
        return f"Ошибка при обработке изображения: {str(e)}"

def download_image(url, save_path):
    """Скачивает изображение по URL"""
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            with open(save_path, 'wb') as f:
                f.write(response.content)
            logger.info(f"Изображение сохранено: {save_path}")
            return True
        else:
            logger.error(f"Ошибка скачивания изображения: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"Ошибка при скачивании изображения: {e}")
        return False
