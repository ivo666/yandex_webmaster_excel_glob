""" Модуль для загрузки данных в ddm/date_dimension
Должен обновлять данные в целевой таблице """

import polars as pl
import logging
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.database.connection import db_session_scope
from src.models.models import DateDimension  # Модель dates для слоя DDM

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DDMDates:
    def __init__(self):
        self.logger = logger
        self.df_lookup = None

    def get_lookup_dates(self) -> pl.DataFrame:
        """ Получаем данные из ppl_lookup.date_unique"""
        try:
            with db_session_scope() as (session, engine):
                self.logger.info("🔄 SSH-туннель поднят. Подключаемся к базе...")
                
                with engine.connect() as conn:
                    query = "SELECT dt FROM ppl_lookup.date_unique"
                    self.logger.info("📥 Выкачиваем данные из ppl_lookup/date_unique в Polars...")
                    self.df_lookup = pl.read_database(query=query, connection=conn)
                    
                self.logger.info(f"✅ Данные успешно скачаны. Размер: {self.df_lookup.shape}")
                return self.df_lookup
                
        except Exception as e:
            self.logger.error(f"🔴 Ошибка получения данных из ppl_lookup-слоя: {e}")
            raise
    
    def load_ddm_dates(self):
        """ Функция загрузки дат в таблицу date_dimension
        Должны записываться только новые даты. """
        if self.df_lookup is None or self.df_lookup.height == 0:
            self.logger.warning("⚠️ Нет данных для обработки. Сначала вызовите get_lookup_dates()")
            return

        try:
            self.logger.info("🛠 Расчет календарных признаков на Polars...")
            df_features = self.df_lookup.with_columns([
                pl.col("dt").dt.year().alias("year"),
                pl.col("dt").dt.month().alias("month"),
                pl.col("dt").dt.weekday().alias("day_of_week"),
                # В Polars weekday возвращает 1 (понедельник) ... 7 (воскресенье)
                pl.col("dt").dt.weekday().is_in([6, 7]).alias("is_weekend")
            ])
            
            records = df_features.to_dicts()
            if not records:
                self.logger.info("ℹ️ Список записей пуст.")
                return
                
            self.logger.info(f"Параметры date_dimension успешно подготовлены: {len(records)} строк.")

            with db_session_scope() as (session, engine):
                # Создаем базовый insert
                stmt = pg_insert(DateDimension).values(records)
                # Добавляем инструкцию "если такая дата уже есть — ничего не делать"
                stmt = stmt.on_conflict_do_nothing(index_elements=['dt'])
                
                session.execute(stmt)
                session.commit()
                self.logger.info("🎉 Данные в ddm/date_dimension успешно обновлены.")

        except Exception as e:
            self.logger.error(f"🔴 Ошибка обновления ddm/date_dimension: {e}")
            raise

if __name__ == "__main__":
    loader = DDMDates()
    loader.get_lookup_dates()
    loader.load_ddm_dates()
