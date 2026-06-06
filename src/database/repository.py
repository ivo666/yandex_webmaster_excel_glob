import logging
from typing import List
from sqlalchemy import text, insert, delete
import polars as pl

from src.models.models import Webm  # Наша декларативная модель

logger = logging.getLogger(__name__)

class WebmasterRepository:
    def __init__(self, db_session_scope):
        """
        Принимает контекстный менеджер db_session_scope для управления транзакциями
        """
        self.db_scope = db_session_scope

    def delete_by_dates(self, session, dates: List[str], sync_sequence: bool = True) -> int:
        """Удаляет записи за указанные даты внутри активной сессии"""
        if not dates:
            logger.info("Нет дат для удаления.")
            return 0

        # В SQLAlchemy 2.0 используем delete().where() вместо текстового SQL
        stmt = delete(Webm).where(Webm.dt.in_(dates))
        result = session.execute(stmt)
        deleted_count = result.rowcount

        logger.info(f"🗑 Удалено старых записей за {len(dates)} дат: {deleted_count}")

        if sync_sequence and deleted_count > 0:
            self.sync_sequence(session)

        return deleted_count

    def insert_data(self, session, df: pl.DataFrame) -> int:
        """
        Вставляет данные из Polars DataFrame в таблицу rdl.webm_excel
        """
        required_columns = ['dt', 'page_path', 'query', 'demand', 'impressions', 'position', 'clicks']

        # Если в DataFrame случайно затесался id, удаляем его
        if 'id' in df.columns:
            logger.warning("⚠️ Найдена колонка id! Удаляем перед вставкой.")
            df = df.drop('id')

        missing = [col for col in required_columns if col not in df.columns]
        if missing:
            raise ValueError(f"Отсутствуют колонки: {missing}")

        # ИСПРАВЛЕНО: Просто выбираем нужные колонки, Polars сам корректно переведет null в None при вызове .to_dicts()
        df_to_insert = df.select(required_columns)
        records = df_to_insert.to_dicts()

        logger.info(f"Подготовлено строк для вставки (Bulk Insert): {len(records)}")

        if records:
            session.execute(insert(Webm).values(records))
            return len(records)
        return 0

    def get_existing_dates(self, session) -> List[str]:
        """Получает список уникальных дат, которые уже есть в таблице"""
        query = text("""
            SELECT DISTINCT TO_CHAR(dt, 'YYYY-MM-DD') as date_str
            FROM rdl.webm_excel
            ORDER BY date_str
        """)
        result = session.execute(query).fetchall()
        dates = [row[0] for row in result]
        logger.info(f"Найдено {len(dates)} уникальных дат в таблице на сервере")
        return dates

    def sync_sequence(self, session) -> int:
        """Синхронизирует sequence с максимальным ID в таблице"""
        max_id = session.execute(
            text("SELECT COALESCE(MAX(id), 0) FROM rdl.webm_excel")
        ).scalar() or 0

        # Используем ваш синтаксис сброса последовательности
        session.execute(
            text(f"SELECT setval('rdl.webm_excel_id_seq', {max_id}, true)")
        )
        
        curr_val = session.execute(text("SELECT currval('rdl.webm_excel_id_seq')")).scalar()
        logger.info(f"🔄 Sequence синхронизирован: max_id={max_id}, currval={curr_val}")
        return curr_val