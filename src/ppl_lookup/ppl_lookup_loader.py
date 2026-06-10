import polars as pl
import logging
from sqlalchemy.dialects.postgresql import insert as pg_insert
from src.database.connection import db_session_scope
from src.models.models import LookupQuery, LookupPage, LookupDate

class PplLookupLoader:
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

    def extract_clean_data(self) -> pl.DataFrame:
        """Шаг 1: Выкачиваем только нужные плоские данные из ppl"""
        self.logger.info("Выкачиваем данные из ppl.webmaster_aggregated...")
        
        query = "SELECT dt, query, page_path FROM ppl.webmaster_aggregated"
        
        with db_session_scope() as (session, engine):
            with engine.connect() as conn:
                df = pl.read_database(query=query, connection=conn)
        return df

    def load_registry(self):
        """Главный метод управления загрузкой реестров"""
        try:
            # Получаем плоский датафрейм
            df_base = self.extract_clean_data()
            
            # --- ОБРАБОТКА QUERY ---
            df_query = df_base.select(
                pl.col('query').str.to_lowercase()
            ).unique()
            
            # --- ОБРАБОТКА PAGE_PATH ---
            df_page = df_base.select(
                pl.col('page_path').str.to_lowercase()
                .unique()
            )
            
            # --- ОБРАБОТКА DATE ---
            df_date = df_base.select(
                pl.col('dt')
                .unique()
            )

            # Открываем соединение с базой через engine.begin() (авто-коммит)
            with db_session_scope() as (session, engine):
                with engine.begin() as conn:
                    
                    # 1. Загрузка ЗАПРОСОВ
                    self.logger.info("Загрузка query_unique...")
                    stmt_q = pg_insert(LookupQuery).values(df_query.to_dicts())
                    conn.execute(stmt_q.on_conflict_do_nothing(index_elements=["query"]))
                    
                    # 2. Загрузка URL-адресов
                    self.logger.info("Загрузка page_unique...")
                    # ТВОЙ КОД ЗДЕСЬ: Напиши insert + on_conflict_do_nothing для страниц
                    stmt_p = pg_insert(LookupPage).values(df_page.to_dicts())
                    conn.execute(stmt_p.on_conflict_do_nothing(index_elements=['page_path']))
                    
                    # 3. Загрузка ДАТ
                    self.logger.info("Загрузка date_unique...")
                    # ТВОЙ КОД ЗДЕСЬ: Напиши insert + on_conflict_do_nothing для дат
                    stmt_d = pg_insert(LookupDate).values(df_date.to_dicts())
                    conn.execute(stmt_d.on_conflict_do_nothing(index_elements=['dt']))

            self.logger.info("🚀 Все реестры сущностей ppl_lookup успешно обновлены!")

        except Exception as e:
            self.logger.error(f"🔴 Ошибка в конвейере ppl_lookup: {e}")
            raise

if __name__ == "__main__":
    # Настраиваем базовый логгер, чтобы видеть инфо-сообщения в консоли
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    loader = PplLookupLoader()
    loader.load_registry()
