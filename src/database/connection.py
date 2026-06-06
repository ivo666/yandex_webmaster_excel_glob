import os
import logging
from contextlib import contextmanager
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sshtunnel import SSHTunnelForwarder

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка .env с учетом структуры папок
current_file_dir = Path(__file__).resolve().parent
project_root = current_file_dir.parent.parent  # Поднимаемся до корня проекта '04 SQLA'
load_dotenv(dotenv_path=project_root / '.env')

# Считываем конфигурацию из .env
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
# Для SSH-туннеля целевой хост БД внутри сервера обычно localhost/127.0.0.1
DB_REMOTE_HOST = os.getenv("DB_HOST", "127.0.0.1") 
DB_REMOTE_PORT = int(os.getenv("DB_PORT", 5432))

SSH_HOST = os.getenv("SSH_HOST")
SSH_PORT = int(os.getenv("SSH_PORT", 22))
SSH_USER = os.getenv("SSH_USER")
SSH_PASSWORD = os.getenv("SSH_PASSWORD")


@contextmanager
def db_session_scope():
    """Контекстный менеджер, который автоматически открывает SSH-туннель,
    создает движок SQLAlchemy, выдает сессию и гарантированно всё закрывает в конце.
    """
    # 1. Настраиваем SSH-туннель
    tunnel = SSHTunnelForwarder(
        (SSH_HOST, SSH_PORT),
        ssh_username=SSH_USER,
        ssh_password=SSH_PASSWORD,
        remote_bind_address=(DB_REMOTE_HOST, DB_REMOTE_PORT)
    )
    
    logger.info(f" Попытка установить SSH-соединение с {SSH_HOST}...")
    tunnel.start()
    # Туннель открывает случайный свободный порт на вашем ЛОКАЛЬНОМ ПК (например, 62345)
    # и перенаправляет трафик через SSH на удаленный порт 5432 базы данных
    local_port = tunnel.local_bind_port
    logger.info(f" SSH-туннель успешно поднят на локальном порту: {local_port}")
    
    # 2. Формируем строку подключения к ЛОКАЛЬНОМУ концу туннеля
    database_url = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@127.0.0.1:{local_port}/{DB_NAME}"
    
    # 3. Инициализируем SQLAlchemy
    engine = create_engine(database_url, echo=False) # Поставьте True, если нужны логи SQL
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    
    session = SessionLocal()
    try:
        # Отдаем сессию и сам engine (может пригодиться для metadata) наружу в блок with
        yield session, engine
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f" Ошибка внутри сессии БД: {e}")
        raise e
    finally:
        session.close()
        engine.dispose()
        tunnel.stop()
        logger.info(" SSH-туннель и соединения с БД успешно закрыты.")


def test_remote_connection():
    """Тестовая функция для проверки удаленного коннекта"""
    print("\n--- Проверка удаленного подключения через SSH ---")
    try:
        with db_session_scope() as (session, engine):
            # Проверяем работу через выполнение простого запроса
            result = session.execute(text("SELECT version();")).fetchone()
            print(f"\n УСПЕШНО! Ответ от удаленной БД:")
            print(f"Версия PostgreSQL: {result[0]}\n")
    except Exception as e:
        print(f"\n НЕ УДАЛОСЬ подключиться к удаленному серверу.")
        logger.error(f"Детали ошибки: {e}")


if __name__ == "__main__":
    test_remote_connection()