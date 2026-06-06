import logging
import os
import shutil
from datetime import datetime
from pathlib import Path

from src.database.connection import db_session_scope
from src.database.repository import WebmasterRepository
from src.excel_reader.reader import ExcelReader

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_pipeline():
    logger.info("=== ЗАПУСК КОНВЕЙЕРА ДОЗАПИСИ ДАННЫХ ===")

    project_root = Path(__file__).resolve().parent.parent
    input_dir = project_root / "data" / "input"
    archive_dir = project_root / "data" / "archive"

    reader = ExcelReader(input_dir, archive_dir)

    found_files = reader.find_excel_files()
    if not found_files:
        logger.warning("Нет новых файлов Excel для обработки.")
        return

    # Цепочка вызовов из вашего reader.py
    reader.read_excel_files()
    reader.rename_columns()
    reader.get_unique_dates()
    
    logger.info("Трансформируем данные в Polars...")
    df_clean = reader.transform_to_long()

    if df_clean is None or df_clean.height == 0:
        logger.error("🔴 Ошибка: Датафрейм пустой после трансформации!")
        return

    # Инициализируем репозиторий
    repo = WebmasterRepository(db_session_scope)

    try:
        # Открываем единую транзакцию через SSH-туннель
        with db_session_scope() as (session, engine):
            logger.info("Успешно подключились к удаленной БД.")

            # 1. Получаем уникальные даты из загружаемого файла Excel (переводим в строки 'YYYY-MM-DD')
            file_dates = df_clean["dt"].unique().dt.strftime("%Y-%m-%d").to_list()
            logger.info(f"Даты в новом файле для загрузки: {file_dates}")

            # 2. УДАЛЕНИЕ: Стираем данные за эти даты, если они есть в базе (с авто-сбросом sequence)
            repo.delete_by_dates(session, file_dates, sync_sequence=True)

            # 3. ВСТАВКА: Дозаписываем новые данные (id сгенерируются автоматически СУБД)
            inserted_count = repo.insert_data(session, df_clean)
            
            # 4. ФИНАЛЬНАЯ СИНХРОНИЗАЦИЯ: На всякий случай фиксируем sequence в конце вставки
            repo.sync_sequence(session)
            
            logger.info(f"🎉 УСПЕШНО! Дозаписано строк: {inserted_count}.")

        # 5. Перенос файла в архив
        logger.info("Архивируем обработанный файл...")
        archive_dir.mkdir(parents=True, exist_ok=True)
        for file_path in found_files:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            archive_name = f"{file_path.stem}_{timestamp}{file_path.suffix}"
            shutil.move(str(file_path), str(archive_dir / archive_name))
        logger.info("Конвейер успешно завершил работу. Логи чисты! 🚀")

    except Exception as e:
        logger.error(f"🔴 Крах конвейера: {e}")

if __name__ == "__main__":
    run_pipeline()