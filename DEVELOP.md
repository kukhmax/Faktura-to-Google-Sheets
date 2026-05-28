# 📝 DEVELOP.md — Лог разработки Faktura Bot

Этот файл содержит подробный лог каждого шага разработки проекта.

---

## Шаг 1: Инициализация проекта (2026-05-28)

### Что сделано:
- Инициализирован git-репозиторий (`git init`)
- Создан `.gitignore` — исключены `.env`, `credentials.json`, `user_settings.json`, `__pycache__/`, виртуальное окружение и файлы IDE
- Создан `.env.example` — шаблон переменных окружения с описанием каждой переменной:
  - `TELEGRAM_BOT_TOKEN` — токен Telegram-бота
  - `OCR_API_KEY` — ключ OCR.space API
  - `GOOGLE_SPREADSHEET_ID` — ID таблицы (пусто — создаётся автоматически)
  - `GOOGLE_CREDENTIALS_FILE` — путь к JSON-ключу сервисного аккаунта
  - `DEFAULT_TAX_PERCENT` — налог по умолчанию (5%)
  - `DEFAULT_MARGIN_PERCENT` — маржа по умолчанию (40%)
- Создан `requirements.txt` — зависимости проекта:
  - `python-telegram-bot>=20.0` — async Telegram Bot API
  - `gspread>=5.0` — работа с Google Sheets
  - `google-auth>=2.0` — аутентификация Google API
  - `python-dotenv>=1.0` — загрузка .env файлов
  - `requests>=2.28` — HTTP-запросы (OCR API)
  - `Pillow>=9.0` — обработка изображений
- Создан `README.md` — полная документация: установка, настройка всех сервисов, структура таблицы, формулы расчёта, использование бота
- Создан `DEVELOP.md` — этот файл

### Файлы:
- `.gitignore`
- `.env.example`
- `requirements.txt`
- `README.md`
- `DEVELOP.md`

---

## Шаг 2: Модуль конфигурации (2026-05-28)

### Что сделано:
- Создан `config.py` — центральный модуль конфигурации:
  - Загрузка переменных из `.env` через `python-dotenv`
  - Константы Telegram: `TELEGRAM_BOT_TOKEN`
  - Константы OCR.space: `OCR_API_KEY`, `OCR_API_URL`, `OCR_LANGUAGE=pol`, `OCR_ENGINE=2`
  - Константы Google Sheets: `GOOGLE_SPREADSHEET_ID`, `GOOGLE_CREDENTIALS_FILE`, `SPREADSHEET_NAME`
  - Дефолтные значения: `DEFAULT_TAX_PERCENT=5`, `DEFAULT_MARGIN_PERCENT=40`
  - Заголовки таблицы `SHEET_HEADERS` (10 столбцов)
  - Функция `validate_config()` — проверяет наличие всех обязательных переменных и файла credentials

### Файлы:
- `config.py`
