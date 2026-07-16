from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Mapped, mapped_column
from sqlalchemy import Column, Integer, String, Float, DateTime, Date, Boolean, Text, MetaData
from sqlalchemy import func
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

# ==========================================
# СЛОЙ PPL_LOOKUP (Накопительные реестры сущностей)
# ==========================================
class LookupDate(Base):
    __tablename__ = "date_unique"
    __table_args__ = {"schema": "ppl_lookup"}

    # Дата сама по себе уникальна, делаем её первичным ключом
    dt: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    # Техническое поле: когда дата впервые появилась в системе
    created_at: Mapped[datetime] = mapped_column(
        DateTime, 
        server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<LookupDate {self.dt}>"


class LookupQuery(Base):
    __tablename__ = "query_unique"
    __table_args__ = {"schema": "ppl_lookup"}

    # Текст запроса уникален. Ограничиваем первичным ключом, 
    # чтобы работал ON CONFLICT DO NOTHING
    query: Mapped[str] = mapped_column(Text, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, 
        server_default=func.now()
    )

    def __repr__(self) -> str:
        query_str = self.query[:20] if self.query else "None"
        return f"<LookupQuery '{query_str}...'>"


class LookupPage(Base):
    __tablename__ = "page_unique"
    __table_args__ = {"schema": "ppl_lookup"}

    # URL-путь уникален и является первичным ключом
    page_path: Mapped[str] = mapped_column(Text, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, 
        server_default=func.now()
    )

    def __repr__(self) -> str:
        path_str = self.page_path[:20] if self.page_path else "None"
        return f"<LookupPage '{path_str}...'>"
    
# ==========================================
# СЛОЙ DDM (Аналитические измерения и факты по твоей схеме)
# ==========================================

class QueryDimension(Base):
    __tablename__ = "query_dimension"
    __table_args__ = {"schema": "ddm"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    is_brand_query: Mapped[bool] = mapped_column(Boolean, nullable=True)
    whos_brand: Mapped[str] = mapped_column(Text, nullable=True)
    query_type: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PageDimension(Base):
    __tablename__ = "page_dimension"
    __table_args__ = {"schema": "ddm"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    page_path: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    site_section: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DateDimension(Base):
    __tablename__ = "date_dimension"
    __table_args__ = {"schema": "ddm"}

    dt: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    is_weekend: Mapped[bool] = mapped_column(Boolean, nullable=False)


class FctRowDemand(Base):
    """
    Таблица фактов спроса (Твоя идея!).
    Связывает ID исходной агрегированной строки со значением спроса.
    """
    __tablename__ = "fct_row_demand"
    __table_args__ = {"schema": "ddm"}

    # row_id — это id из таблицы ppl.webmaster_aggregated
    row_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    demand: Mapped[int] = mapped_column(Integer, nullable=False)


class FctPageImpressionsClicks(Base):
    """
    Атомарная таблица фактов показов и кликов.
    Зерно: Каждая строка — один конкретный показ или клик.
    """
    __tablename__ = "fct_page_impressions_clicks"
    __table_args__ = {"schema": "ddm"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Ссылка на исходную строку для сквозной аналитики и джойна со спросом
    row_id: Mapped[int] = mapped_column(Integer, nullable=False)
    
    dt: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    query_id: Mapped[int] = mapped_column(Integer, nullable=False)
    page_id: Mapped[int] = mapped_column(Integer, nullable=False)
    
    impression_position: Mapped[float] = mapped_column(Float, nullable=False)
    is_click: Mapped[bool] = mapped_column(Boolean, nullable=False)



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
            connection.execute(text("CREATE SCHEMA IF NOT EXISTS ppl_lookup;"))
            connection.commit()
        # Синхронизируем модели с удаленным движком
        Base.metadata.create_all(bind=remote_engine)
        print("Все таблицы на сервере успешно созданы!")