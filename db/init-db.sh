#!/bin/bash
set -e

echo "Инициализация базы данных max_bot..."

psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "CREATE DATABASE max_bot;" 
