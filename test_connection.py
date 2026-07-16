import os
import sys
from dotenv import load_dotenv
from sshtunnel import SSHTunnelForwarder
from sqlalchemy import create_engine, text

# Загружаем переменные из .env
load_dotenv()

print("--- Проверка конфигурации .env ---")
ssh_host = os.getenv("SSH_HOST")
ssh_user = os.getenv("SSH_USER")
db_name = os.getenv("DB_NAME")

print(f"SSH Host: {ssh_host}")
print(f"SSH User: {ssh_user}")
print(f"DB Name: {db_name}")

if not all([ssh_host, ssh_user, db_name]):
    print("Ошибка: Не все переменные окружения загружены! Проверьте файл .env")
    sys.exit(1)

print("\n--- Попытка установить соединение ---")

try:
    # 1. Настройка и запуск SSH-туннеля
    with SSHTunnelForwarder(
        (os.getenv("SSH_HOST"), int(os.getenv("SSH_PORT", 22))),
        ssh_username=os.getenv("SSH_USER"),
        ssh_password=os.getenv("SSH_PASSWORD"),
        remote_bind_address=(os.getenv("DB_HOST", "127.0.0.1"), int(os.getenv("DB_PORT", 5432)))
    ) as tunnel:
        
        print(f"Успешно! SSH-туннель открыт на локальном порту: {tunnel.local_bind_port}")
        
        # 2. Формирование строки подключения к БД через локальный порт туннеля
        db_url = (
            f"postgresql+psycopg2://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
            f"@127.0.0.1:{tunnel.local_bind_port}/{os.getenv('DB_NAME')}"
        )
        
        engine = create_engine(db_url)
        
        # 3. Тестовый запрос к PostgreSQL
        with engine.connect() as connection:
            result = connection.execute(text("SELECT version();"))
            db_version = result.fetchone()[0]
            print(f"Успешно! Подключение к PostgreSQL установлено.")
            print(f"Версия СУБД: {db_version}")
            print("\nТест пройден на 100%! Всё настроено верно.")

except Exception as e:
    print(f"\nПроизошла ошибка при подключении:\n{e}")
