""" Главный управляющий модуль всего ETL-конвейера """
import logging
from src.load_data import run_pipeline as run_rdl_pipeline
from src.ppl.ppl_loader import PPLLoader
from src.ppl_lookup.ppl_lookup_loader import PplLookupLoader

# Импортируем наши новые загрузчики DDM слоя
from src.ddm.dates_loader import DDMDates
from src.ddm.queries_loader import DDMQueries
from src.ddm.page_paths_loader import DDMPages
from src.ddm.fct_demand_loader import DDMDemand
from src.ddm.fct_pic_loader import DDMPicLoader

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
    
    # ШАГ 3: ОБНОВЛЕНИЕ СУЩНОСТЕЙ В PPL_LOOKUP
    try:
        logger.info("⏳ ШАГ 3: Обновление уникальных реестров (Query, Page, Date)...")
        lookup_loader = PplLookupLoader()
        lookup_loader.load_registry()
        logger.info("✅ ШАГ 3 завершен успешно.")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка на ШАГЕ 3 (PPL_LOOKUP): {e}")
        return

    # ШАГ 4: ОБНОВЛЕНИЕ ИЗМЕРЕНИЙ АНАЛИТИЧЕСКОГО СЛОЯ (DDM DIMENSIONS)
    try:
        logger.info("⏳ ШАГ 4: Обновление аналитических измерений DDM (Звезда)...")
        
        # 4.1. Даты
        dates_loader = DDMDates()
        dates_loader.get_lookup_dates()
        dates_loader.load_ddm_dates()
        
        # 4.2. Поисковые запросы
        queries_loader = DDMQueries()
        queries_loader.get_lookup_queries()
        queries_loader.get_ddm_queries()
        queries_loader.get_unique_query()
        queries_loader.add_query_params()
        queries_loader.load_ddm_queries()
        
        # 4.3. URL-страницы
        pages_loader = DDMPages()
        pages_loader.get_lookup_pages()
        pages_loader.get_ddm_pages()
        pages_loader.get_unique_pages()
        pages_loader.add_page_params()
        pages_loader.load_ddm_pages()
        
        logger.info("✅ ШАГ 4 завершен успешно.")
    except Exception as e:
        logger.error(f"❌ Крах на ШАГЕ 4 (DDM Dimensions): {e}")
        return

    # ШАГ 5: РАСЧЕТ И ЗАЛИВКА ТАБЛИЦ ФАКТОВ (DDM FACTS)
    try:
        logger.info("⏳ ШАГ 5: Расчет и загрузка аналитических таблиц фактов...")
        
        # 5.1. Факты атомарного спроса
        demand_loader = DDMDemand()
        demand_loader.get_ppl_demand()
        demand_loader.get_existing_fct_demand()
        demand_loader.filter_new_demand()
        demand_loader.load_ddm_demand()
        
        # 5.2. Атомарные факты показов и кликов (Расшивка)
        pic_loader = DDMPicLoader()
        df_wagg = pic_loader.get_webm_agg_data()
        df_queries = pic_loader.get_query_dimension()
        df_pages = pic_loader.get_page_dimension()
        pic_loader.transform_to_atomic(df_queries, df_pages)
        pic_loader.load_ddm_facts()
        
        logger.info("✅ ШАГ 5 завершен успешно.")
    except Exception as e:
        logger.error(f"❌ Крах на ШАГЕ 5 (DDM Facts): {e}")
        return

    logger.info("🎉 ================================================")
    logger.info("🎉 КОНВЕЙЕР УСПЕШНО ВЫПОЛНИЛ ВСЕ ЭТАПЫ РАБОТЫ!")
    logger.info("🎉 ================================================")

if __name__ == "__main__":
    main()
