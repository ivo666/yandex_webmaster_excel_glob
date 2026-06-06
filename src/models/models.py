from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Mapped, mapped_column
from sqlalchemy import Column, Integer, String, Float, DateTime, Date, Boolean, Text, MetaData
from datetime import datetime
import os
import logging
from dotenv import load_dotenv

# Определяем путь к папке, где лежит этот файл (src/models)
current_dir = os.path.dirname(os.path.abspath(__file__))

# Поднимаемся на два уровня вверх: сначала в src, потом в корень проекта
project_root = os.path.dirname(os.path.dirname(current_dir))

# Собираем точный путь к .env в корне
dotenv_path = os.path.join(project_root, '.env')

# Загружаем переменные строго по этому пути
load_dotenv(dotenv_path=dotenv_path)

DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")  
DB_NAME = os.getenv("DB_NAME", "postgres")

# Строка подключения (psycopg2)
DATABASE_URL = f'postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'

# Создаем движок 
# echo=True - показывает SQL запросы (полезно для обучения)
engine = create_engine(DATABASE_URL, echo=True)

class Base(DeclarativeBase):
    pass

# Настройка базового логирования, чтобы видеть ошибки, если они возникнут
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==========================================
# СЛОЙ RDL (Сырые данные)
# ==========================================
class Webm(Base):
    __tablename__ = "webm_excel"
    __table_args__ = {"schema": "rdl"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dt: Mapped[datetime.date] = mapped_column(Date, nullable=False) 
    page_path: Mapped[str] = mapped_column(Text, nullable=True)
    query: Mapped[str] = mapped_column(Text, nullable=True)
    demand: Mapped[int] = mapped_column(Integer, nullable=True)
    impressions: Mapped[int] = mapped_column(Integer, nullable=True)
    position: Mapped[float] = mapped_column(Float, nullable=True)
    clicks: Mapped[int] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        # Исправлено self.date -> self.dt
        date_str = self.dt.strftime('%Y-%m-%d') if self.dt else "None"
        query_str = self.query[:15] if self.query else "None"
        return f"<Webm {date_str} | Query: {query_str}... | Clicks: {self.clicks}>"


# ==========================================
# СЛОЙ PPL (Обработанные данные / Витрины)
# ==========================================
class WebmAgg(Base):
    __tablename__ = "webmaster_aggregated"
    __table_args__ = {"schema": "ppl"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dt: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=True)
    page_path: Mapped[str] = mapped_column(Text, nullable=True)
    demand: Mapped[int] = mapped_column(Integer, nullable=True)
    impressions: Mapped[int] = mapped_column(Integer, nullable=True)
    position: Mapped[float] = mapped_column(Float, nullable=True)
    clicks: Mapped[int] = mapped_column(Integer, nullable=True)

# Этот класс пранируется перенести в следующий ORM-слоей
# class WebmPos(Base):
    # __tablename__ = "webmaster_positions"
    # __table_args__ = {"schema": "ppl"}

    # id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # impressions: Mapped[int] = mapped_column(Integer, nullable=True)
    # impression_order: Mapped[int] = mapped_column(Integer, nullable=True)
    # click: Mapped[bool] = mapped_column(Boolean, nullable=True)


# ==========================================
# ПРОВЕРКА ПОДКЛЮЧЕНИЯ И СИНХРОНИЗАЦИЯ
# ==========================================
def test_connection():
    print("\n--- Проверка подключения и создание схем ---")
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            print(" Успешно! Подключение к базе установлено.")
            
            # Автоматически создаем ОБЕ схемы, если их нет
            connection.execute(text("CREATE SCHEMA IF NOT EXISTS rdl;"))
            connection.execute(text("CREATE SCHEMA IF NOT EXISTS ppl;"))
            connection.commit()
            print(" Схемы 'rdl' и 'ppl' проверены/созданы.")
        
        print("\n--- Синхронизация структуры таблиц ---")
        # SQLAlchemy сама пройдет по всем классам (Webm, WebmAgg, WebmPos) и создаст их
        Base.metadata.create_all(bind=engine)
        print(" Успешно! Все таблицы во всех слоях созданы.")
            
    except Exception as e:
        print(" Произошла ошибка!")
        logger.error(f"Детали: {e}")

if __name__ == "__main__":
    from src.database.connection import db_session_scope

    with db_session_scope() as (session, remote_engine):
        print("Создаем схемы и таблицы на УДАЛЕННОМ сервере...")
        with remote_engine.connect() as connection:
            connection.execute(text("CREATE SCHEMA IF NOT EXISTS rdl;"))
            connection.execute(text("CREATE SCHEMA IF NOT EXISTS ppl;"))
            connection.commit()
        # Синхронизируем модели с удаленным движком
        Base.metadata.create_all(bind=remote_engine)
        print("Все таблицы на сервере успешно созданы!")