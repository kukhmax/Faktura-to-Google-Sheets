"""
Модуль для работы с Google Sheets API.

Обеспечивает:
- Авторизацию через Service Account.
- Создание новой Google Таблицы (если ID не задан).
- Предоставление публичного доступа по ссылке (на чтение).
- Добавление данных из фактур в таблицу.
"""

import logging
import gspread
from google.oauth2.service_account import Credentials

import config
from text_parser import InvoiceData, calculate_new_prices

logger = logging.getLogger(__name__)

# Области видимости для Google API
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]


def get_gspread_client() -> gspread.Client:
    """Авторизуется и возвращает клиент gspread."""
    try:
        credentials = Credentials.from_service_account_file(
            config.GOOGLE_CREDENTIALS_FILE,
            scopes=SCOPES
        )
        return gspread.authorize(credentials)
    except Exception as e:
        logger.error(f"Ошибка авторизации Google API: {e}")
        raise e


def get_or_create_spreadsheet(spreadsheet_id: str = None) -> tuple[gspread.Spreadsheet, bool]:
    """
    Открывает существующую таблицу или создает новую.
    
    Returns:
        Кортеж (Spreadsheet, is_created)
    """
    client = get_gspread_client()
    
    # Пытаемся открыть по переданному ID или из конфига
    sid = spreadsheet_id or config.GOOGLE_SPREADSHEET_ID
    
    if sid:
        try:
            spreadsheet = client.open_by_key(sid)
            logger.info(f"Успешно открыта существующая таблица ID: {sid}")
            return spreadsheet, False
        except Exception as e:
            logger.warning(f"Не удалось открыть таблицу по ID {sid}: {e}. Будет создана новая.")

    # Создаем новую таблицу
    try:
        logger.info(f"Создание новой таблицы с именем '{config.SPREADSHEET_NAME}'...")
        spreadsheet = client.create(config.SPREADSHEET_NAME)
        
        # Настраиваем публичный доступ на чтение, чтобы пользователь мог её открыть
        try:
            spreadsheet.client.insert_permission(
                spreadsheet.id,
                value=None,
                perm_type="anyone",
                role="reader"
            )
            logger.info("Предоставлен доступ к таблице для всех по ссылке (на чтение).")
        except Exception as perm_err:
            logger.error(f"Не удалось настроить публичный доступ: {perm_err}")

        # Инициализируем заголовки в первом листе
        sheet = spreadsheet.get_worksheet(0)
        sheet.append_row(config.SHEET_HEADERS)
        
        # Делаем первую строчку жирной для красоты
        try:
            sheet.format("A1:J1", {"textFormat": {"bold": True}})
        except Exception as fmt_err:
            logger.warning(f"Не удалось отформатировать заголовки: {fmt_err}")
            
        return spreadsheet, True
        
    except Exception as e:
        logger.error(f"Ошибка при создании новой таблицы: {e}")
        raise e


def append_invoice_to_sheet(
    invoice_data: InvoiceData,
    tax_percent: float,
    margin_percent: float,
    spreadsheet_id: str = None
) -> dict:
    """
    Рассчитывает новые цены и записывает данные фактуры в Google Sheets.
    
    Args:
        invoice_data: Извлеченные данные фактуры
        tax_percent: Процент налога (например, 5)
        margin_percent: Процент маржи (например, 40)
        spreadsheet_id: Опциональный ID таблицы (если нужно записать в конкретную)
        
    Returns:
        dict с результатами:
            - success (bool): успешность
            - spreadsheet_id (str): ID таблицы
            - spreadsheet_url (str): ссылка на таблицу
            - items_added (int): сколько товаров добавлено
            - error (str | None): ошибка, если есть
    """
    try:
        if not invoice_data.is_valid:
            return {
                "success": False,
                "spreadsheet_id": "",
                "spreadsheet_url": "",
                "items_added": 0,
                "error": "Нет корректных товаров для добавления в таблицу"
            }

        # Получаем/создаем таблицу
        spreadsheet, is_created = get_or_create_spreadsheet(spreadsheet_id)
        sheet = spreadsheet.get_worksheet(0)
        
        # Рассчитываем цены для товаров
        calculated_items = calculate_new_prices(
            invoice_data.items,
            tax_percent,
            margin_percent
        )
        
        # Формируем строки для вставки
        rows_to_append = []
        for item in calculated_items:
            # Заменяем пустые значения даты и номера фактуры на прочерки или плейсхолдеры
            date_val = invoice_data.date or "-"
            inv_num = invoice_data.invoice_number or "-"
            
            row = [
                date_val,
                inv_num,
                item["name"],
                item["unit_price"],
                item["quantity"],
                item["total_price"],
                f"{item['tax_percent']}%",
                f"{item['margin_percent']}%",
                item["new_unit_price"],
                item["new_total_price"]
            ]
            rows_to_append.append(row)
            
        # Добавляем строки в таблицу
        sheet.append_rows(rows_to_append, value_input_option="USER_ENTERED")
        logger.info(f"Успешно добавлено {len(rows_to_append)} строк в таблицу {spreadsheet.title}")
        
        return {
            "success": True,
            "spreadsheet_id": spreadsheet.id,
            "spreadsheet_url": spreadsheet.url,
            "items_added": len(rows_to_append),
            "is_created": is_created,
            "error": None
        }
        
    except Exception as e:
        logger.error(f"Ошибка записи в Google Sheets: {e}")
        return {
            "success": False,
            "spreadsheet_id": "",
            "spreadsheet_url": "",
            "items_added": 0,
            "error": str(e)
        }
