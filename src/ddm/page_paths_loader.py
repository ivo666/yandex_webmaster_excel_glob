""" Модуль для загрузки данных в ddm/page_dimension
Должен обновлять данные в целевой таблице """

import polars as pl
import logging
from sqlalchemy import insert

from src.database.connection import db_session_scope
from src.models.models import PageDimension  # Модель страниц для слоя DDM

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DDMPages:
    def __init__(self):
        self.logger = logger
        self.df_lookup = None
        self.df_ddm = None
        self.df_unique = None
        self.df_final = None

    def get_lookup_pages(self) -> pl.DataFrame:
        """ Получаем список страниц из ppl_lookup.page_unique """
        try:
            with db_session_scope() as (session, engine):
                self.logger.info("🔄 SSH-туннель поднят. Подключаемся к базе...")
                with engine.connect() as conn:
                    query = "SELECT page_path FROM ppl_lookup.page_unique"
                    self.logger.info("📥 Выкачиваем данные из ppl_lookup/page_unique в Polars...")
                    self.df_lookup = pl.read_database(query=query, connection=conn)
                    
                self.logger.info(f"✅ Данные успешно скачаны. Размер: {self.df_lookup.shape}")
                return self.df_lookup
        except Exception as e:
            self.logger.error(f"🔴 Ошибка получения данных из ppl_lookup-слоя: {e}")
            raise

    def get_ddm_pages(self) -> pl.DataFrame:
        """ Получаем список уже существующих страниц в page_dimension """
        try:
            with db_session_scope() as (session, engine):
                self.logger.info("🔄 SSH-туннель поднят. Подключаемся к базе...")
                with engine.connect() as conn:
                    query = "SELECT page_path FROM ddm.page_dimension"
                    self.logger.info("📥 Выкачиваем данные из ddm.page_dimension в Polars...")
                    self.df_ddm = pl.read_database(query=query, connection=conn)
                    
            # ИСПРАВЛЕНО: Явно приводим колонку к String на случай пустой таблицы
            if "page_path" in self.df_ddm.columns:
                self.df_ddm = self.df_ddm.with_columns(pl.col("page_path").cast(pl.String))
                    
            self.logger.info(f"✅ Данные успешно скачаны. Размер: {self.df_ddm.shape}")
            return self.df_ddm
        except Exception as e:
            self.logger.error(f"🔴 Ошибка получения данных из ddm.page_dimension: {e}")
            raise


    def get_unique_pages(self) -> pl.DataFrame:
        """ Очищаем загружаемые страницы от уже существующих """
        if self.df_lookup is None:
            self.logger.warning("⚠️ Нет данных для обработки. Сначала вызовите get_lookup_pages()")
            return 
        
        try:
            # Исправлено на anti
            self.df_unique = self.df_lookup.join(self.df_ddm, on="page_path", how="anti")
            self.logger.info(f"Страницы для вставки очищены: {self.df_unique.height}")
            return self.df_unique
        except Exception as e:
            self.logger.error(f"Ошибка очистки страниц для вставки: {e}")
            raise
    
    def add_page_params(self) -> pl.DataFrame:
        """ Добавляем параметры к страницам (заглушка) """
        if self.df_unique is None or self.df_unique.is_empty():
            self.logger.warning("⚠️ Нет данных для обработки. Сначала вызовите get_unique_pages()")
            return 
        
        try:
            self.df_final = self.df_unique.with_columns([
                pl.lit(None, dtype=pl.String).alias("site_section")
            ])
            self.logger.info("Успешное добавление параметров к страницам")
            return self.df_final
        except Exception as e:
            self.logger.error(f"Ошибка добавления параметров к страницам: {e}")
            raise

    def load_ddm_pages(self):
        """ Функция загрузки страниц в таблицу page_dimension """
        if self.df_final is None or self.df_final.height == 0:
            self.logger.warning("⚠️ Нет новых данных для вставки.")
            return

        try: 
            records = self.df_final.to_dicts()
            self.logger.info(f"Параметры page_dimension успешно подготовлены: {len(records)} строк.")
            
            with db_session_scope() as (session, engine):
                stmt = insert(PageDimension).values(records)
                session.execute(stmt)
                session.commit()
                self.logger.info("🎉 Данные в ddm.page_dimension успешно обновлены.")
        except Exception as e:
            self.logger.error(f"🔴 Ошибка обновления ddm.page_dimension: {e}")
            raise

if __name__ == "__main__":
    loader = DDMPages()
    loader.get_lookup_pages()
    loader.get_ddm_pages()
    loader.get_unique_pages()
    loader.add_page_params()
    loader.load_ddm_pages()
