""" Основной модуль загрузки данных в ppl-слой """
import os
import sys
from pathlib import Path

# 1. СНАЧАЛА настраиваем пути, чтобы импорты из src гарантированно работали
project_root = Path(os.getcwd()).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import logging
from datetime import datetime
import polars as pl
from sqlalchemy import text, insert

from src.database.connection import db_session_scope
from src.models.models import WebmAgg  # Модель для слоя PPL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PPLLoader:
    def __init__(self):
        self.logger = logger
        self.df_rdl = None
        self.df_corr = None
        self.df_final = None
    
    def get_rdl_data(self) -> pl.DataFrame: 
        """ Получаем данные из rdl.webm_excel """
        try:
            with db_session_scope() as (session, engine):
                self.logger.info("🔄 SSH-туннель поднят. Подключаемся к базе...")
                
                with engine.connect() as conn:
                    query = "SELECT * FROM rdl.webm_excel"
                    self.logger.info("📥 Выкачиваем данные из rdl.webm_excel в Polars...")
                    self.df_rdl = pl.read_database(query=query, connection=conn)
                    
                self.logger.info(f"✅ Данные успешно скачаны. Размер: {self.df_rdl.shape}")
                return self.df_rdl
                
        except Exception as e:
            self.logger.error(f"🔴 Ошибка получения данных из rdl-слоя: {e}")
            raise

    def clean_dyn_params(self):
        """ Очищаем page_path от динамических параметров """
        try:
            # ИСПРАВЛЕНО: Чистый синтаксис Polars через .with_columns()
            self.df_rdl = self.df_rdl.with_columns(
                pl.col('page_path').str.split('?').list.get(0)
            )
            self.logger.info("Page_path успешно очищены от динамических параметров.")
            return self.df_rdl
        
        except Exception as e:
            self.logger.error(f"Ошибка очистки динамических параметров page_path: {e}")
            raise

    def restore_business_logic(self):
        """ Восстанавливаем бизнес логику """
        try:
            self.df_corr = self.df_rdl.with_columns([
                pl.when(pl.col('demand') < pl.col('impressions'))
                .then(pl.col('impressions'))
                .otherwise(pl.col('demand'))
                .alias('demand_corr'),
                
                pl.when(pl.col('clicks') > pl.col('impressions'))
                .then(pl.col('impressions'))
                .otherwise(pl.col('clicks'))
                .alias('clicks_corr')
            ])
            self.logger.info("Бизнес логика успешно восстановлена.")
            return self.df_corr
            
        except Exception as e:
            self.logger.error(f"Ошибка восстановления бизнес логики: {e}")
            raise

    def prepare_to_load(self):
        """ Подготавливаем данные к загрузке """
        try:
            # ИСПРАВЛЕНО: sefl -> self
            self.df_final = self.df_corr.select([
                'id', 
                'dt', 
                'query',
                'page_path',
                pl.col('demand_corr').alias('demand'), 
                'impressions', 
                'position', 
                pl.col('clicks_corr').alias('clicks')
            ])
            self.logger.info("Данные подготовлены к загрузке.")
            return self.df_final
        
        except Exception as e:
            self.logger.error(f"Ошибка подготовки данных к загрузке: {e}")
            raise

    def load_to_ppl(self):
        """ Очищаем витрину и заливаем финальный датафрейм на удаленный сервер """
        if self.df_final is None:
            raise ValueError("Данные не подготовлены! Сначала вызови предыдущие методы.")
            
        records_to_insert = self.df_final.drop("id").to_dicts()
        
        try:
            with db_session_scope() as (session, engine):
                with engine.connect() as conn:
                    self.logger.info("🗑 Очищаем таблицу ppl.webmaster_aggregated...")
                    conn.execute(text("TRUNCATE TABLE ppl.webmaster_aggregated RESTART IDENTITY CASCADE;"))
                    
                    self.logger.info(f"📥 Заливаем {len(records_to_insert)} строк в слой PPL...")
                    conn.execute(insert(WebmAgg), records_to_insert)
                    conn.commit()
                    
            self.logger.info("🎉 Слой PPL успешно обновлен на удаленном сервере!")
            
        except Exception as e:
            self.logger.error(f"🔴 Ошибка загрузки в PPL: {e}")
            raise


# Точка входа для тестирования класса
if __name__ == "__main__":
    loader = PPLLoader()
    
    # Запускаем конвейер по цепочке
    loader.get_rdl_data()
    loader.clean_dyn_params()
    loader.restore_business_logic()
    loader.prepare_to_load()
    loader.load_to_ppl()
