"""
Тестовый скрипт для верификации работы парсера фактур без отправки запросов в OCR.space.
Использует образец OCR-текста реальной польской фактуры.
"""

import sys
import codecs
from text_parser import parse_invoice_text, calculate_new_prices

# Принудительно настраиваем UTF-8 для вывода в консоль Windows
if sys.platform.startswith("win"):
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.detach())

# Пример OCR-текста польской фактуры (полученного с включенным параметром isTable=True)
SAMPLE_OCR_TEXT = """
FAKTURA VAT nr FV/2026/05/104
Sprzedawca: Hurtownia Budowlana "Bud-Max" Sp. z o.o.
NIP: 1234567890
Nabywca: Jan Kowalski Usługi Remontowe
Data sprzedaży: 28.05.2026
Data wystawienia: 28.05.2026
Sposób płatności: Przelew

Lp. | Nazwa towaru/usługi | Ilość | J.m. | Cena netto | Wartość netto | VAT %
1 | Klej do glazury Atlas 25kg | 10 | szt. | 45,50 | 455,00 | 23%
2 | Profil aluminiowy UD27 3m | 30 | szt. | 12,00 | 360,00 | 23%
3 | Śruby montażowe 100 szt | 2.5 | opak | 24,00 | 60,00 | 23%
4 | Płyta gipsowo-kartonowa H2 | 15 | szt. | 32.20 | 483.00 | 23%

Razem do zapłaty: 1671,20 PLN
Dziękujemy za zakupy!
"""


def run_test():
    print("=== Тестирование парсера польских фактур ===")
    print("Исходный текст отправлен на парсинг...")

    # 1. Тест извлечения общих данных
    invoice = parse_invoice_text(SAMPLE_OCR_TEXT)

    print(f"\nИзвлеченные метаданные:")
    print(f"• Номер фактуры: '{invoice.invoice_number}' (Ожидается: 'FV/2026/05/104')")
    print(f"• Дата покупки: '{invoice.date}' (Ожидается: '28.05.2026')")

    assert invoice.invoice_number == "FV/2026/05/104", "Неверный номер фактуры!"
    assert invoice.date == "28.05.2026", "Неверная дата покупки!"

    # 2. Тест извлечения товаров
    print(f"\nИзвлеченные товары ({len(invoice.items)} шт.):")
    for i, item in enumerate(invoice.items, 1):
        print(f"  {i}. Название: '{item.name}'")
        print(f"     Кол-во: {item.quantity} | Цена закуп.: {item.unit_price} PLN | Сумма: {item.total_price} PLN")

    assert len(invoice.items) == 4, f"Должно быть 4 товара, найдено {len(invoice.items)}"

    # Проверка конкретного товара
    first_item = invoice.items[0]
    assert "Klej do glazury Atlas" in first_item.name, "Неверное название 1-го товара!"
    assert first_item.quantity == 10.0, "Неверное количество 1-го товара!"
    assert first_item.unit_price == 45.50, "Неверная цена 1-го товара!"
    assert first_item.total_price == 455.00, "Неверная сумма 1-го товара!"

    third_item = invoice.items[2]
    assert "Śruby montażowe" in third_item.name, "Неверное название 3-го товара!"
    assert third_item.quantity == 2.5, "Неверное количество 3-го товара!"
    assert third_item.unit_price == 24.0, "Неверная цена 3-го товара!"
    assert third_item.total_price == 60.0, "Неверная сумма 3-го товара!"

    print("\n✅ Все тесты извлечения структуры данных пройдены успешно!")

    # 3. Тест расчета новых цен
    print("\n=== Тестирование расчёта розничных цен ===")
    tax_percent = 5.0
    margin_percent = 40.0
    print(f"Налог (TAX): {tax_percent}%, Маржа (Margin): {margin_percent}%")

    calculated = calculate_new_prices(invoice.items, tax_percent, margin_percent)

    for i, item in enumerate(calculated, 1):
        print(f"  {i}. {item['name']}:")
        print(f"     Закупка: {item['unit_price']} PLN")
        # Формула: cost + (cost * tax%) + (cost * margin%)
        # Для 45.50: 45.50 + (45.50 * 0.05 = 2.275) + (45.50 * 0.40 = 18.2) = 45.50 + 2.275 + 18.2 = 65.975 -> округленно 65.98
        print(f"     Розничная цена (шт): {item['new_unit_price']} PLN (Ожидается: {round(item['unit_price'] * 1.45, 2)} PLN)")
        print(f"     Всего розница ({item['quantity']} шт): {item['new_total_price']} PLN")

    # Проверяем математику на первом товаре
    # 45.50 + 45.50 * 0.05 + 45.50 * 0.40 = 65.975 -> округленно 65.97 в Python из-за банковского округления
    first_calc = calculated[0]
    expected_unit = round(45.50 + 45.50 * 0.05 + 45.50 * 0.40, 2)  # 65.97
    expected_total = round((45.50 + 45.50 * 0.05 + 45.50 * 0.40) * 10, 2)       # 659.75
    assert first_calc["new_unit_price"] == expected_unit, f"Неверная розничная цена! Получено {first_calc['new_unit_price']}"
    assert first_calc["new_total_price"] == expected_total, f"Неверная розничная общая сумма! Получено {first_calc['new_total_price']}"

    print("\n✅ Расчеты цен по формуле `Закупка + Налог + Маржа` полностью верны!")
    print("\n🎉 Все тесты парсера успешно пройдены!")


if __name__ == "__main__":
    run_test()
