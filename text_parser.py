"""
Модуль парсинга текста фактур.

Извлекает структурированные данные из OCR-текста:
- Дата покупки
- Номер фактуры
- Товары: название, цена за единицу, количество, общая стоимость

Поддерживает различные форматы польских фактур.
"""

import re
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class InvoiceItem:
    """Один товар из фактуры."""

    name: str
    unit_price: float  # Цена закупки (за штуку)
    quantity: float  # Количество
    total_price: float  # Общая стоимость (unit_price × quantity)

    def __str__(self):
        return (
            f"{self.name}: {self.unit_price:.2f} × {self.quantity} "
            f"= {self.total_price:.2f}"
        )


@dataclass
class InvoiceData:
    """Данные извлечённые из фактуры."""

    date: str = ""  # Дата покупки
    invoice_number: str = ""  # Номер фактуры
    seller: str = ""  # Название продавца
    items: list = field(default_factory=list)  # Список InvoiceItem
    raw_text: str = ""  # Исходный OCR-текст (для отладки)

    @property
    def is_valid(self) -> bool:
        """Проверяет, что извлечены хотя бы какие-то данные."""
        return len(self.items) > 0

    @property
    def total_sum(self) -> float:
        """Общая сумма всех товаров."""
        return sum(item.total_price for item in self.items)


def parse_invoice_text(text: str) -> InvoiceData:
    """
    Парсит OCR-текст фактуры и извлекает данные.

    Args:
        text: Текст, извлечённый из фактуры через OCR.

    Returns:
        InvoiceData с извлечёнными данными.
    """
    invoice = InvoiceData(raw_text=text)

    # Извлекаем дату
    invoice.date = _extract_date(text)

    # Извлекаем продавца (dostawca/sprzedawca)
    invoice.seller = _extract_seller(text)

    # Извлекаем номер фактуры
    invoice.invoice_number = _extract_invoice_number(text, invoice.seller)

    # Извлекаем товары
    invoice.items = _extract_items(text, invoice.seller)

    logger.info(
        f"Парсинг завершён: продавец='{invoice.seller}', дата='{invoice.date}', "
        f"номер='{invoice.invoice_number}', "
        f"товаров={len(invoice.items)}"
    )

    return invoice


def _extract_date(text: str) -> str:
    """
    Извлекает дату покупки из текста фактуры.

    Поддерживаемые форматы:
    - DD.MM.YYYY, DD-MM-YYYY, DD/MM/YYYY
    - YYYY-MM-DD, YYYY.MM.DD, YYYY/MM/DD (ISO формат)
    - Data sprzedaży: DD.MM.YYYY или YYYY-MM-DD
    - Data wystawienia: DD.MM.YYYY или YYYY-MM-DD
    """
    # Шаблон даты: DD.MM.YYYY или YYYY-MM-DD
    date_regex = r"(\d{1,4}[.\-/]\d{1,2}[.\-/]\d{2,4})"
    
    # Сначала ищем дату с меткой (более точно)
    labeled_patterns = [
        rf"[Dd]ata\s+sprzeda[żz]y[:\s]+{date_regex}",
        rf"[Dd]ata\s+wystawienia[:\s]+{date_regex}",
        rf"[Dd]ata[:\s]+{date_regex}",
        rf"[Dd]nia[:\s]+{date_regex}",
    ]

    for pattern in labeled_patterns:
        match = re.search(pattern, text)
        if match:
            date_str = match.group(1)
            return _normalize_date(date_str)

    # Если не нашли с меткой, ищем просто дату
    # Сначала пробуем YYYY-MM-DD
    iso_pattern = r"(\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2})"
    match = re.search(iso_pattern, text)
    if match:
        return _normalize_date(match.group(1))
    
    # Затем DD.MM.YYYY
    dmy_pattern = r"(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{4})"
    match = re.search(dmy_pattern, text)
    if match:
        return _normalize_date(match.group(1))

    return ""


def _normalize_date(date_str: str) -> str:
    """Нормализует дату в формат DD.MM.YYYY."""
    # Заменяем разделители на точки
    normalized = date_str.replace("-", ".").replace("/", ".")

    # Проверяем формат и добавляем ведущие нули
    parts = normalized.split(".")
    if len(parts) == 3:
        # Определяем формат: YYYY-MM-DD или DD-MM-YYYY
        if len(parts[0]) == 4:
            # ISO формат: YYYY.MM.DD → DD.MM.YYYY
            year = parts[0]
            month = parts[1].zfill(2)
            day = parts[2].zfill(2)
        else:
            # Европейский формат: DD.MM.YYYY
            day = parts[0].zfill(2)
            month = parts[1].zfill(2)
            year = parts[2]
            if len(year) == 2:
                year = "20" + year
        return f"{day}.{month}.{year}"

    return date_str


def _extract_invoice_number(text: str, seller: str = None) -> str:
    """
    Извлекает номер фактуры.

    Поддерживаемые форматы:
    - Faktura VAT nr FV/2024/001
    - Faktura nr: 123/2024
    - FA-001/2024
    - FV 2024/001
    - Nr faktury: 123
    """
    # Нормализуем текст: объединяем строки, чтобы поймать многострочные номера
    # "Faktura VAT\nnr FS-192/26/SUR" → "Faktura VAT nr FS-192/26/SUR"
    normalized = re.sub(r'\s*\n\s*', ' ', text)
    normalized = re.sub(r'\s{2,}', ' ', normalized)

    # Специальный парсинг для Stoklasa: 10-значное число после Faktura или Faktura nr.
    if seller and "stoklasa" in seller.lower():
        match = re.search(r"Faktura\s+(?:nr\.?\s*)?(\d{9,11})\b", normalized, flags=re.IGNORECASE)
        if match:
            return match.group(1)

    patterns = [
        # Самые точные совпадения (с префиксами FV/FA/FS)
        r"\b[Nn]r\s+((?:FV|FA|FS)[/\-\s]*[\w/\-]+)",
        r"\b((?:FV|FA|FS)[/\-\s]*\d[\w/\-\s]*\d)\b",
        # Поиск nr после Faktura с ограничением расстояния, чтобы избежать ложных срабатываний
        r"[Ff]aktura.{0,40}?\bnr\s*[:\.]?\s*([\w/\-]+(?:[\s]+[\w/\-]+)*)",
        # "Faktura (VAT) nr FV 1/2015" или "Faktura nr: 123/2024"
        r"[Ff]aktura\s+(?:VAT\s+)?(?:[Nn]r\.?\s*:?\s*)([\w/\-]+(?:[\s]+[\w/\-]+)*)",
        r"[Nn]r\.?\s+faktury[:\s]+([\w/\-]+(?:[\s]+[\w/\-]+)*)",
        r"[Ff]aktura[:\s]+([\w/\-]+(?:[\s]+[\w/\-]+)*)",
    ]

    for pattern in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            number = match.group(1).strip()
            # Очистка от лишних пробелов вокруг /
            number = re.sub(r"\s*/\s*", "/", number)
            # Убираем хвостовые слова, которые не являются частью номера
            # (например, "Data" после номера)
            number = re.sub(r"\s+(Data|Termin|Metoda|Nabywca|Sprzedawca|Dostawca|Odbiorca|Uwagi).*$", "", number, flags=re.IGNORECASE)
            # Убираем лишние пробелы
            number = " ".join(number.split())
            if number:
                return number

    return ""


def _extract_items(text: str, seller: str = "-") -> list:
    """
    Извлекает товары из текста фактуры.

    Стратегия:
    1. Если продавец Stoklasa, используем специализированный парсер Stoklasa
    2. Иначе пробуем интеллектуальный парсер на основе кодов товаров и табуляции
    3. Если не сработало, используем стандартный табличный парсер
    4. Если таблица не найдена — пробуем гибкий построчный поиск
    """
    # 1. Если продавец Stoklasa, используем специализированный парсер
    if seller and "stoklasa" in seller.lower():
        try:
            items = _parse_stoklasa_items(text)
            if items:
                logger.info(f"Успешно извлечено {len(items)} товаров с помощью парсера Stoklasa.")
                return items
        except Exception as e:
            logger.error(f"Ошибка парсинга Stoklasa: {e}")

    # 1.5 Если продавец NATURAL, используем специализированный парсер
    if seller and "natural" in seller.lower():
        try:
            items = _parse_natural_items(text)
            if items:
                logger.info(f"Успешно извлечено {len(items)} товаров с помощью парсера NATURAL.")
                return items
        except Exception as e:
            logger.error(f"Ошибка парсинга NATURAL: {e}")

    # 1.6 Если продавец JURPOL, используем специализированный парсер
    if seller and "jurpol" in seller.lower():
        try:
            items = _parse_jurpol_items(text)
            if items:
                logger.info(f"Успешно извлечено {len(items)} товаров с помощью парсера JURPOL.")
                return items
        except Exception as e:
            logger.error(f"Ошибка парсинга JURPOL: {e}")

    # 1.7 Если продавец ALEXIS, используем специализированный парсер
    if seller and "alexis" in seller.lower():
        try:
            items = _parse_alexis_items(text)
            if items:
                logger.info(f"Успешно извлечено {len(items)} товаров с помощью парсера ALEXIS.")
                return items
        except Exception as e:
            logger.error(f"Ошибка парсинга ALEXIS: {e}")

    # 2. Пробуем интеллектуальный парсер
    try:
        items = _parse_table_code_and_tab_aware(text)
        if items:
            logger.info(f"Успешно извлечено {len(items)} товаров с помощью интеллектуального парсера.")
            return items
    except Exception as e:
        logger.error(f"Ошибка интеллектуального парсинга товаров: {e}")

    # Стандартный фолбек
    items = []
    lines = text.split("\n")
    lines = [line.strip() for line in lines if line.strip()]

    # Ищем начало таблицы товаров
    table_start = _find_table_start(lines)

    if table_start is not None:
        items = _parse_table_items(lines, table_start)

    # Если не нашли через таблицу — пробуем построчный парсинг
    if not items:
        items = _parse_items_flexible(lines)

    return items


def _find_table_start(lines: list) -> int | None:
    """
    Ищет начало таблицы товаров по заголовкам.

    Типичные заголовки польских фактур:
    - Lp. | Nazwa | Ilość | J.m. | Cena jedn. | Wartość | VAT
    - Nr | Opis | Ilość | Cena | Suma
    """
    header_keywords = [
        "nazwa",
        "ilo[sś][cć]",
        "cena",
        "warto[sś][cć]",
        "opis",
        "towar",
        "j\\.?\\s*m",
        "suma",
    ]

    for i, line in enumerate(lines):
        line_lower = line.lower()
        # Если строка содержит 2+ ключевых слова — это вероятно заголовок
        matches = sum(
            1 for kw in header_keywords if re.search(kw, line_lower)
        )
        if matches >= 2:
            return i

    return None


def _parse_table_items(lines: list, header_idx: int) -> list:
    """Парсит товары из таблицы, начиная со строки после заголовков."""
    items = []

    # Определяем конец таблицы
    end_keywords = [
        "razem", "suma", "do zapłaty", "do zaplaty",
        "łącznie", "lacznie", "ogółem", "ogolem",
        "sposób", "sposob", "płatność", "platnosc",
        "termin", "uwagi", "podpis",
    ]

    # Определяем, есть ли в таблице колонка Lp. (порядковый номер)
    # Проверяем первые несколько строк. Если они начинаются с цифры, то Lp есть.
    has_lp = False
    valid_lines_count = 0
    lines_starting_with_digit = 0
    
    for i in range(header_idx + 1, min(header_idx + 6, len(lines))):
        l = lines[i].strip()
        if not l or any(kw in l.lower() for kw in end_keywords):
            break
        # Строка должна содержать хотя бы 2 числа, чтобы считаться товарной строкой
        if len(_extract_numbers(l)) >= 2:
            valid_lines_count += 1
            cleaned_start = l.lstrip(" |│┃\t")
            if cleaned_start and cleaned_start[0].isdigit():
                lines_starting_with_digit += 1
                
    if valid_lines_count > 0 and (lines_starting_with_digit / valid_lines_count) >= 0.5:
        has_lp = True

    for i in range(header_idx + 1, len(lines)):
        line = lines[i].strip()
        if not line:
            continue

        # Проверяем, не достигли ли конца таблицы
        line_lower = line.lower()
        if any(kw in line_lower for kw in end_keywords):
            break

        # Проверяем на многострочное описание (continuation line)
        is_continuation = False
        if items:
            cleaned_start = line.lstrip(" |│┃\t")
            if has_lp:
                # Если в таблице есть Lp., строка без ведущей цифры — это продолжение названия
                if not (cleaned_start and cleaned_start[0].isdigit()):
                    is_continuation = True
            else:
                # Если Lp. нет, строка считается продолжением, если в ней нет достаточного количества чисел
                # или если числа не сходятся математически
                numbers = _extract_numbers(line)
                if len(numbers) < 2:
                    is_continuation = True
                elif len(numbers) >= 3:
                    q, p, t = _determine_price_quantity(numbers)
                    expected = q * p
                    if abs(expected - t) > (t * 0.15):
                        is_continuation = True

        if is_continuation:
            cleaned_addition = _extract_item_name(line)
            if cleaned_addition:
                items[-1].name = f"{items[-1].name} {cleaned_addition}"
            continue

        # Пробуем извлечь товар из строки
        item = _parse_item_line(line)
        if item:
            items.append(item)
        else:
            # Если строка не распарсилась, но у нас есть предыдущий товар,
            # и в строке нет явных признаков других сущностей, считаем её продолжением
            if items:
                cleaned_addition = _extract_item_name(line)
                if cleaned_addition:
                    items[-1].name = f"{items[-1].name} {cleaned_addition}"

    return items


def _parse_item_line(line: str) -> InvoiceItem | None:
    """
    Пробует извлечь товар из одной строки таблицы.

    Типичные форматы строк:
    - 1 Towar ABC 10 szt. 25,50 255,00
    - 1. Nazwa towaru 5 25.50 127.50
    - Towar 10x25,00=250,00
    """
    # Очищаем строку от процентов (ставок НДС, например, 23%, 8%), чтобы они не мешали распознавать числа
    cleaned_line = re.sub(r"\b\d+\s*%\s*", " ", line)
    
    # Убираем порядковый номер в начале строки, если он отделен точкой, скобкой или вертикальной чертой
    cleaned_line = re.sub(r"^\s*\d+\s*[.|\)]\s*", " ", cleaned_line)
    
    # Ищем все числа в очищенной строке
    numbers = _extract_numbers(cleaned_line)

    if len(numbers) < 2:
        return None

    # Извлекаем текстовую часть (название товара)
    name = _extract_item_name(line)

    if not name or len(name) < 2:
        return None

    # Определяем цену, количество, сумму по позиции в строке
    if len(numbers) >= 3:
        # Типичный формат: количество, цена_за_шт, сумма
        # Но порядок может отличаться — берём наиболее вероятный
        quantity, unit_price, total = _determine_price_quantity(numbers)
    elif len(numbers) == 2:
        # Два числа: предполагаем цена и количество
        n1, n2 = numbers[0], numbers[1]
        if n1 >= 1 and n1 == int(n1) and n1 < n2:
            # Первое — количество, второе — цена
            quantity = n1
            unit_price = n2
        elif n2 >= 1 and n2 == int(n2) and n2 < n1:
            quantity = n2
            unit_price = n1
        else:
            quantity = 1
            unit_price = n1
        total = unit_price * quantity
    else:
        return None

    if unit_price <= 0:
        return None

    return InvoiceItem(
        name=name,
        unit_price=round(unit_price, 2),
        quantity=quantity,
        total_price=round(total, 2),
    )


def _extract_numbers(text: str) -> list:
    """
    Извлекает все числа из строки.

    Поддерживает форматы:
    - 1234 (целое)
    - 12,50 или 12.50 (десятичное)
    - 1 234,50 (с пробелом как разделителем тысяч)
    """
    # Находим числа в различных форматах
    # Порядок: сначала числа с десятичной частью (до 4 десятичных знаков), потом целые.
    # Используем [\\d ]* вместо [\\d\\s]* чтобы предотвратить захват табов \\t между колонками.
    pattern = r"(\d+(?: \d+)*[,\.]\d{1,4}|\d+)"
    raw_matches = re.findall(pattern, text)

    numbers = []
    for match in raw_matches:
        try:
            num = _parse_number(match.strip())
            if num is not None:
                numbers.append(num)
        except ValueError:
            continue

    return numbers


def _parse_number(text: str) -> float | None:
    """
    Парсит число из строки.

    Обрабатывает форматы:
    - "1234" → 1234.0
    - "12,50" → 12.50
    - "12.50" → 12.50
    - "1 234,50" → 1234.50
    """
    if not text:
        return None

    # Убираем пробелы (разделители тысяч)
    cleaned = text.replace(" ", "")

    # Заменяем запятую на точку
    cleaned = cleaned.replace(",", ".")

    try:
        return float(cleaned)
    except ValueError:
        return None


def _extract_item_name(line: str) -> str:
    """
    Извлекает название товара из строки, убирая числа и единицы измерения.
    """
    # 1. Убираем порядковый номер в начале (1., 2., 1), 2) и т.д., а также с вертикальной чертой)
    cleaned = re.sub(r"^\s*\d+\s*[.|\)]\s*", "", line)

    # 2. Убираем ставки VAT (до удаления отдельных цифр!)
    cleaned = re.sub(r"\b\d{1,2}\s*%\s*", "", cleaned)
    cleaned = re.sub(r"\bzw\.?\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bnp\.?\b", "", cleaned, flags=re.IGNORECASE)

    # 3. Убираем единицы измерения (включая опечатки OCR типа tsz.)
    units = [
        "szt", "szt.", "tsz.", "tsz", "sztuk", "kpl", "kpl.", "komplet",
        "kg", "g", "l", "ml", "m", "m2", "m3", "mb",
        "op", "op.", "opak", "opak.",
        "para", "zest", "zest.", "zestaw",
        "usł", "usl", "godz",
    ]
    for unit in units:
        cleaned = re.sub(rf"\b{re.escape(unit)}\b", "", cleaned, flags=re.IGNORECASE)

    # 4. Убираем числа с десятичной частью (до 4 знаков)
    cleaned = re.sub(r"\d[\d\s]*[,\.]\d{1,4}", "", cleaned)

    # 5. Убираем только отдельно стоящие целые числа (не трогаем дефисы в кодах вроде HFT-3-PERLA)
    cleaned = re.sub(r"(?<![\w\-])\d+(?![\w\-])", "", cleaned)

    # 6. Убираем пустые скобки, которые могли остаться после удаления чисел
    cleaned = re.sub(r"\(\s*\)", "", cleaned)
    cleaned = re.sub(r"\[\s*\]", "", cleaned)

    # 7. Убираем лишние разделители и пробелы
    cleaned = re.sub(r"[|│┃]", " ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = cleaned.strip(" .\t-")

    return cleaned


def _determine_price_quantity(numbers: list) -> tuple:
    """
    Определяет, какие числа — количество, цена и сумма.

    Логика:
    - Если последнее число ≈ произведение двух других → это сумма
    - Количество обычно целое число и меньше цены
    - Предпочитается естественный порядок: Количество < Цена < Сумма в строке
    """
    if len(numbers) < 3:
        return 1, numbers[0], numbers[0]

    # Берём последние 3 числа (первые могут быть порядковым номером и т.д.)
    nums = numbers[-3:]

    # Пробуем все комбинации
    best = None
    best_diff = float("inf")

    for qi in range(3):
        for pi in range(3):
            if qi == pi:
                continue
            ti = 3 - qi - pi
            q, p, t = nums[qi], nums[pi], nums[ti]

            if q <= 0 or p <= 0:
                continue

            expected_total = q * p
            diff = abs(expected_total - t)

            # Предпочитаем комбинации где количество — целое, но не наказываем дробные количества меньше 1
            penalty = 0 if (q == int(q) or q < 1.0) else 10
            diff += penalty

            # Значительное преимущество для естественного порядка: Количество < Цена < Сумма
            if qi < pi < ti:
                diff -= 15.0  # Перекрывает штраф за дробное количество

            if diff < best_diff:
                best_diff = diff
                best = (q, p, t)

    if best and best_diff < best[2] * 0.1 or (best and best_diff < 0):  # Допуск 10% или идеальный порядок со скидкой
        # Если была скидка, восстанавливаем исходные значения для возврата
        # Но нам нужны исходные q, p, t
        # Найдем оригинальные q, p, t для лучшей комбинации без учета скидки
        # На самом деле best содержит верные q, p, t, так как мы просто минимизировали diff для выбора
        return best

    # Не удалось определить — берём простой вариант
    # Предполагаем: количество, цена, сумма (в порядке появления)
    return nums[0], nums[1], nums[2]


def _parse_items_flexible(lines: list) -> list:
    """
    Гибкий парсинг товаров — пробует найти товарные строки
    без привязки к таблице.

    Ищет строки, содержащие текст + числа (цена, количество).
    """
    items = []

    # Пропускаем строки с заголовками/шапкой
    skip_keywords = [
        "faktura", "nip", "regon", "adres", "sprzedawca", "nabywca",
        "odbiorca", "bank", "konto", "telefon", "tel.", "email",
        "www", "ulica", "ul.", "kod", "miasto",
    ]

    for line in lines:
        line_lower = line.lower().strip()

        # Пропускаем заголовки
        if any(kw in line_lower for kw in skip_keywords):
            continue

        # Пропускаем слишком короткие строки
        if len(line.strip()) < 5:
            continue

        # Пробуем извлечь товар
        item = _parse_item_line(line)
        if item:
            items.append(item)

    return items


def calculate_new_prices(
    items: list,
    tax_percent: float,
    margin_percent: float,
) -> list:
    """
    Рассчитывает новые цены для каждого товара.

    Формула:
        new_price = unit_price + (unit_price × tax%) + (unit_price × margin%)
        new_price = unit_price × (1 + tax_percent/100 + margin_percent/100)

    Args:
        items: Список InvoiceItem.
        tax_percent: Процент налога (например, 5).
        margin_percent: Процент маржи (например, 40).

    Returns:
        Список словарей с рассчитанными ценами.
    """
    results = []

    for item in items:
        tax_amount = item.unit_price * (tax_percent / 100)
        margin_amount = item.unit_price * (margin_percent / 100)
        new_unit_price = item.unit_price + tax_amount + margin_amount
        new_total_price = new_unit_price * item.quantity

        results.append(
            {
                "name": item.name,
                "unit_price": round(item.unit_price, 2),
                "quantity": item.quantity,
                "total_price": round(item.total_price, 2),
                "tax_percent": tax_percent,
                "margin_percent": margin_percent,
                "new_unit_price": round(new_unit_price, 2),
                "new_total_price": round(new_total_price, 2),
            }
        )

    return results


def _parse_table_code_and_tab_aware(text: str) -> list:
    """
    Интеллектуальный парсинг таблицы товаров на основе кодов и табуляции.
    Идеально подходит для фактур с многострочными названиями и сложной разметкой.
    """
    lines = text.split("\n")
    cleaned_lines = [l.strip() for l in lines if l.strip()]

    # Ищем начало таблицы товаров
    start_idx = 0
    for idx, line in enumerate(cleaned_lines):
        line_lower = line.lower()
        if "nazwa towaru" in line_lower or ("kod" in line_lower and "cena" in line_lower):
            start_idx = idx + 1
            break

    if start_idx >= len(cleaned_lines):
        return []

    end_keywords = ["razem", "suma", "do zapłaty", "do zaplaty", "łącznie", "lacznie", "ogółem", "ogolem"]

    raw_items = []
    
    # Шаблон кода товара: 2-10 заглавных букв, затем дефис и продолжение кода (не цифры в начале!)
    code_pattern = re.compile(r"\b[A-ZÜÄÖĆŁŚŹŻ]{2,10}-[\w\-]+\b")
    unit_pattern = re.compile(r"(\d[\d ]*[,\.]\d{1,4}|\d+)\s*(tsz|mb|szt|kpl|kg|op|opak|t52)", re.IGNORECASE)

    # Проверяем наличие кодов в таблице
    has_codes = False
    for line in cleaned_lines[start_idx:]:
        line_lower = line.lower()
        if any(ek in line_lower for ek in end_keywords):
            break
        parts = [p.strip() for p in re.split(r"\t|\|", line) if p.strip()]
        for part in parts:
            match = code_pattern.search(part)
            if match:
                code_str = match.group(0)
                if f"({code_str}" not in part and f"{code_str})" not in part:
                    if "ZS-" not in part and "FS-" not in part:
                        has_codes = True
                        break
        if has_codes:
            break
            
    if not has_codes:
        return []

    for idx in range(start_idx, len(cleaned_lines)):
        line = cleaned_lines[idx]
        line_lower = line.lower()
        if any(ek in line_lower for ek in end_keywords):
            break

        # Игнорируем футеры и служебные строки
        if "comarch erp" in line_lower or "strona:" in line_lower or "wersja" in line_lower:
            continue

        # Разделяем по табуляции или вертикальной черте |
        parts = [p.strip() for p in re.split(r"\t|\|", line) if p.strip()]
        if not parts:
            continue

        # Проверяем, начинается ли строка с порядкового номера (Lp. / №)
        starts_with_lp = False
        if parts[0].isdigit():
            val = int(parts[0])
            if 1 <= val <= 100:
                starts_with_lp = True

        # Проверяем наличие кода товара в колонках
        code_match = None
        code_part_idx = -1
        for p_idx, part in enumerate(parts):
            match = code_pattern.search(part)
            if match:
                code_str = match.group(0)
                # Игнорируем коды в круглых скобках (это часть описания)
                if f"({code_str}" in part or f"{code_str})" in part:
                    continue
                if "ZS-" not in part and "FS-" not in part:
                    code_match = code_str
                    code_part_idx = p_idx
                    break

        # Определяем временные числа из правой части строки для проверки на новый товар
        temp_name_idx = code_part_idx if code_part_idx != -1 else (1 if starts_with_lp and len(parts) > 1 else 0)
        temp_data_parts = parts[temp_name_idx + 1:]
        temp_numbers = []
        for dp in temp_data_parts:
            if "%" in dp:
                continue
            col_nums = re.findall(r"(\d[\d ]*[,\.]\d{1,4}|\d+)", dp)
            if col_nums:
                val = float(col_nums[0].replace(" ", "").replace(",", "."))
                if val >= 100000 and val == int(val):
                    continue
                temp_numbers.append(val)

        is_new_item = (code_match is not None) or (starts_with_lp and len(temp_numbers) >= 2)

        if is_new_item:
            # Определяем колонку названия/кода товара
            name_idx = temp_name_idx
            name = parts[name_idx]
            
            # Удаляем sequence numbers и мусор перед кодом товара
            if code_match:
                idx_code = name.find(code_match)
                if idx_code != -1:
                    name = name[idx_code:]
            else:
                name = re.sub(r"^\s*\d+\s+", "", name)

            data_parts = temp_data_parts
            
            # Извлекаем числа из колонок данных
            numbers = []
            for dp in data_parts:
                if "%" in dp:
                    continue
                col_nums = re.findall(r"(\d[\d ]*[,\.]\d{1,4}|\d+)", dp)
                if col_nums:
                    val = float(col_nums[0].replace(" ", "").replace(",", "."))
                    if val >= 100000 and val == int(val):
                        continue
                    numbers.append(val)

            # Проверяем явное указание количества с единицей измерения
            qty = None
            qty_match = unit_pattern.search(line)
            if qty_match:
                qty = float(qty_match.group(1).replace(" ", "").replace(",", "."))

            q, p, t = _determine_price_quantity_robust(numbers, qty)

            current_item = {
                "name": name,
                "quantity": q,
                "unit_price": p,
                "total_price": t,
                "numbers": numbers,
                "qty_override": qty
            }
            raw_items.append(current_item)
            
        elif raw_items:
            # Это строка-продолжение (описание или перенесённые цены)
            current_item = raw_items[-1]
            desc_part = ""
            for p in parts:
                if not re.match(r"^\d[\d ]*[,\.]\d{1,4}$|^\d+$", p) and "%" not in p:
                    desc_part = p
                    break

            if desc_part:
                cleaned_desc = _clean_product_name_robust(desc_part)
                if cleaned_desc:
                    current_item["name"] = f"{current_item['name']} {cleaned_desc}"

            # Извлекаем числа из остальных колонок
            extra_numbers = []
            for p in parts:
                if p == desc_part or "%" in p:
                    continue
                col_nums = re.findall(r"(\d[\d ]*[,\.]\d{1,4}|\d+)", p)
                if col_nums:
                    val = float(col_nums[0].replace(" ", "").replace(",", "."))
                    if val >= 100000 and val == int(val):
                        continue
                    extra_numbers.append(val)

            if extra_numbers:
                current_item["numbers"].extend(extra_numbers)
                q, p, t = _determine_price_quantity_robust(current_item["numbers"], current_item["qty_override"])
                current_item["quantity"] = q
                current_item["unit_price"] = p
                current_item["total_price"] = t

    # Маппим результаты в InvoiceItem
    results = []
    for item in raw_items:
        # Дополнительно очищаем имя перед сохранением
        final_name = _clean_product_name_robust(item["name"])
        # Убираем ведущие цифры Lp., если они склеились с названием
        final_name = re.sub(r"^\s*\d+\s+", "", final_name)
        if len(final_name) >= 2:
            results.append(
                InvoiceItem(
                    name=final_name,
                    unit_price=round(item["unit_price"], 2),
                    quantity=item["quantity"],
                    total_price=round(item["total_price"], 2)
                )
            )
            
    return results


def _clean_product_name_robust(text: str) -> str:
    """Очищает строку от мусорных чисел, процентов и единиц измерения."""
    cleaned = re.sub(r"^\s*\d+\s*[.|\)]?\s*", "", text)
    cleaned = re.sub(r"\b\d{1,2}\s*%\s*", "", cleaned)
    cleaned = re.sub(r"\bzw\.?\b", "", cleaned, flags=re.IGNORECASE)
    units = ["szt", "szt.", "tsz.", "tsz", "sztuk", "kpl", "kpl.", "komplet", "kg", "mb", "op", "opak", "t52"]
    for unit in units:
        cleaned = re.sub(rf"\b{re.escape(unit)}\b", "", cleaned, flags=re.IGNORECASE)
    # We do not aggressively strip all numbers here because parts are already separated by tabs,
    # and stripping numbers destroys valid model numbers like "6158", "2241", etc.
    cleaned = re.sub(r"\(\s*\)", "", cleaned)
    cleaned = re.sub(r"\[\s*\]", "", cleaned)
    cleaned = re.sub(r"[|│┃]", " ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip(" .\t-")


def _determine_price_quantity_robust(numbers: list, known_qty: float = None) -> tuple:
    """Вычисляет цену, количество и сумму по списку чисел."""
    if len(numbers) == 0:
        return known_qty if known_qty is not None else 1.0, 0.0, 0.0
        
    if known_qty is not None:
        best_price = None
        best_total = None
        best_diff = float("inf")
        
        for i, n in enumerate(numbers):
            if n <= 0: continue
            expected_total = known_qty * n
            for j, other in enumerate(numbers):
                if i == j: continue
                diff = abs(expected_total - other)
                if diff < best_diff:
                    best_diff = diff
                    best_price = n
                    best_total = other
                    
        if best_price is not None and best_diff < best_total * 0.15:
            return known_qty, best_price, best_total
            
        other_nums = [n for n in numbers if n != known_qty]
        if len(other_nums) >= 1:
            p = other_nums[0]
            return known_qty, p, round(known_qty * p, 2)
        return known_qty, numbers[0], round(known_qty * numbers[0], 2)

    # Если количество не задано
    if len(numbers) == 1:
        return 1.0, numbers[0], numbers[0]
    if len(numbers) == 2:
        n1, n2 = numbers[0], numbers[1]
        if abs(n1 - n2) < (n1 * 0.01):
            return 1.0, n1, n2
        if n1 < n2 or n1 < 1.0:
            return n1, n2, round(n1 * n2, 2)
        else:
            return n2, n1, round(n1 * n2, 2)

    best = None
    best_diff = float("inf")
    
    for i in range(len(numbers)):
        for j in range(len(numbers)):
            if i == j: continue
            for k in range(len(numbers)):
                if k == i or k == j: continue
                q, p, t = numbers[i], numbers[j], numbers[k]
                if q <= 0 or p <= 0 or t <= 0: continue
                
                expected = q * p
                diff = abs(expected - t)
                
                if diff > (t * 0.15):
                    continue
                
                penalty = 0
                if q != int(q) and q >= 1.0:
                    penalty += 10.0
                
                if i < j < k:
                    diff -= 5.0
                
                diff += penalty
                
                if diff < best_diff:
                    best_diff = diff
                    best = (q, p, t)

    if best:
        return best
        
    return numbers[0], numbers[1], numbers[2]


def _extract_seller(text: str) -> str:
    """
    Определяет продавца по тексту фактуры.
    """
    text_lower = text.lower()
    
    # 1. Проверяем на Stoklasa
    if "stoklasa" in text_lower:
        return "Stoklasa"
        
    # 2. Проверяем на NATURAL
    if "natural" in text_lower and "walczak" in text_lower:
        return "NATURAL"
        
    # 2. Проверяем на GAIA
    if "gaia" in text_lower or "skravki" in text_lower or "542-24-38-603" in text_lower or "5422438603" in text_lower:
        return '"GAIA" Sp. z o.o.'
        
    # 3. Проверяем на JURPOL
    if "jurpol" in text_lower or "gąsiorek" in text_lower or "gasiorek" in text_lower or "7251086439" in text_lower:
        return "JURPOL"
        
    # 4. Проверяем на ALEXIS
    if "alexis" in text_lower or "mikucki" in text_lower or "524-020-26-22" in text_lower or "5240202622" in text_lower:
        return "ALEXIS"
        
    # 3. Дефолтный или пытаемся извлечь из "Sprzedawca:"
    sprzedawca_patterns = [
        r"Sprzedawca[:\s]+([^\n\t|]+)",
        r"Dostawca[:\s]+([^\n\t|]+)"
    ]
    for pattern in sprzedawca_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            seller = match.group(1).strip()
            # Очистка
            seller = re.sub(r'\s+', ' ', seller)
            if seller and len(seller) > 2:
                return seller
                
    return "-"


def _extract_invoice_row_numbers(text: str) -> list:
    """
    Интеллектуально извлекает числа из числовой части строки товара.
    Убирает единицы измерения (включая опечатки OCR типа S2t -> szt) и проценты,
    после чего парсит все валидные float.
    """
    # 1. Заменяем s2t/S2t на szt
    cleaned = re.sub(r"\bs2t\b", "szt", text, flags=re.IGNORECASE)
    # 2. Разделяем слипшиеся буквы и цифры (например, 15mb -> 15 mb)
    cleaned = re.sub(r"(\d+)([a-zA-Z]+)", r"\1 \2", cleaned)
    cleaned = re.sub(r"([a-zA-Z]+)(\d+)", r"\1 \2", cleaned)
    # 3. Убираем единицы измерения
    units_to_remove = ["sztuka", "sztuk", "szt", "tsz", "kpl", "komplet", "kg", "mb", "op", "opak"]
    for unit in units_to_remove:
        cleaned = re.sub(rf"\b{re.escape(unit)}\b", " ", cleaned, flags=re.IGNORECASE)
    # 4. Убираем %
    cleaned = cleaned.replace("%", " ")
    
    # 5. Извлекаем числа
    nums = []
    for p in cleaned.split():
        match = re.search(r"(\d+[\.,]?\d*)", p)
        if match:
            try:
                nums.append(float(match.group(1).replace(",", ".")))
            except ValueError:
                pass
    return nums


def _parse_natural_items(text: str) -> list:
    """
    Специализированный парсер для фактур NATURAL.
    """
    import logging
    with open("natural_raw.txt", "w", encoding="utf-8") as f:
        f.write(text)
    
    lines = text.split("\n")
    cleaned_lines = [l.strip() for l in lines if l.strip()]

    raw_items = []
    
    for line in cleaned_lines:
        parts = [p.strip() for p in re.split(r"\t|\|", line) if p.strip()]
        
        if len(parts) < 3:
            continue
            
        # Проверяем, является ли первый элемент номером строки (Lp.)
        # Номер строки может содержать мусорные знаки типа | или !, очистим их для проверки.
        match = re.match(r"^(\d+)\s*(?:[|!]\s*)?", parts[0])
        if match:
            lp_val = int(match.group(1))
            if 1 <= lp_val <= 100:
                name_part = parts[0][match.end():].strip()
                if name_part:
                    name = name_part
                    rest_parts = parts[1:]
                else:
                    name = parts[1]
                    rest_parts = parts[2:]
            else:
                name = parts[0]
                rest_parts = parts[1:]
        else:
            name = parts[0]
            rest_parts = parts[1:]
            
        # Исключаем строки итогов
        name_lower = name.lower()
        if any(keyword in name_lower for keyword in ["razem", "w tym", "suma", "dostawca", "odbiorca", "nabywca", "sprzedawca"]):
            continue
            
        logging.info(f"Processing line: {line}")
        
        # Извлекаем все числа из части строки после названия товара
        rest_of_line = " ".join(rest_parts)
        nums = _extract_invoice_row_numbers(rest_of_line)
                    
        # У нас должно быть минимум 4 числа (если кол-во или НДС пропущены)
        if len(nums) >= 4:
            brutto = nums[-1]
            vat_kwota = nums[-2]
            
            # Проверяем, есть ли ставка НДС перед kwota VAT
            if len(nums) >= 6:
                if 0 <= nums[-3] <= 100:
                    vat_rate = nums[-3] / 100.0
                    netto_wartosc = nums[-4]
                    netto_cena = nums[-5]
                    qty = nums[-6]
                else:
                    vat_rate = 0.23
                    netto_wartosc = nums[-3]
                    netto_cena = nums[-4]
                    qty = nums[-5]
            elif len(nums) == 5:
                if 0 <= nums[-3] <= 100:
                    vat_rate = nums[-3] / 100.0
                    netto_wartosc = nums[-4]
                    netto_cena = nums[-5]
                    qty = round(netto_wartosc / netto_cena, 2) if netto_cena > 0 else 1.0
                else:
                    vat_rate = 0.23
                    netto_wartosc = nums[-3]
                    netto_cena = nums[-4]
                    qty = nums[-5]
            else: # len(nums) == 4
                if 0 <= nums[-3] <= 100:
                    vat_rate = nums[-3] / 100.0
                    netto_cena = nums[-4]
                else:
                    vat_rate = 0.23
                    netto_cena = nums[-3]
                netto_wartosc = brutto - vat_kwota
                qty = round(netto_wartosc / netto_cena, 2) if netto_cena > 0 else 1.0
                
            # Цена закупки = Cena netto + VAT
            unit_price = round(netto_cena * (1 + vat_rate), 2)
            name = _clean_product_name_robust(name)
            
            if len(name) < 2:
                continue
            
            raw_items.append(
                InvoiceItem(
                    name=name,
                    quantity=qty,
                    unit_price=unit_price,
                    total_price=brutto
                )
            )
            
    return raw_items


def _parse_alexis_items(text: str) -> list:
    """
    Специализированный парсер для фактур ALEXIS.
    Учитывает возможный сдвиг строк (когда название на одной строке, а числа сдвинуты).
    """
    with open("alexis_raw.txt", "w", encoding="utf-8") as f:
        f.write(text)
        
    lines = text.split("\n")
    cleaned_lines = [l.strip() for l in lines if l.strip()]
    
    # Находим границы таблицы товаров
    start_idx = None
    end_idx = None
    
    for idx, line in enumerate(cleaned_lines):
        line_lower = line.lower()
        if "symbol / cn / pkwiu" in line_lower:
            start_idx = idx + 1
        elif "wartość w grupach vat" in line_lower or "razem wartość" in line_lower:
            end_idx = idx
            break
            
    if start_idx is None:
        # Пытаемся найти начало по ключевым словам
        for idx, line in enumerate(cleaned_lines):
            line_lower = line.lower()
            if "tkanina" in line_lower and ("tipo" in line_lower or "tip0" in line_lower):
                start_idx = idx
                break
                
    if start_idx is None:
        return []
        
    if end_idx is None or end_idx <= start_idx:
        # Если конец не нашли, берем 15 строк после начала
        end_idx = min(start_idx + 15, len(cleaned_lines))
        
    table_lines = cleaned_lines[start_idx:end_idx]
    
    # Извлекаем названия и блоки чисел
    names = []
    num_blocks = []
    
    for line in table_lines:
        code_match = re.search(r"\b(TIP[O0]?\d+)\b", line, re.IGNORECASE)
        if code_match:
            parts = line.split(code_match.group(1), 1)
            after_code = parts[1]
            parts_after = [p.strip() for p in re.split(r"\t|\|", after_code) if p.strip()]
            if parts_after:
                names.append(parts_after[0])
                num_blocks.append(parts_after[1:])
            else:
                names.append("")
                num_blocks.append([])
        else:
            parts = [p.strip() for p in re.split(r"\t|\|", line) if p.strip()]
            names.append(None)
            num_blocks.append(parts)
            
    if not names:
        return []
        
    # Проверяем сдвиг: если на первой строке нет названия (None), а на последней строке нет чисел (пустой массив)
    if names[0] is None and len(num_blocks[-1]) == 0:
        aligned_names = [n for n in names if n is not None]
        aligned_num_blocks = [nb for nb in num_blocks if len(nb) > 0]
    else:
        aligned_names = [n for n in names if n is not None]
        aligned_num_blocks = [nb for n, nb in zip(names, num_blocks) if n is not None]
        
    raw_items = []
    
    for name, block in zip(aligned_names, aligned_num_blocks):
        rest_of_line = " ".join(block)
        nums = _extract_invoice_row_numbers(rest_of_line)
        
        if len(nums) >= 3:
            if len(nums) >= 7:
                brutto = nums[-1]
                vat_kwota = nums[-2]
                if 0 <= nums[-3] <= 100:
                    vat_rate = nums[-3] / 100.0
                    netto_wartosc = nums[-4]
                    netto_cena = nums[-5]
                    qty = nums[-7]
                else:
                    vat_rate = 0.23
                    netto_wartosc = nums[-3]
                    netto_cena = nums[-4]
                    qty = nums[-5]
            elif len(nums) == 6:
                brutto = nums[-1]
                vat_kwota = nums[-2]
                if 0 <= nums[-3] <= 100:
                    vat_rate = nums[-3] / 100.0
                    netto_wartosc = nums[-4]
                    netto_cena = nums[-5]
                    qty = nums[-6]
                else:
                    vat_rate = 0.23
                    netto_wartosc = nums[-3]
                    netto_cena = nums[-4]
                    qty = nums[-5]
            elif len(nums) == 5:
                brutto = nums[-1]
                vat_kwota = nums[-2]
                if 0 <= nums[-3] <= 100:
                    vat_rate = nums[-3] / 100.0
                    netto_wartosc = nums[-4]
                    netto_cena = nums[-5]
                    qty = round(netto_wartosc / netto_cena, 2) if netto_cena > 0 else 1.0
                else:
                    vat_rate = 0.23
                    netto_wartosc = nums[-3]
                    netto_cena = nums[-4]
                    qty = nums[-5]
            elif len(nums) == 4:
                brutto = nums[-1]
                vat_kwota = nums[-2]
                if 0 <= nums[-3] <= 100:
                    vat_rate = nums[-3] / 100.0
                    netto_cena = nums[-4]
                else:
                    vat_rate = 0.23
                    netto_cena = nums[-3]
                netto_wartosc = brutto - vat_kwota
                qty = round(netto_wartosc / netto_cena, 2) if netto_cena > 0 else 1.0
            else: # len(nums) == 3
                vat_rate = 0.23
                netto_cena = nums[-1]
                qty = nums[-3]
                netto_wartosc = qty * netto_cena
                brutto = round(netto_wartosc * 1.23, 2)
                
            unit_price = round(netto_cena * (1 + vat_rate), 2)
            name = _clean_product_name_robust(name)
            
            if len(name) < 2:
                continue
                
            raw_items.append(
                InvoiceItem(
                    name=name,
                    quantity=qty,
                    unit_price=unit_price,
                    total_price=brutto
                )
            )
            
    return raw_items


def _parse_jurpol_items(text: str) -> list:
    """
    Специализированный парсер для фактур JURPOL.
    """
    import logging
    with open("jurpol_raw.txt", "w", encoding="utf-8") as f:
        f.write(text)
    
    lines = text.split("\n")
    cleaned_lines = [l.strip() for l in lines if l.strip()]

    raw_items = []
    
    for line in cleaned_lines:
        parts = [p.strip() for p in re.split(r"\t|\|", line) if p.strip()]
        
        if len(parts) < 3:
            continue
            
        # Проверяем, является ли первый элемент номером строки (Lp.)
        # Номер строки может содержать мусорные знаки типа | или !, очистим их для проверки.
        match = re.match(r"^(\d+)\s*(?:[|!]\s*)?", parts[0])
        if match:
            lp_val = int(match.group(1))
            if 1 <= lp_val <= 100:
                name_part = parts[0][match.end():].strip()
                if name_part:
                    name = name_part
                    rest_parts = parts[1:]
                else:
                    name = parts[1]
                    rest_parts = parts[2:]
            else:
                name = parts[0]
                rest_parts = parts[1:]
        else:
            name = parts[0]
            rest_parts = parts[1:]
            
        # Исключаем строки итогов
        name_lower = name.lower()
        if any(keyword in name_lower for keyword in ["razem", "w tym", "suma", "dostawca", "odbiorca", "nabywca", "sprzedawca"]):
            continue
            
        logging.info(f"Processing line: {line}")
        
        # Извлекаем все числа из части строки после названия товара
        rest_of_line = " ".join(rest_parts)
        nums = _extract_invoice_row_numbers(rest_of_line)
                    
        # У нас должно быть минимум 4 числа
        if len(nums) >= 4:
            brutto = nums[-1]
            vat_kwota = nums[-2]
            
            # Различные сценарии в зависимости от количества распознанных чисел
            if len(nums) >= 6:
                if 0 <= nums[-3] <= 100:
                    vat_rate = nums[-3] / 100.0
                    netto_wartosc = nums[-4]
                    netto_cena = nums[-5]
                    qty = nums[-6]
                else:
                    vat_rate = 0.23
                    netto_wartosc = nums[-3]
                    netto_cena = nums[-4]
                    qty = nums[-5]
            elif len(nums) == 5:
                if 0 <= nums[-3] <= 100:
                    vat_rate = nums[-3] / 100.0
                    netto_wartosc = nums[-4]
                    netto_cena = nums[-5]
                    qty = round(netto_wartosc / netto_cena, 2) if netto_cena > 0 else 1.0
                else:
                    vat_rate = 0.23
                    netto_wartosc = nums[-3]
                    netto_cena = nums[-4]
                    qty = nums[-5]
            else: # len(nums) == 4
                if 0 <= nums[-3] <= 100:
                    vat_rate = nums[-3] / 100.0
                    netto_cena = nums[-4]
                else:
                    vat_rate = 0.23
                    netto_cena = nums[-3]
                netto_wartosc = brutto - vat_kwota
                qty = round(netto_wartosc / netto_cena, 2) if netto_cena > 0 else 1.0
                
            # Цена закупки = Cena netto + VAT
            unit_price = round(netto_cena * (1 + vat_rate), 2)
            name = _clean_product_name_robust(name)
            
            if len(name) < 2:
                continue
                
            raw_items.append(
                InvoiceItem(
                    name=name,
                    quantity=qty,
                    unit_price=unit_price,
                    total_price=brutto
                )
            )
            
    return raw_items


def _parse_stoklasa_items(text: str) -> list:
    """
    Специализированный парсер для фактур Stoklasa с двухпроходным восстановлением поврежденных OCR-строк.
    """
    lines = text.split("\n")
    cleaned_lines = [l.strip() for l in lines if l.strip()]

    candidates = []
    
    code_at_start_pattern = re.compile(r"^\s*(\d{4,12})\b")
    ean_pattern = re.compile(r"\b(\d{13})\b")
    
    for idx, line in enumerate(cleaned_lines):
        code_match = code_at_start_pattern.match(line)
        if not code_match:
            continue
        
        ean_match = ean_pattern.search(line)
        if not ean_match:
            continue
            
        code = code_match.group(1)
        ean = ean_match.group(1)
        
        # Берем подстроку после EAN
        ean_pos = line.find(ean)
        after_ean = line[ean_pos + len(ean):]
        
        # Извлекаем все числа из подстроки после EAN
        numbers = _extract_numbers(after_ean)
        
        # Если чисел слишком мало (меньше 3), то это либо подарок без цены, либо неверная строка. Пропускаем.
        if len(numbers) < 3:
            continue
            
        # Собираем строки с описанием товара
        name_parts = []
        
        # Захватываем текст на той же строке между кодом и EAN (если есть)
        code_pos = line.find(code)
        if code_pos != -1 and ean_pos != -1 and code_pos < ean_pos:
            same_line_text = line[code_pos + len(code):ean_pos].strip()
            if same_line_text:
                name_parts.append(same_line_text)
                
        name_idx = idx + 1
        tariff_pattern = re.compile(r"\b\d{10}\b")
        
        while name_idx < len(cleaned_lines):
            next_line = cleaned_lines[name_idx]
            
            # Останавливаемся, если следующая строка - начало нового товара
            if code_at_start_pattern.match(next_line) and ean_pattern.search(next_line):
                break
                
            # Останавливаемся, если дошли до итоговой секции
            if any(ek in next_line.lower() for ek in ["razem", "suma", "do zapłaty", "do zaplaty"]):
                break
                
            # Останавливаемся, если строка содержит таможенный тариф
            if tariff_pattern.search(next_line):
                break
                
            cleaned_part = re.sub(r"[|\u2502\u2503\t]", " ", next_line)
            cleaned_part = re.sub(r"\s{2,}", " ", cleaned_part).strip()
            if cleaned_part:
                name_parts.append(cleaned_part)
                
            name_idx += 1
            
        description = " ".join(name_parts)
        full_name = f"{code} {description}" if description else code
        full_name = re.sub(r"\s{2,}", " ", full_name).strip()
        
        candidates.append({
            "code": code,
            "ean": ean,
            "full_name": full_name,
            "numbers": numbers,
            "raw_line": line
        })

    known_prices = {}    # code -> (net_unit_price, vat_percent)
    known_prefixes = {}  # prefix -> (net_unit_price, vat_percent)

    # Проход 1: Парсим полные строки (>= 5 чисел после EAN) и строим базу цен/VAT
    for c in candidates:
        nums = c["numbers"]
        code = c["code"]
        
        quantity = None
        net_unit_price = None
        vat_percent = None
        net_total = None
        vat_amount = None
        gross_total = None
        
        if len(nums) >= 6:
            # Случай 6 чисел: стандартные колонки
            # [qty, net_unit_price, vat_percent, net_total, vat_amount, gross_total]
            quantity = nums[0]
            net_unit_price = nums[1]
            vat_percent = nums[2]
            net_total = nums[3]
            vat_amount = nums[4]
            gross_total = nums[5]
        elif len(nums) == 5:
            # Случай 5 чисел
            # Возможны варианты:
            # А) [net_unit_price, vat_percent, net_total, vat_amount, gross_total] (нет qty)
            # Б) [qty, net_unit_price, net_total, vat_amount, gross_total] (нет vat_percent)
            if nums[1] in [23.0, 8.0, 5.0]:
                net_unit_price = nums[0]
                vat_percent = nums[1]
                net_total = nums[2]
                vat_amount = nums[3]
                gross_total = nums[4]
                if net_unit_price > 0:
                    quantity = net_total / net_unit_price
                else:
                    quantity = 1.0
            else:
                quantity = nums[0]
                net_unit_price = nums[1]
                net_total = nums[2]
                vat_amount = nums[3]
                gross_total = nums[4]
                if net_total > 0:
                    vat_percent = (vat_amount / net_total) * 100.0
                else:
                    vat_percent = 23.0
                    
        if net_unit_price is not None and vat_percent is not None:
            # Сохраняем цену в базу для последующего использования в неполных строках
            known_prices[code] = (net_unit_price, vat_percent)
            for length in [4, 3]:
                if len(code) >= length:
                    prefix = code[:length]
                    if prefix not in known_prefixes:
                        known_prefixes[prefix] = (net_unit_price, vat_percent)
            
            unit_price = net_unit_price * (1 + vat_percent / 100.0)
            c["quantity"] = round(quantity, 2) if quantity is not None else 1.0
            c["unit_price"] = round(unit_price, 2)
            c["total_price"] = round(gross_total if gross_total is not None else (quantity * unit_price), 2)
            c["resolved"] = True
        else:
            c["resolved"] = False

    # Проход 2: Восстанавливаем неполные строки (3-4 числа после EAN)
    for c in candidates:
        if not c["resolved"]:
            nums = c["numbers"]
            code = c["code"]
            
            quantity = None
            net_unit_price = None
            vat_percent = None
            gross_total = None
            
            if len(nums) == 4:
                # [vat_percent, net_total, vat_amount, gross_total]
                vat_percent = nums[0]
                net_total = nums[1]
                gross_total = nums[3]
            elif len(nums) == 3:
                # [net_total, vat_amount, gross_total]
                net_total = nums[0]
                gross_total = nums[2]
                if net_total > 0:
                    vat_percent = ((gross_total - net_total) / net_total) * 100.0
                else:
                    vat_percent = 23.0
                    
            # Ищем цену товара в нашей базе (по коду или по префиксам)
            price_info = None
            if code in known_prices:
                price_info = known_prices[code]
            else:
                if len(code) >= 4 and code[:4] in known_prefixes:
                    price_info = known_prefixes[code[:4]]
                elif len(code) >= 3 and code[:3] in known_prefixes:
                    price_info = known_prefixes[code[:3]]
            
            if price_info:
                net_unit_price, resolved_vat = price_info
                if vat_percent is None:
                    vat_percent = resolved_vat
            else:
                # Фолбек: предполагаем, что это кусок ткани с нарезкой 0.5 метра
                quantity = 0.5
                if net_total is not None:
                    net_unit_price = net_total / 0.5
                else:
                    net_unit_price = 0.0
                vat_percent = 23.0
                
            if quantity is None and net_unit_price > 0:
                quantity = net_total / net_unit_price
                
            if quantity is None:
                quantity = 1.0
                
            vat_percent = vat_percent if vat_percent is not None else 23.0
            unit_price = net_unit_price * (1 + vat_percent / 100.0)
            
            c["quantity"] = round(quantity, 2)
            c["unit_price"] = round(unit_price, 2)
            c["total_price"] = round(gross_total if gross_total is not None else (quantity * unit_price), 2)
            c["resolved"] = True

    # Собираем результирующий список
    items = []
    for c in candidates:
        if c.get("resolved"):
            items.append(
                InvoiceItem(
                    name=c["full_name"],
                    unit_price=c["unit_price"],
                    quantity=c["quantity"],
                    total_price=c["total_price"]
                )
            )
            
    return items


