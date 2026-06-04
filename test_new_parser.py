import sys
import codecs
import re

if sys.platform.startswith("win"):
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.detach())

def parse_ocr_text_robust(text):
    lines = text.split("\n")
    cleaned_lines = [l.strip() for l in lines if l.strip()]

    # Find table start
    start_idx = 0
    for idx, line in enumerate(cleaned_lines):
        line_lower = line.lower()
        if "nazwa towaru" in line_lower or ("kod" in line_lower and "cena" in line_lower):
            start_idx = idx + 1
            break

    print(f"Table starts at line index {start_idx}: '{cleaned_lines[start_idx]}'")

    end_keywords = ["razem", "suma", "do zapłaty", "do zaplaty", "łącznie", "lacznie", "ogółem", "ogolem"]

    items = []
    current_item = None

    # Code pattern: starts with letters, contains hyphens
    # Must start with 2-10 letters, not digits! E.g. HFT-, DRU-, SEL-
    code_pattern = re.compile(r"\b[A-ZÜÄÖĆŁŚŹŻ]{2,10}-[\w\-]+\b", re.IGNORECASE)
    unit_pattern = re.compile(r"(\d[\d ]*[,\.]\d{1,4}|\d+)\s*(tsz|mb|szt|kpl|kg|op|opak|t52)", re.IGNORECASE)

    for idx in range(start_idx, len(cleaned_lines)):
        line = cleaned_lines[idx]
        line_lower = line.lower()
        if any(ek in line_lower for ek in end_keywords):
            print(f"Reached end of table at line {idx}: '{line}'")
            break

        parts = [p.strip() for p in line.split("\t") if p.strip()]
        if not parts:
            continue

        # Check if line contains a product code
        code_match = None
        code_part_idx = -1
        for p_idx, part in enumerate(parts):
            match = code_pattern.search(part)
            if match:
                code_str = match.group(0)
                # Ignore if code is inside parentheses
                if f"({code_str}" in part or f"{code_str})" in part:
                    continue
                if "ZS-" not in part and "FS-" not in part:
                    code_match = code_str
                    code_part_idx = p_idx
                    break

        if code_match:
            # Start of a new item!
            name = parts[code_part_idx]
            # Strip sequence numbers that are merged with the code (e.g., '9 GUM-6-PERLA-480-883' -> 'GUM-6-PERLA-480-883')
            name = re.sub(r"^\s*\d+\s+", "", name)
            
            # Get data columns after code
            data_parts = parts[code_part_idx + 1:]
            
            # Extract numbers from data columns
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

            # Check if there is an explicit quantity matching unit pattern
            qty = None
            qty_match = unit_pattern.search(line)
            if qty_match:
                qty = float(qty_match.group(1).replace(" ", "").replace(",", "."))

            q, p, t = determine_price_quantity_robust(numbers, qty)

            current_item = {
                "name": name,
                "quantity": q,
                "unit_price": p,
                "total_price": t,
                "numbers": numbers,
                "qty_override": qty
            }
            items.append(current_item)
            
        elif current_item:
            # Continuation line (description or split numbers)
            desc_part = ""
            for p in parts:
                if not re.match(r"^\d[\d ]*[,\.]\d{1,4}$|^\d+$", p) and "%" not in p:
                    desc_part = p
                    break

            if desc_part:
                cleaned_desc = clean_product_name(desc_part)
                if cleaned_desc:
                    current_item["name"] = f"{current_item['name']} {cleaned_desc}"

            # Extract any numbers from other columns
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
                q, p, t = determine_price_quantity_robust(current_item["numbers"], current_item["qty_override"])
                current_item["quantity"] = q
                current_item["unit_price"] = p
                current_item["total_price"] = t

    return items

def clean_product_name(text):
    cleaned = re.sub(r"^\s*\d+\s*[.|\)]?\s*", "", text)
    cleaned = re.sub(r"\b\d{1,2}\s*%\s*", "", cleaned)
    cleaned = re.sub(r"\bzw\.?\b", "", cleaned, flags=re.IGNORECASE)
    units = ["szt", "szt.", "tsz.", "tsz", "sztuk", "kpl", "kpl.", "komplet", "kg", "mb", "op", "opak", "t52"]
    for unit in units:
        cleaned = re.sub(rf"\b{re.escape(unit)}\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\d[\d ]*[,\.]\d{1,4}", "", cleaned)
    cleaned = re.sub(r"(?<![\w\-])\d+(?![\w\-])", "", cleaned)
    cleaned = re.sub(r"\(\s*\)", "", cleaned)
    cleaned = re.sub(r"\[\s*\]", "", cleaned)
    cleaned = re.sub(r"[|│┃]", " ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip(" .\t-")

def determine_price_quantity_robust(numbers, known_qty=None):
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

    # If quantity is not known
    if len(numbers) == 1:
        return 1.0, numbers[0], numbers[0]
    if len(numbers) == 2:
        n1, n2 = numbers[0], numbers[1]
        # If they are very close, quantity is likely 1.0
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

with open("ocr_raw_invoice_new.txt", "r", encoding="utf-8") as f:
    text = f.read()

items = parse_ocr_text_robust(text)
print("\n=== Parsed Items ===")
for idx, item in enumerate(items, 1):
    print(f"{idx:2d}. Qty: {item['quantity']:-8.4f} | Price: {item['unit_price']:-8.2f} | Total: {item['total_price']:-8.2f} | Name: '{item['name']}'")
