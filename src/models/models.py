from sqlalchemy import create_engine, text, inspect, ForeignKey
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Mapped, mapped_column
from sqlalchemy import Column, Integer, String, Float, DateTime, Date, Boolean, Text, MetaData
from sqlalchemy import func
from datetime import datetime
import os
import logging
from dotenv import load_dotenv

# Настройка базового логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Base(DeclarativeBase):
    pass

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
        date_str = self.dt.strftime('%Y-%m-%d') if self.dt else "None"
        query_str = self.query[:15] if self.query else "None"
        return f"<Webm {date_str} | Query: {query_str}... | Clicks: {self.clicks}>"


# ==========================================
# СЛОЙ PPL (Обработанные данные)
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

    dt: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<LookupDate {self.dt}>"


class LookupQuery(Base):
    __tablename__ = "query_unique"
    __table_args__ = {"schema": "ppl_lookup"}

    query: Mapped[str] = mapped_column(Text, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        query_str = self.query[:20] if self.query else "None"
        return f"<LookupQuery '{query_str}...'>"


class LookupPage(Base):
    __tablename__ = "page_unique"
    __table_args__ = {"schema": "ppl_lookup"}

    page_path: Mapped[str] = mapped_column(Text, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        path_str = self.page_path[:20] if self.page_path else "None"
        return f"<LookupPage '{path_str}...'>"


# ==========================================
# СЛОЙ DDM (Аналитические измерения и факты)
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
    Таблица фактов спроса.
    Связана по primary_key с row_id из ppl.webmaster_aggregated
    """
    __tablename__ = "fct_row_demand"
    __table_args__ = {"schema": "ddm"}

    row_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    demand: Mapped[int] = mapped_column(Integer, nullable=False)


class FctPageImpressionsClicks(Base):
    """
    Атомарная таблица фактов показов и кликов с внешними ключами.
    """
    __tablename__ = "fct_page_impressions_clicks"
    __table_args__ = {"schema": "ddm"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    row_id: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Внешние ключи на аналитические измерения (DDM)
    dt: Mapped[datetime.date] = mapped_column(Date, ForeignKey("ddm.date_dimension.dt"), nullable=False)
    query_id: Mapped[int] = mapped_column(Integer, ForeignKey("ddm.query_dimension.id"), nullable=False)
    page_id: Mapped[int] = mapped_column(Integer, ForeignKey("ddm.page_dimension.id"), nullable=False)
    
    impression_position: Mapped[float] = mapped_column(Float, nullable=False)
    is_click: Mapped[bool] = mapped_column(Boolean, nullable=False)


# ==========================================
# ИНИЦИАЛИЗАЦИЯ НА СЕРВЕРЕ
# ==========================================
if __name__ == "__main__":
    from src.database.connection import db_session_scope

    # Запускаем через контекстный менеджер SSH-туннеля
    with db_session_scope() as (session, remote_engine):
        print("Создаем необходимые схемы на УДАЛЕННОМ сервере...")
        with remote_engine.connect() as connection:
            connection.execute(text("CREATE SCHEMA IF NOT EXISTS rdl;"))
            connection.execute(text("CREATE SCHEMA IF NOT EXISTS ppl;"))
            connection.execute(text("CREATE SCHEMA IF NOT EXISTS ppl_lookup;"))
            connection.execute(text("CREATE SCHEMA IF NOT EXISTS ddm;")) # Добавлена схема ddm
            connection.commit()
        
        print("Синхронизируем модели и создаем таблицы во всех схемах...")
        Base.metadata.create_all(bind=remote_engine)
        print("Все таблицы на сервере fzhm_webm_orm успешно созданы!")
