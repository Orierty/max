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
            break
        except psycopg2.OperationalError:
            print("Ожидание базы данных...")
            time.sleep(2)


def create_database():
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
        print(f"База {DB_NAME} уже существует, пропускаем создание")
    cur.close()
    conn.close()


def init_tables():
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, database=DB_NAME
    )
    cur = conn.cursor()
    with open("db/schema.sql", "r", encoding="utf-8") as f:
        cur.execute(f.read())
    conn.commit()
    cur.close()
    conn.close()
    print("Таблицы созданы!")


if __name__ == "__main__":
    wait_for_postgres()
    create_database()
    init_tables()
