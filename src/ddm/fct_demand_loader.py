""" Модуль для загрузки данных в ddm.fct_row_demand """
""" Запуск из корня: python -m src.ddm.fct_demand_loader """

import polars as pl
import logging
from sqlalchemy import insert

from src.database.connection import db_session_scope
from src.models.models import FctRowDemand  # Модель фактов спроса из DDM

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DDMDemand:
    def __init__(self):
        self.logger = logger
        self.df_ppl = None
        self.df_fct = None
        self.df_final = None

    def get_ppl_demand(self) -> pl.DataFrame:
        """ Извлекаем id и demand из слоя предобработки ppl.webmaster_aggregated """
        try:
            with db_session_scope() as (session, engine):
                self.logger.info("🔄 SSH-туннель поднят. Подключаемся к базе...")
                with engine.connect() as conn:
                    # Переименовываем id в row_id для соответствия целевой таблице
                    query = "SELECT id AS row_id, demand FROM ppl.webmaster_aggregated"
                    self.logger.info("📥 Выкачиваем данные из ppl.webmaster_aggregated в Polars...")
                    self.df_ppl = pl.read_database(query=query, connection=conn)
                    
            self.logger.info(f"✅ Данные из PPL скачаны. Размер: {self.df_ppl.shape}")
            return self.df_ppl
        except Exception as e:
            self.logger.error(f"🔴 Ошибка получения данных из ppl-слоя: {e}")
            raise

    def get_existing_fct_demand(self) -> pl.DataFrame:
        """ Получаем список уже загруженных row_id из таблицы фактов спроса """
        try:
            with db_session_scope() as (session, engine):
                self.logger.info("🔄 SSH-туннель поднят. Подключаемся к базе...")
                with engine.connect() as conn:
                    query = "SELECT row_id FROM ddm.fct_row_demand"
                    self.logger.info("📥 Выкачиваем row_id из ddm.fct_row_demand в Polars...")
                    self.df_fct = pl.read_database(query=query, connection=conn)
                    
            # Твой любимый фикс: страхуем Polars от пустоты на первом запуске
            if "row_id" in self.df_fct.columns:
                self.df_fct = self.df_fct.with_columns(pl.col("row_id").cast(pl.Int32))
                    
            self.logger.info(f"✅ Данные из FCT скачаны. Размер: {self.df_fct.shape}")
            return self.df_fct
        except Exception as e:
            self.logger.error(f"🔴 Ошибка получения данных из ddm.fct_row_demand: {e}")
            raise

    def filter_new_demand(self) -> pl.DataFrame:
        """ Очищаем данные от уже существующих row_id (идемпотентность) """
        if self.df_ppl is None:
            self.logger.warning("⚠️ Нет данных для обработки. Сначала вызовите get_ppl_demand()")
            return 
        
        try:
            # Используем анти-джойн по row_id
            self.df_final = self.df_ppl.join(self.df_fct, on="row_id", how="anti")
            self.logger.info(f"Строки спроса для вставки очищены. К записи: {self.df_final.height}")
            return self.df_final
        except Exception as e:
            self.logger.error(f"Ошибка фильтрации новых строк спроса: {e}")
            raise

    def load_ddm_demand(self):
        """ Выполняем пакетную вставку новых строк спроса в СУБД """
        if self.df_final is None or self.df_final.height == 0:
            self.logger.warning("⚠️ Нет новых строк спроса для вставки.")
            return

        try: 
            records = self.df_final.to_dicts()
            self.logger.info(f"Данные fct_row_demand успешно подготовлены: {len(records)} строк.")
            
            with db_session_scope() as (session, engine):
                stmt = insert(FctRowDemand).values(records)
                session.execute(stmt)
                session.commit()
                self.logger.info("🎉 Таблица ddm.fct_row_demand успешно обновлена!")
        except Exception as e:
            self.logger.error(f"🔴 Ошибка записи в ddm.fct_row_demand: {e}")
            raise

if __name__ == "__main__":
    loader = DDMDemand()
    loader.get_ppl_demand()
    loader.get_existing_fct_demand()
    loader.filter_new_demand()
    loader.load_ddm_demand()
