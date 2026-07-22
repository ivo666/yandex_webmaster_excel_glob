""" Модуль для загрузки данных в ddm/query_dimension
Должен обновлять данные в целевой таблице """

import polars as pl
import logging
from sqlalchemy import insert

from src.database.connection import db_session_scope
from src.models.models import QueryDimension  # Модель queries для слоя DDM

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DDMQueries:
    def __init__(self):
        self.logger = logger
        self.df_lookup = None
        self.df_ddm = None
        self.df_unique = None
        self.df_final = None

    def get_lookup_queries(self) -> pl.DataFrame:
        """ Получаем список запросов из ppl_lookup.query_unique """
        try:
            with db_session_scope() as (session, engine):
                self.logger.info("🔄 SSH-туннель поднят. Подключаемся к базе...")
                with engine.connect() as conn:
                    query = "SELECT query FROM ppl_lookup.query_unique"
                    self.logger.info("📥 Выкачиваем данные из ppl_lookup/query_unique в Polars...")
                    self.df_lookup = pl.read_database(query=query, connection=conn)
                    
                self.logger.info(f"✅ Данные успешно скачаны. Размер: {self.df_lookup.shape}")
                return self.df_lookup
        except Exception as e:
            self.logger.error(f"🔴 Ошибка получения данных из ppl_lookup-слоя: {e}")
            raise

    def get_ddm_queries(self) -> pl.DataFrame:
        """ Получаем список уже существующих запросов в query_dimension """
        try:
            with db_session_scope() as (session, engine):
                self.logger.info("🔄 SSH-туннель поднят. Подключаемся к базе...")
                with engine.connect() as conn:
                    query = "SELECT query FROM ddm.query_dimension"
                    self.logger.info("📥 Выкачиваем данные из ddm.query_dimension в Polars...")
                    self.df_ddm = pl.read_database(query=query, connection=conn)
                    
            # ИСПРАВЛЕНО: Явно приводим колонку к String на случай, если таблица пустая
            if "query" in self.df_ddm.columns:
                self.df_ddm = self.df_ddm.with_columns(pl.col("query").cast(pl.String))
                    
            self.logger.info(f"✅ Данные успешно скачаны. Размер: {self.df_ddm.shape}")
            return self.df_ddm
        except Exception as e:
            self.logger.error(f"🔴 Ошибка получения данных из ddm.query_dimension: {e}")
            raise


    def get_unique_query(self) -> pl.DataFrame:
        """ Очищаем загружаемые запросы от уже существующих """
        if self.df_lookup is None:
            self.logger.warning("⚠️ Нет данных для обработки. Сначала вызовите get_lookup_queries()")
            return 
        
        try:
            self.df_unique = self.df_lookup.join(self.df_ddm, on="query", how="anti")
            self.logger.info(f"Запросы для вставки очищены: {self.df_unique.height}")
            return self.df_unique
        except Exception as e:
            self.logger.error(f"Ошибка очистки запросов для вставки: {e}")
            raise
    
    def add_query_params(self) -> pl.DataFrame:
        """ Добавляем параметры к запросам (заглушка) """
        if self.df_unique is None or self.df_unique.is_empty():
            self.logger.warning("⚠️ Нет данных для обработки. Сначала вызовите get_unique_query()")
            return 
        
        try:
            # ИСПРАВЛЕНО: Явное создание пустых колонок нужного типа в Polars
            self.df_final = self.df_unique.with_columns([
                pl.lit(None, dtype=pl.Boolean).alias("is_brand_query"),
                pl.lit(None, dtype=pl.String).alias("whos_brand"),
                pl.lit(None, dtype=pl.String).alias("query_type")
            ])
            self.logger.info("Успешное добавление параметров к Поисковому Запросу")
            return self.df_final
        except Exception as e:
            self.logger.error(f"Ошибка добавления параметров к Поисковому Запросу: {e}")
            raise

    def load_ddm_queries(self):
        """ Функция загрузки запросов в таблицу query_dimension """
        if self.df_final is None or self.df_final.height == 0:
            self.logger.warning("⚠️ Нет новых данных для вставки.")
            return

        try: 
            records = self.df_final.to_dicts()
            self.logger.info(f"Параметры query_dimension успешно подготовлены: {len(records)} строк.")
            
            with db_session_scope() as (session, engine):
                # ИСПРАВЛЕНО: Использование стандартного инсерта модели
                stmt = insert(QueryDimension).values(records)
                session.execute(stmt)
                session.commit()
                self.logger.info("🎉 Данные в ddm.query_dimension успешно обновлены.")
        except Exception as e:
            self.logger.error(f"🔴 Ошибка обновления ddm.query_dimension: {e}")
            raise

if __name__ == "__main__":
    loader = DDMQueries()
    loader.get_lookup_queries()
    loader.get_ddm_queries()
    loader.get_unique_query()
    loader.add_query_params()
    loader.load_ddm_queries()
