import os
import sys
import logging
from dotenv import load_dotenv
from sshtunnel import SSHTunnelForwarder
from sqlalchemy import create_engine

# Инициализируем логгер
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("DDM_Initializer")

# Загружаем переменные из .env
load_dotenv()

# Импортируем наш Base и новые модели
from src.models.models import Base, QueryDimension, PageDimension, DateDimension, FctRowDemand, FctPageImpressionsClicks

logger.info("=== Запуск процесса инициализации таблиц DDM ===")

# Настройки для SSH
SSH_HOST = os.getenv("SSH_HOST")
SSH_PORT = int(os.getenv("SSH_PORT", 22))
SSH_USER = os.getenv("SSH_USER")
SSH_PASSWORD = os.getenv("SSH_PASSWORD")

# Настройки для БД
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

if not all([SSH_HOST, SSH_USER, DB_NAME, DB_PASSWORD]):
    logger.error("Ошибка: Не все переменные окружения найдены в .env!")
    sys.exit(1)

try:
    # 1. Поднимаем SSH-туннель
    logger.info(f"Поднимаем SSH-туннель к {SSH_HOST}...")
    with SSHTunnelForwarder(
        (SSH_HOST, SSH_PORT),
        ssh_username=SSH_USER,
        ssh_password=SSH_PASSWORD,
        remote_bind_address=(DB_HOST, DB_PORT)
    ) as tunnel:
        
        logger.info(f"SSH-туннель успешно открыт на локальном порту: {tunnel.local_bind_port}")
        
        # 2. Формируем временный URL для engine внутри туннеля
        db_url = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@127.0.0.1:{tunnel.local_bind_port}/{DB_NAME}"
        engine = create_engine(db_url, echo=False)
        
        # 3. Создаем только те таблицы, которых еще нет в БД
        logger.info("Сканируем базу и создаем новые таблицы слоя ddm...")
        
        # Таблицы создаются на основе метаданных классов, импортированных выше
        Base.metadata.create_all(engine)
        
        logger.info("🎉 Все новые таблицы в схеме ddm успешно созданы на удаленном сервере!")

except Exception as e:
    logger.error(f"🔴 Критическая ошибка при создании таблиц: {e}")
    sys.exit(1)
