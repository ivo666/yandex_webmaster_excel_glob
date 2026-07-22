""" Скрипт первоначальной загрузки исторических данных в rdl-слой """
""" Запуск из корневой директории python -m src.utils.load_history"""
import os
import sys
import logging
import shutil
from datetime import datetime
from pathlib import Path
from sqlalchemy import insert, text
import polars as pl
from dotenv import load_dotenv

# 1. НАСТРОЙКА ПУТЕЙ PYTHON
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent.parent

if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Явно загружаем .env из корня проекта
load_dotenv(dotenv_path=project_root / '.env')

from src.database.connection import db_session_scope
from src.models.models import Webm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_historical_data():
    logger.info("=== СТАРТ ЗАГРУЗКИ ИСТОРИЧЕСКИХ ДАННЫХ В RDL ===")
    
    csv_path = project_root / "data" / "input" / "webm.csv"
    archive_dir = project_root / "data" / "archive"
    
    if not csv_path.exists():
        logger.error(f"🔴 Файл {csv_path} не найден!")
        return

    logger.info(f"Читаем CSV файл: {csv_path.name}...")
    
    try:
        # 1. Читаем файл
        df = pl.read_csv(csv_path)
        
        # 2. Пересоздаем колонку id: удаляем старую и генерируем новую последовательность с 1
        df = df.drop("id")
        df = df.with_row_index(name="id", offset=1)
        
        # 3. Приводим типы данных
        df_prepared = df.with_columns([
            pl.col("id").cast(pl.Int32),
            pl.col("dt").str.to_date("%Y-%m-%d"),
            pl.col("demand").cast(pl.Int32),
            pl.col("impressions").cast(pl.Int32),
            pl.col("clicks").cast(pl.Int32),
            pl.col("position").cast(pl.Float64)
        ])
        
        records = df_prepared.to_dicts()
        total_rows = len(records)
        max_id = int(df_prepared["id"].max())
        
        logger.info(f"Данные переиндексированы. Новые ID: от 1 до {max_id}.")
        
    except Exception as e:
        logger.error(f"🔴 Ошибка подготовки данных из CSV: {e}")
        return

    try:
        with db_session_scope() as (session, engine):
            logger.info("Удаляем старые данные из rdl.webm_excel перед миграцией...")
            session.execute(text("TRUNCATE TABLE rdl.webm_excel RESTART IDENTITY CASCADE;"))
            
            logger.info("Заливаем исторические данные на удаленный server (Bulk Insert)...")
            session.execute(insert(Webm), records)
            logger.info(f" Успешно записано {total_rows} строк.")

            logger.info(f"Синхронизируем счетчик ID в PostgreSQL (устанавливаем на {max_id})...")
            seq_query = text("SELECT setval(pg_get_serial_sequence('rdl.webm_excel', 'id'), :max_id, true);")
            session.execute(seq_query, {"max_id": max_id})
            
            session.commit()
            logger.info("🎉 ИСТОРИЧЕСКАЯ МИГРАЦИЯ УСПЕШНО ЗАВЕРШЕНА В БД!")

        # Перенос файла истории в архив
        logger.info("Архивируем обработанный CSV-файл...")
        archive_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_name = f"historic_webm_{timestamp}.csv"
        shutil.move(str(csv_path), str(archive_dir / archive_name))
        logger.info(f"Файл успешно перемещен в архив как {archive_name} 🚀")

    except Exception as e:
        logger.error(f"🔴 Ошибка при загрузке истории в БД: {e}")



if __name__ == "__main__":
    load_historical_data()
