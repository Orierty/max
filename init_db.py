import os
import time
import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "postgres")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "max_bot")


def wait_for_postgres():
    """Ждём, пока Postgres поднимется."""
    while True:
        try:
            conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=DB_PASSWORD,
                database="postgres",
            )
            conn.close()
            print("Postgres готов!")
            return
        except psycopg2.OperationalError:
            print("Ожидание базы данных...")
            time.sleep(2)


def create_database():
    """Создаём базу, если она ещё не создана."""
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database="postgres",
    )
    conn.autocommit = True
    cur = conn.cursor()

    try:
        cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DB_NAME)))
        print(f"База данных {DB_NAME} создана!")
    except psycopg2.errors.DuplicateDatabase:
        print(f"База {DB_NAME} уже существует — пропускаем.")

    cur.close()
    conn.close()


def tables_exist():
    """Проверяем, существует ли хотя бы одна таблица из схемы."""
    required_tables = [
        "users",
        "requests",
        "chat_rooms",
        "volunteers",
        "wave_queue",
    ]

    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
    )
    cur = conn.cursor()

    cur.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema='public';
        """
    )
    existing_tables = {row[0] for row in cur.fetchall()}

    cur.close()
    conn.close()

    if existing_tables:
        print(f"Найдены существующие таблицы: {existing_tables}")
    return any(tbl in existing_tables for tbl in required_tables)


def init_tables():
    """Создаём таблицы по schema.sql, если их нет."""
    if tables_exist():
        print("Таблицы уже существуют — пропускаем schema.sql.")
        return

    print("Схема пуста — создаём таблицы...")

    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
    )
    cur = conn.cursor()

    with open("db/schema.sql", "r", encoding="utf-8") as f:
        schema = f.read()
        cur.execute(schema)

    conn.commit()
    cur.close()
    conn.close()

    print("Таблицы созданы.")


if __name__ == "__main__":
    wait_for_postgres()
    create_database()
    init_tables()
