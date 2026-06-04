import sys
import codecs
from text_parser import parse_invoice_text, _extract_numbers, _extract_invoice_number

# Ensure UTF-8 output on Windows
if sys.platform.startswith("win"):
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.detach())

def run_fixes_test():
    print("=== Testing Parser Bug Fixes ===")

    # Test Case 1: Multi-line invoice number
    text_invoice_num = "Sprzedawca: XYZ\nFaktura VAT\nnr FS-192/26/SUR\nData: 2026-06-04"
    inv_num = _extract_invoice_number(text_invoice_num)
    print(f"Extracted Invoice Number: '{inv_num}' (Expected: 'FS-192/26/SUR')")
    assert inv_num == "FS-192/26/SUR", f"Failed: got '{inv_num}'"

    # Test Case 2: Extracting decimal numbers (0,0100)
    numbers = _extract_numbers("0,0100 tsz. 1 350,00 13,50")
    print(f"Extracted numbers: {numbers} (Expected to contain 0.01, 1350.0, 13.5)")
    assert 0.01 in numbers, "Failed to extract 0.01 from 0,0100"
    assert 1350.0 in numbers, "Failed to extract 1350.0"
    assert 13.5 in numbers, "Failed to extract 13.5"

    # Test Case 3: Complete parser test with multi-line item and 0,0100 quantity
    ocr_sample = """
FAKTURA VAT nr FS-192/26/SUR
Sprzedawca: Firma A
Nabywca: Firma B
Data wystawienia: 04.06.2026

Lp. | Nazwa towaru/usługi | PKWiU | Ilość | J.m. | Cena netto | Wartość netto | VAT %
1 | HFT-3-PERLA-809-885 | 62129000 | 0,0100 | tsz. | 1 350,00 | 13,50 | 23%
    Haftki 3-rzędowe PERLA 99L GAIA (809) (885)
2 | Zwykły Towar | | 10 | szt. | 5,00 | 50,00 | 23%
"""

    invoice = parse_invoice_text(ocr_sample)
    print(f"\nInvoice number parsed: '{invoice.invoice_number}'")
    print(f"Items parsed ({len(invoice.items)}):")
    for i, item in enumerate(invoice.items, 1):
        print(f"  {i}. '{item.name}': {item.quantity} x {item.unit_price} = {item.total_price}")

    assert invoice.invoice_number == "FS-192/26/SUR"
    assert len(invoice.items) == 2, f"Expected 2 items, got {len(invoice.items)}"
    
    # Verify first item name merging and quantity
    first_item = invoice.items[0]
    expected_name = "HFT-3-PERLA-809-885 Haftki 3-rzędowe PERLA 99L GAIA"
    assert expected_name in first_item.name, f"Expected name to contain '{expected_name}', got '{first_item.name}'"
    assert first_item.quantity == 0.01, f"Expected quantity 0.01, got {first_item.quantity}"
    assert first_item.unit_price == 1350.0, f"Expected price 1350.0, got {first_item.unit_price}"
    assert first_item.total_price == 13.5, f"Expected total 13.5, got {first_item.total_price}"

    # Verify second item
    second_item = invoice.items[1]
    assert "Zwykły Towar" in second_item.name
    assert second_item.quantity == 10.0
    assert second_item.unit_price == 5.0
    assert second_item.total_price == 50.0

    # Test Case 4: Stoklasa parser test
    stoklasa_ocr_sample = """
Faktura VAT nr FV/2026/06/999
Dostawca: Stoklasa s.r.o.
Nabywca: Firma B
Data wystawienia: 04.06.2026

Kod taryfy celnej Kraj pochodzenia
020808  8591149319075       1,00 pude      8,03       23         8,03       1,85         9,88 PLN
Igły maszynowe Super stretch 75;90 Organ 3 (75;90) nikiel 1 boks
        8452300000                  CZ
"""
    invoice_stoklasa = parse_invoice_text(stoklasa_ocr_sample)
    print(f"\nStoklasa Invoice parsed: seller='{invoice_stoklasa.seller}' num='{invoice_stoklasa.invoice_number}'")
    print(f"Items parsed ({len(invoice_stoklasa.items)}):")
    for i, item in enumerate(invoice_stoklasa.items, 1):
        print(f"  {i}. '{item.name}': {item.quantity} x {item.unit_price} = {item.total_price}")

    assert invoice_stoklasa.seller == "Stoklasa"
    assert invoice_stoklasa.invoice_number == "FV/2026/06/999"
    assert len(invoice_stoklasa.items) == 1
    stoklasa_item = invoice_stoklasa.items[0]
    assert stoklasa_item.name == "020808 Igły maszynowe Super stretch 75;90 Organ 3 (75;90) nikiel 1 boks"
    assert stoklasa_item.quantity == 1.0
    assert stoklasa_item.unit_price == 9.88
    assert stoklasa_item.total_price == 9.88

    # Test Case 5: Real Stoklasa invoice OCR parser test
    import os
    if os.path.exists("stoklasa_real_ocr.txt"):
        with open("stoklasa_real_ocr.txt", "r", encoding="utf-8") as f:
            real_ocr = f.read()
        invoice_real = parse_invoice_text(real_ocr)
        print(f"\nReal Stoklasa Invoice parsed: seller='{invoice_real.seller}' num='{invoice_real.invoice_number}' items={len(invoice_real.items)}")
        assert invoice_real.seller == "Stoklasa"
        assert invoice_real.invoice_number == "2532005414"
        assert invoice_real.date == "20.08.2025"
        assert len(invoice_real.items) == 22, f"Expected 22 items, got {len(invoice_real.items)}"
        # Verify first item
        first_item = invoice_real.items[0]
        assert first_item.name == "020808 Igły maszynowe Super stretch 75;90 Organ 3 (75;90) nikiel 1 boks"
        assert first_item.quantity == 1.0
        assert first_item.unit_price == 9.88
        assert first_item.total_price == 9.88

    print("\n✅ All bug fixes successfully verified!")

if __name__ == "__main__":
    run_fixes_test()
