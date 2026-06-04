import sys
import codecs
from text_parser import parse_invoice_text

if sys.platform.startswith("win"):
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.detach())

with open("ocr_raw_invoice_new.txt", "r", encoding="utf-8") as f:
    text = f.read()

invoice = parse_invoice_text(text)
print(f"Seller: {invoice.seller}")
print(f"Invoice Number: {invoice.invoice_number}")
print(f"Date: {invoice.date}")
print(f"Total items: {len(invoice.items)}")
for i, item in enumerate(invoice.items, 1):
    print(f"{i:2d}. Name: {item.name}")
    print(f"    Qty: {item.quantity}, Unit Price: {item.unit_price}, Total: {item.total_price}")
