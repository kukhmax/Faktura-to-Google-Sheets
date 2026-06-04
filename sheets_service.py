"""
Модуль для работы с Google Sheets API.

Обеспечивает:
- Авторизацию через Service Account.
- Создание новой Google Таблицы (если ID не задан).
- Предоставление публичного доступа по ссылке (на чтение).
- Добавление данных из фактур в таблицу.
"""

import re
import json
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


def get_service_account_email() -> str:
    """Возвращает email сервисного аккаунта из файла credentials."""
    try:
        with open(config.GOOGLE_CREDENTIALS_FILE) as f:
            creds = json.load(f)
            return creds.get("client_email", "")
    except Exception as e:
        logger.error(f"Не удалось прочитать client_email из credentials: {e}")
        return ""


def ensure_headers(sheet) -> None:
    """
    Проверяет наличие заголовков в первой строке таблицы.
    Если заголовков нет — вставляет их в строку 1 и форматирует жирным.
    """
    try:
        # Читаем первую строку
        first_row = sheet.row_values(1)
        
        # Проверяем, содержит ли первая строка хотя бы один ожидаемый заголовок
        expected_keywords = ["дата", "фактур", "товар", "цена", "количество", "стоимость", "налог", "маржа"]
        first_row_lower = " ".join(str(cell).lower() for cell in first_row) if first_row else ""
        
        has_headers = any(kw in first_row_lower for kw in expected_keywords)
        
        if not has_headers:
            # Вставляем заголовки в первую строку (сдвигая данные вниз)
            sheet.insert_row(config.SHEET_HEADERS, index=1)
            try:
                sheet.format("A1:K1", {"textFormat": {"bold": True}})
            except Exception as fmt_err:
                logger.warning(f"Не удалось отформатировать заголовки: {fmt_err}")
            logger.info("Заголовки добавлены в первую строку таблицы.")
        else:
            logger.debug("Заголовки уже присутствуют в таблице.")
    except Exception as e:
        logger.warning(f"Ошибка проверки/добавления заголовков: {e}")


def verify_and_setup_spreadsheet(spreadsheet_url_or_id: str) -> dict:
    """
    Проверяет доступность таблицы по ссылке или ID,
    настраивает заголовки, если таблица пустая.
    
    Returns:
        dict: {
            "success": bool,
            "spreadsheet_id": str,
            "spreadsheet_url": str,
            "error": str | None
        }
    """
    try:
        # Извлекаем ID из URL или используем как есть
        spreadsheet_id = spreadsheet_url_or_id
        if "docs.google.com/spreadsheets" in spreadsheet_url_or_id:
            match = re.search(r"/d/([a-zA-Z0-9-_]+)", spreadsheet_url_or_id)
            if match:
                spreadsheet_id = match.group(1)
                
        client = get_gspread_client()
        spreadsheet = client.open_by_key(spreadsheet_id)
        sheet = spreadsheet.get_worksheet(0)
        
        # Проверяем и добавляем заголовки, если их нет
        ensure_headers(sheet)
            
        return {
            "success": True,
            "spreadsheet_id": spreadsheet.id,
            "spreadsheet_url": spreadsheet.url,
            "error": None
        }
    except Exception as e:
        err_msg = str(e)
        logger.error(f"Ошибка проверки привязываемой таблицы: {e}")
        
        # Делаем ошибку авторизации более понятной
        if "permissiondenied" in err_msg.lower() or "403" in err_msg or "caller does not have permission" in err_msg.lower():
            err_msg = (
                "Доступ к таблице заблокирован (Permission Denied).\n"
                "Убедитесь, что вы открыли доступ на редактирование (Editor) для email бота:\n"
                f"{get_service_account_email()}"
            )
        elif "spreadsheetnotfound" in err_msg.lower() or "404" in err_msg:
            err_msg = "Таблица не найдена. Проверьте правильность ссылки или ID таблицы."
            
        return {
            "success": False,
            "spreadsheet_id": "",
            "spreadsheet_url": "",
            "error": err_msg
        }


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
            sheet.format("A1:K1", {"textFormat": {"bold": True}})
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
        
        # Гарантируем наличие заголовков в первой строке
        ensure_headers(sheet)
        
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
            seller_val = invoice_data.seller or "-"
            
            row = [
                date_val,
                seller_val,
                inv_num,
                item["name"],
                item["quantity"],
                item["unit_price"],
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
        err_msg = str(e)
        logger.error(f"Ошибка записи в Google Sheets: {err_msg}")
        
        # Проверяем на специфичную ошибку рассинхронизации времени
        if "invalid_grant" in err_msg or "short-lived token" in err_msg or "Check your iat and exp values" in err_msg:
            friendly_err = (
                "Рассинхронизация времени в WSL2/Docker.\n\n"
                "Системное время вашего контейнера отстает или спешит по сравнению с серверами Google "
                "(такое часто происходит в Windows/WSL2 после сна компьютера).\n\n"
                "👉 **Как исправить:**\n"
                "1. Откройте терминал Windows (PowerShell или CMD).\n"
                "2. Выполните команду:\n"
                "   `wsl --shutdown`\n"
                "3. Перезапустите приложение Docker Desktop."
            )
            return {
                "success": False,
                "spreadsheet_id": "",
                "spreadsheet_url": "",
                "items_added": 0,
                "error": friendly_err
            }

        # Проверяем на специфичную ошибку превышения квоты диска
        if "storage quota" in err_msg.lower() or "storagequotaexceeded" in err_msg.lower() or "quota has been exceeded" in err_msg.lower():
            friendly_err = (
                "Превышена квота диска Google Drive сервисного аккаунта бота (storageQuotaExceeded).\n\n"
                "Сервисный аккаунт бота исчерпал лимит свободного места Google Drive и не может создавать новые файлы.\n\n"
                "👉 **Как решить:**\n"
                "1. Создайте пустую Google Таблицу в вашем личном Google Аккаунте.\n"
                "2. Поделитесь этой таблицей с сервисным аккаунтом бота в роли **Редактор (Editor)**. Email бота:\n"
                f"   `{get_service_account_email()}`\n"
                "3. Привяжите вашу таблицу в настройках бота: **⚙️ Настройки** -> **🔗 Привязать таблицу**."
            )
            return {
                "success": False,
                "spreadsheet_id": "",
                "spreadsheet_url": "",
                "items_added": 0,
                "error": friendly_err
            }

        return {
            "success": False,
            "spreadsheet_id": "",
            "spreadsheet_url": "",
            "items_added": 0,
            "error": err_msg
        }
