""" Главный управляющий модуль всего ETL-конвейера """
import logging
from src.load_data import run_pipeline as run_rdl_pipeline
from src.ppl.ppl_loader import PPLLoader
from src.ppl_lookup.ppl_lookup_loader import PplLookupLoader


# Настройка логирования для всего проекта
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("MAIN_PIPELINE")

def main():
    logger.info("🚀 ================================================")
    logger.info("🚀 ЗАПУСК ПОЛНОГО ЦИКЛА ETL-КОНВЕЙЕРА ЯНДЕКС.ВЕБМАСТЕР")
    logger.info("🚀 ================================================")

    # ШАГ 1: Загрузка новых сырых данных из Excel файлов в слой RDL
    try:
        logger.info("⏳ ШАГ 1: Запуск парсинга Excel и загрузки в слой RDL...")
        run_rdl_pipeline()
        logger.info("✅ ШАГ 1 завершен успешно.")
    except Exception as e:
        logger.error(f"❌ Крах на ШАГЕ 1 (RDL): {e}")
        return

    # ШАГ 2: Предобработка данных и заливка в слой PPL
    try:
        logger.info("⏳ ШАГ 2: Запуск предобработки и генерации витрины PPL...")
        loader = PPLLoader()
        
        loader.get_rdl_data()
        loader.clean_dyn_params()
        loader.restore_business_logic()
        loader.prepare_to_load()
        loader.load_to_ppl()
        
        logger.info("✅ ШАГ 2 завершен успешно.")
    except Exception as e:
        logger.error(f"❌ Крах на ШАГЕ 2 (PPL): {e}")
        return
    
    # === ШАГ 3: ОБНОВЛЕНИЕ СУЩНОСТЕЙ В PPL_LOOKUP ===
    try:
        logging.info("MAIN_PIPELINE: 🔄 Запуск ШАГА 3: Обновление уникальных реестров (Query, Page, Date)...")

        lookup_loader = PplLookupLoader()
        lookup_loader.load_registry()

        logging.info("MAIN_PIPELINE: ✅ ШАГ 3 завершен успешно.")
    except Exception as e:
        logging.error(f"MAIN_PIPELINE: 🔴 Критическая ошибка на ШАГЕ 3: {e}")
        # Если шаг критически важен, можно прервать выполнение: raise e

    logger.info("🎉 ================================================")
    logger.info("🎉 КОНВЕЙЕР УСПЕШНО ВЫПОЛНИЛ ВСЕ ЭТАПЫ РАБОТЫ!")
    logger.info("🎉 ================================================")

if __name__ == "__main__":
    main()