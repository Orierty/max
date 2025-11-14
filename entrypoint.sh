#!/bin/bash
set -e


# Инициализация базы и таблиц
python init_db.py

# Запуск основного бота
python main.py
