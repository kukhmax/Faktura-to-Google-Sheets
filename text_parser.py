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

    # Извлекаем номер фактуры
    invoice.invoice_number = _extract_invoice_number(text)

    # Извлекаем товары
    invoice.items = _extract_items(text)

    logger.info(
        f"Парсинг завершён: дата='{invoice.date}', "
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


def _extract_invoice_number(text: str) -> str:
    """
    Извлекает номер фактуры.

    Поддерживаемые форматы:
    - Faktura VAT nr FV/2024/001
    - Faktura nr FV 1/2015
    - Faktura nr: 123/2024
    - FA-001/2024
    - FV 2024/001
    - Nr faktury: 123
    """
    # Нормализуем текст: объединяем строки, чтобы поймать многострочные номера
    # "Faktura VAT\nnr FS-192/26/SUR" → "Faktura VAT nr FS-192/26/SUR"
    normalized = re.sub(r'\s*\n\s*', ' ', text)
    normalized = re.sub(r'\s{2,}', ' ', normalized)

    patterns = [
        # "Faktura (VAT) nr FV 1/2015" или "Faktura nr: 123/2024"
        # Захватываем всё после "nr" до конца строки или двойного пробела
        r"[Ff]aktura\s+(?:VAT\s+)?(?:[Nn]r\.?\s*:?\s*)([\w/\-]+(?:[\s]+[\w/\-]+)*)",
        r"[Nn]r\.?\s+faktury[:\s]+([\w/\-]+(?:[\s]+[\w/\-]+)*)",
        # "FV 1/2015" или "FV/2024/001"
        r"((?:FV|FA)[/\-\s]*\d[\w/\-\s]*\d)",
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
            number = re.sub(r"\s+(Data|Termin|Metoda|Nabywca|Sprzedawca|Uwagi).*$", "", number, flags=re.IGNORECASE)
            # Убираем лишние пробелы
            number = " ".join(number.split())
            if number:
                return number

    return ""


def _extract_items(text: str) -> list:
    """
    Извлекает товары из текста фактуры.

    Стратегия:
    1. Ищем таблицу товаров по заголовкам (Nazwa, Ilość, Cena, itd.)
    2. Парсим строки таблицы
    3. Если таблица не найдена — пробуем более гибкий подход
    """
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
    # Порядок: сначала числа с десятичной частью (до 4 десятичных знаков), потом целые
    pattern = r"(\d[\d\s]*[,\.]\d{1,4}|\d+)"
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
