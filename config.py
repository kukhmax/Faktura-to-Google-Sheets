"""
Модуль конфигурации Faktura Bot.

Загружает настройки из .env файла и предоставляет дефолтные значения.
"""

import os
from dotenv import load_dotenv

# Загружаем переменные из .env файла
load_dotenv()


# ===== Telegram =====
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# ===== OCR.space =====
OCR_API_KEY = os.getenv("OCR_API_KEY", "")
OCR_API_URL = "https://api.ocr.space/parse/image"
OCR_LANGUAGE = "pol"  # Польский язык
OCR_ENGINE = 2        # Engine 2: лучший баланс скорости и качества

# ===== Google Sheets =====
GOOGLE_SPREADSHEET_ID = os.getenv("GOOGLE_SPREADSHEET_ID", "")
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
SPREADSHEET_NAME = "Faktura Bot — Товары"  # Имя новой таблицы при создании

# ===== Настройки по умолчанию =====
DEFAULT_TAX_PERCENT = float(os.getenv("DEFAULT_TAX_PERCENT", "5"))
DEFAULT_MARGIN_PERCENT = float(os.getenv("DEFAULT_MARGIN_PERCENT", "40"))

# ===== Заголовки таблицы =====
SHEET_HEADERS = [
    "Дата покупки",
    "Номер фактуры",
    "Продавец",
    "Название товара",
    "Цена закупки (шт.)",
    "Количество",
    "Общая стоимость",
    "Налог (%)",
    "Маржа (%)",
    "Новая цена (шт.)",
    "Цена всех",
]

# ===== Путь к файлу настроек пользователей =====
USER_SETTINGS_FILE = "user_settings.json"


def validate_config():
    """Проверяет, что все обязательные переменные окружения заданы."""
    errors = []

    if not TELEGRAM_BOT_TOKEN:
        errors.append("TELEGRAM_BOT_TOKEN не задан в .env")
    if not OCR_API_KEY:
        errors.append("OCR_API_KEY не задан в .env")
    if not os.path.exists(GOOGLE_CREDENTIALS_FILE):
        errors.append(
            f"Файл Google credentials не найден: {GOOGLE_CREDENTIALS_FILE}\n"
            "  Скачайте JSON-ключ сервисного аккаунта из Google Cloud Console."
        )

    if errors:
        print("❌ Ошибки конфигурации:")
        for error in errors:
            print(f"   • {error}")
        print("\nСмотрите README.md для инструкций по настройке.")
        return False

    return True
