"""
Главный модуль Telegram-бота.

Реализует:
- Reply-меню (кнопки на панели).
- Обработку фото и PDF документов фактур.
- Интерактивную настройку налога и маржи через inline-кнопки.
- Интеграцию с OCR и Google Sheets.
"""

import os
import logging
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)

import config
import ocr_service
import text_parser
import sheets_service
from user_settings import settings_manager

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния ConversationHandler для настроек
AWAITING_TAX, AWAITING_MARGIN, AWAITING_SPREADSHEET = range(3)

# Главная Reply-клавиатура
def get_main_keyboard():
    keyboard = [
        ["📸 Загрузить фактуру", "📊 Открыть таблицу"],
        ["⚙️ Настройки", "❓ Помощь"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start."""
    user = update.effective_user
    welcome_text = (
        f"👋 Привет, {user.first_name}!\n\n"
        "Я — **Faktura Bot**! Я помогу вам оцифровать бумажные фактуры и PDF "
        "в удобные Google Таблицы с автоматическим расчётом розничных цен.\n\n"
        "**Как это работает:**\n"
        "1. Вы присылаете фото или PDF фактуры (на польском языке).\n"
        "2. Я распознаю текст и нахожу товары.\n"
        "3. Я считаю новую розничную цену: `Стоимость + Налог + Маржа`.\n"
        "4. Я создаю для вас персональную Google Таблицу и добавляю данные в неё!\n\n"
        "Используйте кнопки меню ниже, чтобы управлять ботом."
    )
    await update.message.reply_text(
        welcome_text,
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает справку по боту."""
    help_text = (
        "❓ **Справка по Faktura Bot**\n\n"
        "📸 **Как загрузить фактуру:**\n"
        "Просто пришлите фото фактуры (как обычное изображение) или PDF-документ прямо в этот чат.\n\n"
        "⚙️ **Как настроить налог и маржу:**\n"
        "Нажмите кнопку **⚙️ Настройки**. Вы сможете изменить процент налога (по дефолту 5%) "
        "и маржи (по дефолту 40%), которые будут применяться для расчёта розничных цен.\n\n"
        "📊 **Где посмотреть товары:**\n"
        "При первой загрузке фактуры я создам для вас личную Google Таблицу. Ссылку на неё можно "
        "всегда получить по кнопке **📊 Открыть таблицу**."
    )
    await update.message.reply_text(
        help_text,
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )


async def open_table_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает ссылку на таблицу пользователя."""
    user_id = update.effective_user.id
    url = settings_manager.get_spreadsheet_url(user_id)

    if url:
        keyboard = [[InlineKeyboardButton("📊 Открыть Google Sheets", url=url)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "📈 Ваша персональная таблица успешно создана и доступна по ссылке ниже.\n"
            "Вы можете в любой момент открыть её:",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "ℹ️ У вас еще нет созданной таблицы.\n"
            "Просто отправьте мне фото или PDF вашей первой фактуры, и я автоматически создам "
            "таблицу и пришлю вам ссылку!",
            reply_markup=get_main_keyboard()
        )


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает текущие настройки пользователя и inline-кнопки для изменения."""
    user_id = update.effective_user.id
    tax = settings_manager.get_tax(user_id)
    margin = settings_manager.get_margin(user_id)
    url = settings_manager.get_spreadsheet_url(user_id)
    url_text = f"[Открыть 📈]({url})" if url else "`Не создана/не привязана`"

    settings_text = (
        "⚙️ **Ваши текущие настройки:**\n\n"
        f"• **Налог (по дефолту 5%):** `{tax}%`\n"
        f"• **Маржа (по дефолту 40%):** `{margin}%`\n"
        f"• **Google Таблица:** {url_text}\n\n"
        "Эти параметры используются для расчёта розничной цены товара по формуле:\n"
        "`Новая цена = Закупка + (Закупка × Налог%) + (Закупка × Маржа%)`\n\n"
        "Выберите параметр для изменения:"
    )

    keyboard = [
        [
            InlineKeyboardButton("💰 Изменить налог", callback_data="edit_tax"),
            InlineKeyboardButton("📈 Изменить маржу", callback_data="edit_margin")
        ],
        [
            InlineKeyboardButton("🔗 Привязать свою таблицу", callback_data="edit_spreadsheet")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        settings_text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )


# --- Раздел настроек через Callback/Conversations ---

async def edit_tax_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inline-кнопка изменения налога."""
    query = update.callback_query
    await query.answer()
    
    await query.message.reply_text(
        "💰 **Введите новое значение налога (в процентах, без знака %):**\n"
        "Например, если налог 5%, просто введите `5` или `5.5`.\n"
        "Для отмены введите `/cancel` или нажмите любую кнопку меню."
    )
    return AWAITING_TAX


async def save_tax_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохраняет введенный процент налога."""
    user_id = update.effective_user.id
    text = update.message.text.strip().replace(",", ".")
    
    try:
        val = float(text)
        if val < 0:
            raise ValueError()
        
        settings_manager.set_tax(user_id, val)
        await update.message.reply_text(
            f"✅ **Налог успешно изменен на {val}%!**",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text(
            "❌ Некорректный ввод! Пожалуйста, введите положительное число (например, `5` или `23`)."
        )
        return AWAITING_TAX


async def edit_margin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inline-кнопка изменения маржи."""
    query = update.callback_query
    await query.answer()
    
    await query.message.reply_text(
        "📈 **Введите новое значение маржи (в процентах, без знака %):**\n"
        "Например, если маржа 40%, просто введите `40`.\n"
        "Для отмены введите `/cancel` или нажмите любую кнопку меню."
    )
    return AWAITING_MARGIN


async def save_margin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохраняет введенный процент маржи."""
    user_id = update.effective_user.id
    text = update.message.text.strip().replace(",", ".")
    
    try:
        val = float(text)
        if val < 0:
            raise ValueError()
            
        settings_manager.set_margin(user_id, val)
        await update.message.reply_text(
            f"✅ **Маржа успешно изменена на {val}%!**",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text(
            "❌ Некорректный ввод! Пожалуйста, введите положительное число (например, `40` или `35.5`)."
        )
        return AWAITING_MARGIN


async def edit_spreadsheet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inline-кнопка привязки Google Таблицы."""
    query = update.callback_query
    await query.answer()
    
    email = sheets_service.get_service_account_email()
    
    instruction = (
        "🔗 **Привязка вашей собственной Google Таблицы**\n\n"
        "Чтобы бот мог записывать товары в вашу личную таблицу (это решит проблему с ограничениями диска бота), выполните следующие действия:\n\n"
        "1. Создайте **новую** (или откройте имеющуюся) Google Таблицу в своем Google-аккаунте.\n"
        "2. Нажмите кнопку **Поделиться (Share)** в правом верхнем углу таблицы.\n"
        "3. Добавьте следующий email сервисного аккаунта бота как **Редактора (Editor)**:\n"
        f"   `{email}`\n"
        "4. **Скопируйте ссылку** на эту таблицу (из адресной строки браузера) и **отправьте её мне** в ответном сообщении.\n\n"
        "Для отмены введите `/cancel` или нажмите любую кнопку меню."
    )
    
    await query.message.reply_text(
        instruction,
        parse_mode="Markdown"
    )
    return AWAITING_SPREADSHEET


async def save_spreadsheet_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверяет доступность и сохраняет привязанную таблицу."""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    # Если пользователь нажал кнопку из главного меню — выходим из диалога
    menu_buttons = ["📸 Загрузить фактуру", "📊 Открыть таблицу", "⚙️ Настройки", "❓ Помощь"]
    if text in menu_buttons:
        await update.message.reply_text(
            "ℹ️ Привязка таблицы отменена.",
            reply_markup=get_main_keyboard()
        )
        # Перенаправляем на соответствующий обработчик
        await text_message_router(update, context)
        return ConversationHandler.END
    
    # Простая проверка что текст похож на ссылку или ID
    if not ("docs.google.com" in text or len(text) > 20):
        await update.message.reply_text(
            "❌ Это не похоже на ссылку Google Таблицы.\n\n"
            "Пожалуйста, отправьте полную ссылку на таблицу из адресной строки браузера "
            "(например: `https://docs.google.com/spreadsheets/d/...`).\n\n"
            "Для отмены нажмите любую кнопку меню.",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
        return AWAITING_SPREADSHEET
    
    # Показываем статус проверки
    status_msg = await update.message.reply_text(
        "⏳ Проверяю доступ к вашей таблице..."
    )
    
    import asyncio
    res = await asyncio.to_thread(sheets_service.verify_and_setup_spreadsheet, text)
    
    if not res["success"]:
        try:
            await status_msg.edit_text(
                f"❌ **Не удалось получить доступ к таблице!**\n\n"
                f"Описание ошибки:\n`{res['error']}`\n\n"
                "Пожалуйста, убедитесь, что вы выдали права **Редактора (Editor)** для email бота и прислали верную ссылку, после чего попробуйте отправить ссылку снова.",
                parse_mode="Markdown"
            )
        except Exception:
            await update.message.reply_text(
                f"❌ **Не удалось получить доступ к таблице!**\n\n"
                f"Описание ошибки:\n`{res['error']}`\n\n"
                "Попробуйте отправить ссылку снова.",
                parse_mode="Markdown",
                reply_markup=get_main_keyboard()
            )
        return AWAITING_SPREADSHEET
        
    # Сохраняем настройки
    settings_manager.set_spreadsheet(
        user_id,
        res["spreadsheet_id"],
        res["spreadsheet_url"]
    )
    
    try:
        await status_msg.edit_text(
            "✅ **Таблица успешно привязана к вашему аккаунту!**\n\n"
            "Теперь все распознанные товары из ваших фактур будут добавляться именно в неё.",
            parse_mode="Markdown"
        )
    except Exception:
        await update.message.reply_text(
            "✅ **Таблица успешно привязана к вашему аккаунту!**\n\n"
            "Теперь все распознанные товары из ваших фактур будут добавляться именно в неё.",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
    return ConversationHandler.END


async def cancel_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменяет процесс настройки."""
    await update.message.reply_text(
        "❌ Настройка отменена.",
        reply_markup=get_main_keyboard()
    )
    return ConversationHandler.END


async def select_seller_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback-обработчик для выбора конкретной фирмы/парсера."""
    query = update.callback_query
    await query.answer()
    
    # Получаем выбранную фирму
    seller = query.data.split(":", 1)[1]
    
    # Сохраняем в context.user_data
    context.user_data["force_seller"] = seller
    
    if seller == "AUTO":
        seller_name = "Автоопределение (стандартный поиск)"
    elif seller == "GAIA":
        seller_name = '"GAIA" Sp. z o.o.'
    else:
        seller_name = seller
        
    await query.edit_message_text(
        f"✅ **Выбран парсер для фирмы: {seller_name}**\n\n"
        "📸 Пожалуйста, отправьте фото или PDF-файл вашей фактуры.\n"
        "Я обработаю её с использованием выбранного парсера.",
        parse_mode="Markdown"
    )


# --- Раздел обработки файлов (фото и PDF) ---

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик документов (PDF) и фотографий."""
    user_id = update.effective_user.id
    message = update.message
    
    # 1. Проверяем тип файла
    file_id = None
    filename = "invoice.jpg"
    
    if message.document:
        doc = message.document
        mime = doc.mime_type or ""
        ext = doc.file_name.lower().rsplit(".", 1)[-1] if "." in doc.file_name else ""
        
        # Разрешаем только PDF или изображения
        if mime == "application/pdf" or ext == "pdf":
            file_id = doc.file_id
            filename = doc.file_name
        elif "image" in mime or ext in ["jpg", "jpeg", "png", "bmp", "tiff", "tif"]:
            file_id = doc.file_id
            filename = doc.file_name
        else:
            await message.reply_text(
                "❌ Я принимаю только файлы PDF или изображения (фото фактуры).\n"
                "Пожалуйста, пришлите корректный файл.",
                reply_markup=get_main_keyboard()
            )
            return
            
    elif message.photo:
        # Берем максимальный размер фото
        file_id = message.photo[-1].file_id
        filename = "invoice.jpg"
        
    if not file_id:
        return

    # 2. Оповещаем пользователя и скачиваем файл
    status_message = await message.reply_text(
        "⏳ **Файл получен!** Начинаю распознавание текста через OCR.space API.\n"
        "Это может занять от 15 до 45 секунд, пожалуйста, подождите...",
        parse_mode="Markdown"
    )
    
    try:
        # Скачиваем файл в байты с увеличенным таймаутом
        tg_file = await context.bot.get_file(file_id, read_timeout=60)
        file_bytes = await tg_file.download_as_bytearray(read_timeout=60)
        
        # 3. Распознаем текст через OCR.space
        await status_message.edit_text(
            "⏳ **Файл успешно скачан!** Распознаю польский текст (Engine 2)..."
        )
        import asyncio
        ocr_result = await asyncio.to_thread(ocr_service.ocr_from_bytes, bytes(file_bytes), filename)
        
        if not ocr_result["success"]:
            await status_message.edit_text(
                f"❌ **Ошибка распознавания текста (OCR):**\n`{ocr_result['error']}`\n\n"
                "Попробуйте прислать более чёткое фото или убедитесь, что файл содержит текст.",
                parse_mode="Markdown"
            )
            return

        # 4. Анализируем текст
        await status_message.edit_text(
            "⏳ **Текст распознан!** Начинаю парсинг и поиск товаров..."
        )
        force_seller = context.user_data.get("force_seller")
        invoice_data = text_parser.parse_invoice_text(ocr_result["text"], force_seller=force_seller)
        
        # Сбрасываем принудительный парсер
        context.user_data.pop("force_seller", None)
        
        if not invoice_data.is_valid:
            await status_message.edit_text(
                "❌ **Не удалось найти товары на фактуре.**\n\n"
                "Возможно, формат таблицы слишком нестандартный. Я попытался распознать текст, но товары не определились.\n"
                "Попробуйте отправить другое фото с более чёткой таблицей товаров.",
                parse_mode="Markdown"
            )
            return

        # 5. Записываем в Google Таблицу
        await status_message.edit_text(
            f"⏳ **Товары найдены ({len(invoice_data.items)} поз.)!** Записываю данные в Google Таблицу..."
        )
        
        tax = settings_manager.get_tax(user_id)
        margin = settings_manager.get_margin(user_id)
        spreadsheet_id = settings_manager.get_spreadsheet_id(user_id)
        
        import asyncio
        sheet_result = await asyncio.to_thread(
            sheets_service.append_invoice_to_sheet,
            invoice_data,
            tax,
            margin,
            spreadsheet_id
        )
        
        if not sheet_result["success"]:
            await status_message.edit_text(
                f"❌ **Ошибка работы с Google Sheets:**\n`{sheet_result['error']}`\n\n"
                "Убедитесь, что ваш сервисный аккаунт настроен верно и у него есть доступ.",
                parse_mode="Markdown"
            )
            return
            
        # Если создана новая таблица — сохраняем её данные пользователю
        if sheet_result.get("is_created"):
            settings_manager.set_spreadsheet(
                user_id,
                sheet_result["spreadsheet_id"],
                sheet_result["spreadsheet_url"]
            )
            
        # 6. Отправляем успешный результат
        inv_num = invoice_data.invoice_number or "(не определен)"
        inv_date = invoice_data.date or "(не определена)"
        spreadsheet_url = sheet_result["spreadsheet_url"]
        
        # Формируем превью товаров для сообщения
        items_preview = []
        for idx, it in enumerate(invoice_data.items[:5], 1):
            items_preview.append(f"{idx}. {it.name} — {it.unit_price:.2f} PLN × {it.quantity}")
        if len(invoice_data.items) > 5:
            items_preview.append(f"... и ещё {len(invoice_data.items) - 5} товаров.")
            
        preview_text = "\n".join(items_preview)
        
        seller_name = invoice_data.seller or "(не определен)"
        
        success_text = (
            "✅ **Фактура успешно обработана!**\n\n"
            f"📄 **Сводка фактуры:**\n"
            f"• **Продавец (Фирма):** `{seller_name}`\n"
            f"• **Номер:** `{inv_num}`\n"
            f"• **Дата:** `{inv_date}`\n"
            f"• **Всего товаров:** `{len(invoice_data.items)}` шт.\n"
            f"• **Сумма закупки:** `{invoice_data.total_sum:.2f} PLN`\n\n"
            f"📝 **Превью товаров:**\n{preview_text}\n\n"
            f"💰 Применены настройки: налог `{tax}%`, маржа `{margin}%`.\n"
            "Все расчеты розничной цены произведены и добавлены в вашу таблицу!"
        )
        
        keyboard = [[InlineKeyboardButton("📊 Открыть Google Sheets", url=spreadsheet_url)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await status_message.delete()
        await message.reply_text(
            success_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        context.user_data.pop("force_seller", None)
        logger.error(f"Критическая ошибка обработки файла: {e}", exc_info=True)
        await status_message.edit_text(
            f"❌ **Критическая ошибка обработки:**\n`{str(e)}`",
            parse_mode="Markdown"
        )


async def text_message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Маршрутизатор текстовых сообщений из главного меню."""
    text = update.message.text
    
    if text == "📸 Загрузить фактуру":
        keyboard = [
            [
                InlineKeyboardButton("ALEXIS", callback_data="select_seller:ALEXIS"),
                InlineKeyboardButton("JURPOL", callback_data="select_seller:JURPOL")
            ],
            [
                InlineKeyboardButton("NATURAL", callback_data="select_seller:NATURAL"),
                InlineKeyboardButton("Stoklasa", callback_data="select_seller:Stoklasa")
            ],
            [
                InlineKeyboardButton('"GAIA" Sp. z o.o.', callback_data="select_seller:GAIA"),
                InlineKeyboardButton("Ни одна из них (Авто)", callback_data="select_seller:AUTO")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🏢 **Выбор фирмы/парсера**\n\n"
            "Пожалуйста, выберите фирму, фактуру которой вы хотите загрузить:\n"
            "(Если нужной фирмы нет в списке, выберите **Ни одна из них**)",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    elif text == "📊 Открыть таблицу":
        await open_table_command(update, context)
    elif text == "⚙️ Настройки":
        await settings_command(update, context)
    elif text == "❓ Помощь":
        await help_command(update, context)
    else:
        await update.message.reply_text(
            "🤖 Я не понял это сообщение. Пожалуйста, используйте кнопки меню на панели ввода "
            "или просто отправьте фото/PDF фактуры.",
            reply_markup=get_main_keyboard()
        )


def main():
    """Запуск бота."""
    if not config.validate_config():
        logger.error("Запуск бота невозможен из-за ошибок конфигурации.")
        return

    logger.info("Запуск Faktura Bot...")
    
    # Инициализация приложения
    app = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).build()
    
    # Добавляем обработчик ConversationHandler для изменения настроек
    settings_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(edit_tax_callback, pattern="^edit_tax$"),
            CallbackQueryHandler(edit_margin_callback, pattern="^edit_margin$"),
            CallbackQueryHandler(edit_spreadsheet_callback, pattern="^edit_spreadsheet$"),
        ],
        states={
            AWAITING_TAX: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_tax_handler)
            ],
            AWAITING_MARGIN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_margin_handler)
            ],
            AWAITING_SPREADSHEET: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_spreadsheet_handler)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_settings),
            # Если пользователь нажимает кнопку из главного меню во время настройки
            MessageHandler(filters.Regex("^(📸 Загрузить фактуру|📊 Открыть таблицу|⚙️ Настройки|❓ Помощь)$"), cancel_settings)
        ],
        allow_reentry=True
    )
    app.add_handler(settings_conv)

    # Обработчик выбора конкретного парсера фирмы
    app.add_handler(CallbackQueryHandler(select_seller_callback, pattern="^select_seller:"))

    # Стандартные команды
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("table", open_table_command))

    # Обработка файлов (фото и документы)
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_document))

    # Обработка текстовых кнопок из главного меню
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_router))

    # Запуск polling
    app.run_polling()


if __name__ == "__main__":
    main()
