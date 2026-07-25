""" Модуль для инкрементальной загрузки данных в независимую таблицу ddm.fct_row_demand """
""" Запуск из корня: python -m src.ddm.fct_demand_loader """

import polars as pl
import logging
from datetime import datetime
from sqlalchemy import insert, text

from src.database.connection import db_session_scope
from src.models.models import FctRowDemand  # Обновленная модель фактов спроса

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
        """ Извлекаем все необходимые поля из слоя предобработки ppl.webmaster_aggregated """
        try:
            with db_session_scope() as (session, engine):
                self.logger.info("🔄 SSH-туннель поднят. Подключаемся к базе...")
                with engine.connect() as conn:
                    # Забираем ВСЕ строки, включая demand при нулевых impressions
                    query = "SELECT id AS row_id, dt, query, page_path, demand FROM ppl.webmaster_aggregated"
                    self.logger.info("📥 Выкачиваем данные из ppl.webmaster_aggregated в Polars...")
                    self.df_ppl = pl.read_database(query=query, connection=conn)
                    
            self.logger.info(f"✅ Данные из PPL скачаны. Размер: {self.df_ppl.shape}")
            return self.df_ppl
        except Exception as e:
            self.logger.error(f"🔴 Ошибка получения данных из ppl-слоя: {e}")
            raise

    def get_query_dimension(self) -> pl.DataFrame:
        """ Выкачиваем query_id из справочника ddm.query_dimension """
        try:
            with db_session_scope() as (session, engine):
                with engine.connect() as conn:
                    query = "SELECT id AS query_id, query FROM ddm.query_dimension"
                    return pl.read_database(query=query, connection=conn)
        except Exception as e:
            self.logger.error(f"🔴 Ошибка получения ddm.query_dimension: {e}")
            raise

    def get_page_dimension(self) -> pl.DataFrame:
        """ Выкачиваем page_id из справочника ddm.page_dimension """
        try:
            with db_session_scope() as (session, engine):
                with engine.connect() as conn:
                    query = "SELECT id AS page_id, page_path FROM ddm.page_dimension"
                    return pl.read_database(query=query, connection=conn)
        except Exception as e:
            self.logger.error(f"🔴 Ошибка получения ddm.page_dimension: {e}")
            raise

    def enrich_and_filter_demand(self, df_queries: pl.DataFrame, df_pages: pl.DataFrame) -> pl.DataFrame:
        """ Обогащает спрос суррогатными ID измерений """
        if self.df_ppl is None:
            self.logger.warning("⚠️ Нет данных для обработки. Сначала вызовите get_ppl_demand()")
            return 
        
        try:
            self.logger.info("🔗 Мэтчим данные спроса со справочниками DDM...")
            # Подтягиваем query_id и page_id по текстовым полям
            df_enriched = (
                self.df_ppl
                .join(df_queries, on="query", how="left")
                .join(df_pages, on="page_path", how="left")
            )

            # Теперь мы НЕ делаем anti-join по row_id. Нам нужны все строки текущей пачки!
            self.df_final = df_enriched.select([
                "row_id", "dt", "query_id", "page_id", "demand"
            ])

            self.logger.info(f"Строки спроса подготовлены к перезаписи. Всего: {self.df_final.height}")
            return self.df_final
        except Exception as e:
            self.logger.error(f"Ошибка обогащения строк спроса: {e}")
            raise

    def load_ddm_demand(self):
        """ Выполняем очистку по датам и пакетную вставку (Bulk Insert) в СУБД """
        if self.df_final is None or self.df_final.height == 0:
            self.logger.warning("⚠️ Нет строк спроса для вставки.")
            return

        try: 
            # 1. Находим уникальные даты в текущей пачке для таргетной очистки
            unique_dates = self.df_final["dt"].unique().dt.strftime("%Y-%m-%d").to_list()
            self.logger.info(f"Найдено уникальных дат для перезаписи спроса: {len(unique_dates)}")

            records = self.df_final.to_dicts()
            
            # Конвертируем даты для алхимии
            for r in records:
                if isinstance(r["dt"], str):
                    r["dt"] = datetime.strptime(r["dt"], "%Y-%m-%d").date()

            with db_session_scope() as (session, engine):
                # 2. ОЧИСТКА: Удаляем старый спрос строго за те даты, которые прилетели в новой пачке
                self.logger.info("❌ Удаляем старый спрос за целевые даты...")
                session.execute(
                    text("DELETE FROM ddm.fct_row_demand WHERE dt = ANY(CAST(:dates AS date[]))"),
                    {"dates": unique_dates}
                )

                # 3. ВСТАВКА: Заливаем новые очищенные данные
                self.logger.info(f"🚀 Запускаем пакетную вставку (Bulk Insert) {len(records)} строк спроса...")
                session.execute(insert(FctRowDemand), records)
                session.commit()
                self.logger.info("🎉 Таблица ddm.fct_row_demand успешно обновлена!")
        except Exception as e:
            self.logger.error(f"🔴 Ошибка записи в ddm.fct_row_demand: {e}")
            raise


if __name__ == "__main__":
    loader = DDMDemand()
    
    # 1. Извлекаем данные
    loader.get_ppl_demand()
    df_queries = loader.get_query_dimension()
    df_pages = loader.get_page_dimension()
    
    # 2. Трансформируем и фильтруем дельту
    loader.enrich_and_filter_demand(df_queries, df_pages)
    
    # 3. Загружаем
    loader.load_ddm_demand()
