import sys
import codecs
from text_parser import _parse_table_code_and_tab_aware, InvoiceItem

if sys.platform.startswith("win"):
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.detach())

with open("ocr_raw_invoice_new.txt", "r", encoding="utf-8") as f:
    lines = f.readlines()
    
# completely strip out header up to the first item (line 22)
cropped_text = "".join(lines[22:])

import re

def fixed_parse(text):
    lines = text.split("\n")
    cleaned_lines = [l.strip() for l in lines if l.strip()]

    # Ищем начало таблицы товаров
    start_idx = 0
    for idx, line in enumerate(cleaned_lines):
        line_lower = line.lower()
        if "nazwa towaru" in line_lower or ("kod" in line_lower and "cena" in line_lower):
            start_idx = idx + 1
            break

    # if start_idx == 0 or start_idx >= len(cleaned_lines):
    #     return []
    if start_idx >= len(cleaned_lines):
        return []

    # call the original function, but we bypass the check by overriding it
    # actually I will just copy the rest of the function to be sure
    return _parse_table_code_and_tab_aware(text)

# But I need to actually modify text_parser to test it. I'll just monkeypatch it.
import text_parser
def _parse_table_code_and_tab_aware_fixed(text: str) -> list:
    # the entire original function with start_idx check removed
    lines = text.split("\n")
    cleaned_lines = [l.strip() for l in lines if l.strip()]

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
    code_pattern = re.compile(r"\b[A-ZÜÄÖĆŁŚŹŻ]{2,10}-[\w\-]+\b")
    unit_pattern = re.compile(r"(\d[\d ]*[,\.]\d{1,4}|\d+)\s*(tsz|mb|szt|kpl|kg|op|opak|t52)", re.IGNORECASE)

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

    # use the original internal logic by calling text_parser with a mock text? No, I need the full logic to test.
    # I'll just change the text_parser.py directly since it's just one line.
    pass

