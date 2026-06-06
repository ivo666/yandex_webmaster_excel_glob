""" Скрипт первоначальной загрузки исторических данных в rdl-слой """
""" Запуск из корневой директории python -m src.utils.load_history"""
import os
import sys
import logging
from pathlib import Path
from sqlalchemy import insert, text
import polars as pl
from dotenv import load_dotenv

# 1. НАСТРОЙКА ПУТЕЙ PYTHON
# Находим корень проекта: этот файл лежит в src/utils, значит корень на 2 уровня выше
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent.parent

if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Явно загружаем .env из корня проекта
load_dotenv(dotenv_path=project_root / '.env')

# Теперь импорты из src гарантированно сработают!
from src.database.connection import db_session_scope
from src.models.models import Webm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_historical_data():
    logger.info("=== СТАРТ ЗАГРУЗКИ ИСТОРИЧЕСКИХ ДАННЫХ В RDL ===")
    
    # ИСПРАВЛЕНО: Теперь путь к CSV жестко привязан к корню проекта, а не месту запуска
    csv_path = project_root / "data" / "input" / "webm.csv"
    if not csv_path.exists():
        logger.error(f"Файл {csv_path} не найден!")
        return

    logger.info(f"Читаем CSV файл: {csv_path.name}...")
    df = pl.read_csv(csv_path)
    
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
    max_id = df_prepared["id"].max()

    try:
        with db_session_scope() as (session, engine):
            logger.info("Удаляем старые данные из rdl.webm_excel перед миграцией...")
            session.execute(text("TRUNCATE TABLE rdl.webm_excel RESTART IDENTITY CASCADE;"))
            
            logger.info("Заливаем исторические данные на удаленный сервер...")
            session.execute(insert(Webm).values(records))
            logger.info(f" Успешно записано {total_rows} строк.")

            logger.info(f"Синхронизируем счетчик ID в PostgreSQL (устанавливаем на {max_id})...")
            seq_query = text(f"SELECT setval('rdl.webm_excel_id_seq', {max_id}, true);")
            session.execute(seq_query)
            
            logger.info("🎉 ИСТОРИЧЕСКАЯ МИГРАЦИЯ УСПЕШНО ЗАВЕРШЕНА!")

    except Exception as e:
        logger.error(f"🔴 Ошибка при загрузке истории: {e}")


if __name__ == "__main__":
    load_historical_data()
