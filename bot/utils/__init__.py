"""
Утилиты для бота
"""
from .max_api import (
    get_updates,
    send_message,
    send_message_with_keyboard,
    answer_callback,
    send_location,
    get_bot_info,
    get_bot_link,
    forward_message,
    create_user_mention
)
from .vision import (
    init_vision_model,
    describe_image,
    download_image
)

__all__ = [
    'get_updates',
    'send_message',
    'send_message_with_keyboard',
    'answer_callback',
    'send_location',
    'get_bot_info',
    'get_bot_link',
    'forward_message',
    'create_user_mention',
    'init_vision_model',
    'describe_image',
    'download_image'
]
