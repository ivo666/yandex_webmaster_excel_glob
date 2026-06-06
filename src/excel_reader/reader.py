""" Основной модуль по загрузке данных из excel-файла"""
import polars as pl
from typing import List, Dict, Tuple, Optional
import os
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ExcelReader:
    def __init__(self, input_dir: str, archive_dir: str):
        """ 
        Args:
            input_dir: директория с входным Excel файлом
            archive_dir: директория для архивации обработанных файлов
        """ 
        self.input_dir = Path(input_dir)
        self.archive_dir = Path(archive_dir)
        self.df_primary = None
        self.excel_files = None
        self.unique_dates = None
        self.logger = logger

    def find_excel_files(self):
        """ Находим файлы с данными для загрузки"""
        self.logger.info(f"Ищем в: {self.input_dir.absolute()}")
        self.logger.info(f"Папка существует: {self.input_dir.exists()}")

        if not self.input_dir.exists():
            self.logger.error(f"Папка {self.input_dir} не существует.")
            raise 

        self.excel_files = list(self.input_dir.glob("*.xlsx")) + list(self.input_dir.glob("*.xls"))

        if not self.excel_files:
            self.logger.error("Исходная папка пустая.")

        self.logger.info(f"Найдено Excel файлов {len(self.excel_files)}")
        return self.excel_files
    
    def read_excel_files(self) -> Optional[pl.DataFrame]:
        """Читаем содержимое найденного Excel-файла"""
        try:
            # 1. Проверяем, что список файлов вообще существует и не пуст
            if not hasattr(self, 'excel_files') or not self.excel_files:
                self.logger.warning("Список файлов пуст. Сначала нужно вызвать find_excel_files().")
                return None
            
            # 2. Берем ПЕРВЫЙ файл из списка (индекс 0) для обработки
            target_file = self.excel_files[0]
            self.logger.info(f"Начинаем чтение файла: {target_file.name}")
            
            # 3. Читаем конкретный файл
            self.df_primary = pl.read_excel(
                source=target_file,  # Передаем одиночный объект Path, а не список
                engine='openpyxl'
            )
            
            self.logger.info(f"\nФайл успешно прочитан. Загружено строк: {self.df_primary.height}")
            self.logger.info(f"Колонки: {self.df_primary.columns}")
            return self.df_primary
        
        except Exception as e:
            self.logger.error(f"Ошибка чтения файла: {e}")
            return None
        
    def rename_columns(self):
        """ Обрабатываем данные из исходного файла"""
        # Переименовываем первве два параметра
        if 'Query' in self.df_primary.columns:
            self.df_primary = self.df_primary.rename({'Query' : 'query'})
        else:
            logger.info('Внимание, колонка Query не найдена')

        if 'Url' in self.df_primary.columns:
            self.df_primary = self.df_primary.rename({'Url' : 'page_path'})
        else:
            logger.info('Внимание, колонка Url не найдена')

        self.logger.info(f"\nНовое название параметров: {self.df_primary.columns[:2]}")

    def get_unique_dates(self):
        try:
            metric_columns = [col for col in self.df_primary.columns
                            if col not in ['query', 'page_path'] ]
            
            # получаем список уникальных дат
            self.uniqu_dates = set()
            for col in metric_columns:
                # разделяем по '_' и берем первую часть
                date_part = col.split('_')[0]
                self.uniqu_dates.add(date_part)

            self.logger.info(f"\nСписок уникальных дат: {sorted(self.uniqu_dates)}")

        except Exception as e:
            self.logger.error(f"Ошибка получения уникальных дат: {e}")

    def transform_to_long(self) -> pl.DataFrame:
        """Трансформируем данные из широкого формата в длинный средствами Polars"""

        try:
            if self.df_primary is None:
                raise ValueError('Сначала нужно выполнить read_excel_files()')
            
            id_vars = ['query', 'page_path']
            metric_columns = [col for col in self.df_primary.columns if col not in id_vars]
            
            # Шаг 1: Плавление (melt) — в Polars используется метод .unpivot() (или .melt())
            df_long = self.df_primary.unpivot(
                index=id_vars,
                on=metric_columns,
                variable_name='date_metric',
                value_name='value'
            )

            # Шаг 2: Разделяем колонку date_metric на date и metric, затем удаляем старую
            # Используем структуру .str.split_exact(), чтобы сразу получить две колонки
            df_long = df_long.with_columns([
                pl.col('date_metric').str.split_exact('_', 1).struct.field('field_0').alias('date'),
                pl.col('date_metric').str.split_exact('_', 1).struct.field('field_1').alias('metric')
            ]).drop('date_metric')

   
            # Шаг 3: Делаем Pivot (перевод строк обратно в колонки метрик)
            df_pivoted = df_long.pivot(
                on='metric',
                index=['date', 'page_path', 'query'],
                values='value',
                aggregate_function='first'  # В Polars агрегатная функция обязательна при pivot
            )

            df_pivoted = df_pivoted.rename({'shows' : 'impressions'})

            # Шаг 4: Заменяем null на 0 (fill_value в Polars делается через fill_null)
            # И сразу приводим типы данных в соответствие с нашей моделью SQLAlchemy
            df_pivoted = df_pivoted.fill_null(0).with_columns([
                # Превращаем строковую дату '2026-06-05' в объект даты/времени
                pl.col('date').str.to_date('%Y-%m-%d').alias('dt'),
                # Приводим метрики к нужным типам
                pl.col('demand').cast(pl.Int32),
                pl.col('impressions').cast(pl.Int32),
                pl.col('clicks').cast(pl.Int32),
                pl.col('position').cast(pl.Float64)
            ]).drop('date') # Удаляем текстовую дату, так как теперь у нас есть колонка 'dt'

            df_pivoted = df_pivoted.select(['dt', 'query', 'page_path', 'demand', 'impressions', 'position', 'clicks'])

            # Фильтруем: оставляем только те строки, где хотя бы одна метрика > 0
            df_cleaned = df_pivoted.filter(
                (pl.col('demand') > 0) | 
                (pl.col('impressions') > 0) | 
                (pl.col('clicks') > 0)
            )

            self.logger.info(f"""\n\nТрансформация завершена:
                             {df_cleaned.head()}""")

            return df_cleaned
        
        except Exception as e:
            self.logger.error(f"Ошибка трансформации в длинный формат: {e}")

        


       

    



        
    



if __name__ == "__main__":
    # 1. Получаем абсолютный путь к папке, где лежит текущий файл (src/excel_reader)
    current_file_dir = Path(__file__).resolve().parent
    
    # 2. Поднимаемся на уровень выше, в папку src, а затем в корень проекта
    project_root = current_file_dir.parent.parent  # Теперь это гарантированно '04 SQLA'
    
    # 3. Формируем железно точные абсолютные пути к папкам данных
    input_path = project_root / 'data' / 'input'
    archive_path = project_root / 'data' / 'archive'
    
    # Быстрый тест
    r = ExcelReader(input_path, archive_path)
    r.find_excel_files()
    r.read_excel_files()
    r.rename_columns()
    r.get_unique_dates()
    r.transform_to_long()