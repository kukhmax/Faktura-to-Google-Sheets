import sys
import codecs
from text_parser import _parse_table_items, _parse_items_flexible, _find_table_start

if sys.platform.startswith("win"):
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.detach())

with open("ocr_raw_invoice.txt", "r", encoding="utf-8") as f:
    text = f.read()

lines = text.split("\n")
lines = [line.strip() for line in lines if line.strip()]

# Test _parse_table_items
table_start = _find_table_start(lines)
print(f"Table start index: {table_start}")
if table_start is not None:
    items_table = _parse_table_items(lines, table_start)
    print(f"\n--- _parse_table_items ({len(items_table)} items) ---")
    for i, item in enumerate(items_table, 1):
        print(f"{i:2d}. Name: {item.name}")
        print(f"    Qty: {item.quantity}, Unit Price: {item.unit_price}, Total: {item.total_price}")

# Test _parse_items_flexible
items_flex = _parse_items_flexible(lines)
print(f"\n--- _parse_items_flexible ({len(items_flex)} items) ---")
for i, item in enumerate(items_flex, 1):
    print(f"{i:2d}. Name: {item.name}")
    print(f"    Qty: {item.quantity}, Unit Price: {item.unit_price}, Total: {item.total_price}")
