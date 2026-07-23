""" Основной модуль для загрузки данных в таблицу фактов fct_page_impressions_clicks"""

import polars as pl
import math
import logging
import random

from src.database.connection import db_session_scope
from src.models.models import FctPageImpressionsClicks

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

import math
import random

def generate_atomic_rows(impressions: int, clicks: int, avg_position: float, ctr_model: dict) -> list[dict]:
    """
    Генерирует список словарей с позицией и флагом клика для каждой пачки показов.
    """
    if clicks > impressions:
        clicks = impressions # Страховка бизнес-логики

    # 1. Распределяем позиции показов (твой отличный алгоритм)
    total = math.ceil(impressions * avg_position)
    base = math.floor(avg_position)
    remainder = total - (base * impressions)
    positions = [base + 1] * remainder + [base] * (impressions - remainder)
    
    # 2. Нам нужно выбрать индексы элементов, которые станут кликами.
    # Считаем веса для каждого показа на основе его позиции
    weights = [ctr_model.get(pos, 1) for pos in positions]
    
    # Выбираем уникальные индексы показов для кликов
    click_indices = set()
    
    # Чтобы не зациклиться, если веса некорректны, выбираем поштучно
    # Мы выбираем индекс от 0 до impressions-1 на основе весов позиций
    population = list(range(impressions))
    
    if clicks > 0:
        # random.choices позволяет выбирать с весами. 
        # Делаем выбор без повторений для кликов:
        chosen_indices = []
        # Локальная копия, чтобы убирать выбранное
        local_pop = population.copy()
        local_weights = weights.copy()
        
        for _ in range(clicks):
            idx_in_local = random.choices(range(len(local_pop)), weights=local_weights, k=1)[0]
            chosen_indices.append(local_pop[idx_in_local])
            local_pop.pop(idx_in_local)
            local_weights.pop(idx_in_local)
            
        click_indices = set(chosen_indices)

    # 3. Собираем итоговый атомарный список для explode
    result = []
    for i in range(impressions):
        result.append({
            "impression_position": float(positions[i]),
            "is_click": i in click_indices
        })
        
    return result

ctr_model={1: 36, 2: 24, 3: 12, 4: 8, 5: 6, 6: 5, 7: 4, 8: 4, 9: 3, 10: 3,
            11: 2, 12: 2, 13: 2, 14: 2, 15: 2, 16: 2, 17: 2, 18: 2, 19: 2, 20: 2,
            21: 1, 22: 1, 23: 1, 24: 1, 25: 1, 26: 1, 27: 1, 28: 1, 29: 1, 30: 1, 
            31: 1, 32: 1, 33: 1, 34: 1, 35: 1, 36: 1, 37: 1, 38: 1, 39: 1, 40: 1,
            41: 1, 42: 1, 43: 1, 44: 1, 45: 1, 46: 1, 47: 1, 48: 1, 49: 1, 50: 1}



class DDMPicLoader:
    """ Класс загрузки данных в таблицу фактов """
    def __init__(self):
        self.logger = logger
        self.df_wagg = None 
        self.df_queries = None
        self.df_pages = None
        self.df_final = NotImplemented
  

    def get_webm_agg_data(self):
        """ Получаем данные из ppl.webmaster_aggregated"""

        try:
            with db_session_scope() as (session, engine):
                self.logger.info("🔄 SSH-туннель поднят. Подключаемся к базе...")
                
                with engine.connect() as conn:
                    query = "SELECT id, dt, query, page_path, impressions, position, clicks FROM ppl.webmaster_aggregated WHERE impressions > 0"
                    self.logger.info("📥 Выкачиваем данные из ppl.webmaster_aggregated в Polars...")
                    self.df_wagg = pl.read_database(query=query, connection=conn)
                    
                self.logger.info(f"✅ Данные успешно скачаны. Размер: {self.df_wagg.shape}")
                return self.df_wagg
                            
        except Exception as e:
            self.logger.error(f"🔴 Ошибка получения данных из ppl-слоя: {e}")
            raise

    def get_query_dimension(self):
        try:
            with db_session_scope() as (session, engine):
                self.logger.info("🔄 SSH-туннель поднят. Подключаемся к базе...")
                with engine.connect() as conn:
                    # ИСПРАВЛЕНО: Сразу забираем как query_id
                    query = "SELECT id AS query_id, query FROM ddm.query_dimension"
                    self.logger.info("📥 Выкачиваем данные из ddm.query_dimension в Polars...")
                    self.df_query = pl.read_database(query=query, connection=conn)
                    
                self.logger.info(f"✅ Данные успешно скачаны. Размер: {self.df_query.shape}")
                return self.df_query
        except Exception as e:
            self.logger.error(f"🔴 Ошибка получения данных из ddm.query_dimension: {e}")
            raise

    def get_page_dimension(self):
        try:
            with db_session_scope() as (session, engine):
                self.logger.info("🔄 SSH-туннель поднят. Подключаемся к базе...")
                with engine.connect() as conn:
                    # ИСПРАВЛЕНО: Сразу забираем как page_id
                    query = "SELECT id AS page_id, page_path FROM ddm.page_dimension"
                    self.logger.info("📥 Выкачиваем данные из ddm.page_dimension в Polars...")
                    self.df_page = pl.read_database(query=query, connection=conn)
                    
                self.logger.info(f"✅ Данные успешно скачаны. Размер: {self.df_page.shape}")
                return self.df_page
        except Exception as e:
            self.logger.error(f"🔴 Ошибка получения данных из ddm.page_dimension: {e}")
            raise

    def transform_to_atomic(self, df_queries: pl.DataFrame, df_pages: pl.DataFrame) -> pl.DataFrame:
        """Мэтчит данные с измерениями DDM и разворачивает строки в атомарный вид"""
        try:
            self.logger.info("🔗 Джойним данные PPL со справочниками DDM...")
            
            # Подтягиваем query_id и page_id, дропаем текстовые колонки
            df_enriched = (
                self.df_wagg
                .join(df_queries, on="query", how="left")
                .join(df_pages, on="page_path", how="left")
            )
            
            self.logger.info("🛠 Запускаем генерацию атомарных пачек показов и кликов...")
            # Применяем нашу функцию к каждой строчке, создавая колонку со списком словарей
            df_packed = df_enriched.with_columns(
                pl.struct(["impressions", "clicks", "position"])
                .map_elements(
                    lambda row: generate_atomic_rows(row["impressions"], row["clicks"], row["position"], ctr_model),
                    return_dtype=pl.List(pl.Struct([
                        pl.Field("impression_position", pl.Float64),
                        pl.Field("is_click", pl.Boolean)
                    ]))
                )
                .alias("atomic_data")
            )
            
            self.logger.info("💥 Расшиваем (explode) структуру в атомарные строки фактов...")
            # 1. Сначала делаем explode списка структур
            df_exploded = df_packed.explode("atomic_data")
            
            # 2. Быстро и надежно разворачиваем поля структуры в отдельные колонки
            df_unnested = df_exploded.unnest("atomic_data")
            
            # 3. Оставляем только те поля, которые требует ddm.fct_page_impressions_clicks
            self.df_final = df_unnested.select([
                pl.col("id").alias("row_id"),
                pl.col("dt"),
                pl.col("query_id"),
                pl.col("page_id"),
                pl.col("impression_position").cast(pl.Float64), # Гарантируем тип Float для базы
                pl.col("is_click").cast(pl.Boolean)             # Гарантируем тип Boolean
            ])
            
            self.logger.info(f"✅ Таблица фактов готова к загрузке. Строк к записи: {self.df_final.height}")
            return self.df_final
            
        except Exception as e:
            self.logger.error(f"🔴 Ошибка трансформации данных в атомарный вид: {e}")
            raise

    def load_ddm_facts(self):
        """ Метод очистки по датам и пакетной загрузки фактов в СУБД """
        if self.df_final is None or self.df_final.height == 0:
            self.logger.warning("⚠️ Нет атомарных фактов для записи.")
            return

        try:
            # 1. Извлекаем уникальные даты для очистки (идемпотентность)
            unique_dates = self.df_final["dt"].unique().dt.strftime("%Y-%m-%d").to_list()
            self.logger.info(f"Найдено уникальных дат для перезаписи фактов: {len(unique_dates)}")

            # 2. Подготавливаем записи для Bulk Insert (исключаем автоинкрементный id базы)
            records = self.df_final.to_dicts()

            # Превращаем даты обратно в объекты datetime.date для совместимости с SQLAlchemy/psycopg2
            from datetime import datetime
            for r in records:
                if isinstance(r["dt"], str):
                    r["dt"] = datetime.strptime(r["dt"], "%Y-%m-%d").date()

            with db_session_scope() as (session, engine):
                self.logger.info("❌ Удаляем старые факты за целевые даты...")
                from sqlalchemy import text
                session.execute(
                    text("DELETE FROM ddm.fct_page_impressions_clicks WHERE dt = ANY(CAST(:dates AS date[]))"),
                    {"dates": unique_dates}
                )

                self.logger.info(f"🚀 Запускаем пакетную вставку (Bulk Insert) {len(records)} строк фактов...")
                # Высокопроизводительный инсерт SQLAlchemy Core
                session.execute(FctPageImpressionsClicks.__table__.insert(), records)
                
                session.commit()
                self.logger.info("🎉 Аналитическая таблица фактов показов и кликов успешно обновлена!")

        except Exception as e:
            self.logger.error(f"🔴 Ошибка загрузки фактов в БД: {e}")
            raise

if __name__ == "__main__":
    loader = DDMPicLoader()
    
    # 1. Сбор данных
    df_wagg = loader.get_webm_agg_data()
    df_queries = loader.get_query_dimension()
    df_pages = loader.get_page_dimension()
    
    # 2. Трансформация и атомизация
    loader.transform_to_atomic(df_queries, df_pages)
    
    # 3. Загрузка фактов
    loader.load_ddm_facts()


