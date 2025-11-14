
import psycopg2
import os

from dotenv import load_dotenv

load_dotenv()

def init_database():
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=int(os.getenv('DB_PORT', 5432)),
            database=os.getenv('DB_NAME', 'max_bot'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD')
        )
        cur = conn.cursor()

        with open('db/schema.sql', 'r', encoding='utf-8') as f:
            schema_sql = f.read()

        print("создание таблиц...")
        cur.execute(schema_sql)
        conn.commit()

        print("готово")
        print("\nмзданные таблицы:")

        cur.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)

        tables = cur.fetchall()
        for table in tables:
            print(f"  - {table[0]}")

        cur.close()
        conn.close()

    except Exception as e:
        print(f"ошибка: {e}")
        raise

if __name__ == "__main__":
    init_database()
