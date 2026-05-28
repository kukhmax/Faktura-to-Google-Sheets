"""
Модуль для хранения индивидуальных настроек пользователей.

Сохраняет:
- Процент налога (по умолчанию 5%)
- Процент маржи (по умолчанию 40%)
- ID связанной Google Таблицы (чтобы каждый имел свою личную таблицу)

Хранилище реализовано в виде простого JSON-файла.
"""

import os
import json
import logging

import config

logger = logging.getLogger(__name__)


class UserSettingsManager:
    def __init__(self, filepath: str = config.USER_SETTINGS_FILE):
        self.filepath = filepath
        self.settings = {}
        self.load()

    def load(self):
        """Загружает настройки из JSON файла."""
        if not os.path.exists(self.filepath):
            self.settings = {}
            return

        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                self.settings = json.load(f)
            logger.info(f"Настройки пользователей загружены из {self.filepath}")
        except Exception as e:
            logger.error(f"Не удалось прочитать файл настроек {self.filepath}: {e}")
            self.settings = {}

    def save(self):
        """Сохраняет текущие настройки в JSON файл."""
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=4)
            logger.debug(f"Настройки пользователей сохранены в {self.filepath}")
        except Exception as e:
            logger.error(f"Не удалось сохранить настройки в файл: {e}")

    def _get_user_data(self, user_id: str | int) -> dict:
        """Возвращает настройки конкретного пользователя или создает дефолтные."""
        uid = str(user_id)
        if uid not in self.settings:
            self.settings[uid] = {
                "tax_percent": config.DEFAULT_TAX_PERCENT,
                "margin_percent": config.DEFAULT_MARGIN_PERCENT,
                "spreadsheet_id": "",
                "spreadsheet_url": ""
            }
            self.save()
        return self.settings[uid]

    def get_tax(self, user_id: str | int) -> float:
        """Получает процент налога для пользователя."""
        data = self._get_user_data(user_id)
        return float(data.get("tax_percent", config.DEFAULT_TAX_PERCENT))

    def set_tax(self, user_id: str | int, value: float) -> None:
        """Устанавливает процент налога для пользователя."""
        uid = str(user_id)
        self._get_user_data(uid)  # Инициализация если нет
        self.settings[uid]["tax_percent"] = round(float(value), 2)
        self.save()

    def get_margin(self, user_id: str | int) -> float:
        """Получает процент маржи для пользователя."""
        data = self._get_user_data(user_id)
        return float(data.get("margin_percent", config.DEFAULT_MARGIN_PERCENT))

    def set_margin(self, user_id: str | int, value: float) -> None:
        """Устанавливает процент маржи для пользователя."""
        uid = str(user_id)
        self._get_user_data(uid)  # Инициализация если нет
        self.settings[uid]["margin_percent"] = round(float(value), 2)
        self.save()

    def get_spreadsheet_id(self, user_id: str | int) -> str:
        """Получает ID Google Таблицы пользователя."""
        data = self._get_user_data(user_id)
        return data.get("spreadsheet_id", "")

    def get_spreadsheet_url(self, user_id: str | int) -> str:
        """Получает URL Google Таблицы пользователя."""
        data = self._get_user_data(user_id)
        return data.get("spreadsheet_url", "")

    def set_spreadsheet(self, user_id: str | int, spreadsheet_id: str, spreadsheet_url: str) -> None:
        """Привязывает Google Таблицу к пользователю."""
        uid = str(user_id)
        self._get_user_data(uid)  # Инициализация если нет
        self.settings[uid]["spreadsheet_id"] = spreadsheet_id
        self.settings[uid]["spreadsheet_url"] = spreadsheet_url
        self.save()


# Глобальный синглтон для удобного импорта
settings_manager = UserSettingsManager()
