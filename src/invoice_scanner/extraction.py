"""Deterministic, evidence-preserving extraction from OCR text."""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from invoice_scanner.audit import audit_invoice
from invoice_scanner.ocr import OCRLine
from invoice_scanner.schema import FieldEvidence, InvoiceData, LineItem

SPACE_RE = re.compile(r"[\t\u00a0 ]+")
INVOICE_NUMBER_RE = re.compile(
    r"^\s*(?:invoice|inv)\b(?:"
    r"\s+(?:number|no\.?)\s*(?:#\s*)?[:\-]?\s*|"
    r"\s*#\s*:?\s*|\s*:\s*|\s*-\s*|\s+)"
    r"(?!date\b|due\b)(?P<value>[A-Z0-9][A-Z0-9._/\-]*)\s*$",
    re.IGNORECASE,
)
VENDOR_RE = re.compile(
    r"^\s*(?:vendor|supplier|merchant|from)(?:\s+name)?\s*[:\-]\s*(?P<value>.+?)\s*$",
    re.IGNORECASE,
)
INVOICE_DATE_RE = re.compile(
    r"^\s*(?:invoice\s+)?date\s*[:\-]\s*(?P<value>.+?)\s*$",
    re.IGNORECASE,
)
DUE_DATE_RE = re.compile(
    r"^\s*(?:payment\s+)?due\s+date\s*[:\-]\s*(?P<value>.+?)\s*$",
    re.IGNORECASE,
)
MONEY_TOKEN_RE = re.compile(
    r"(?<![\w.])(?:\(\s*)?-?\s*(?:[$€£¥]\s*)?"
    r"(?:\d{1,3}(?:[,.\s]\d{3})+|\d+)(?:[.,]\d{1,2})?\s*\)?(?!\w)"
)
LINE_ITEM_RE = re.compile(
    r"^(?P<description>.+?)\s+"
    r"(?P<quantity>\d+(?:[.,]\d+)?)\s+"
    r"(?P<unit_price>(?:[$€£¥])?\s*\d[\d,.]*)\s+"
    r"(?P<total>\(?-?(?:[$€£¥])?\s*\d[\d,.]*\)?)"
    r"(?:\s+[A-Z]{3})?\s*$",
    re.IGNORECASE,
)
NUMERIC_ITEM_RE = re.compile(
    r"^(?P<quantity>\d+(?:[.,]\d+)?)\s+"
    r"(?P<unit_price>(?:[$€£¥])?\s*\d[\d,.]*)\s+"
    r"(?P<total>\(?-?(?:[$€£¥])?\s*\d[\d,.]*\)?)"
    r"(?:\s+[A-Z]{3})?\s*$",
    re.IGNORECASE,
)
CURRENCY_CODE_RE = re.compile(r"\b(USD|EUR|GBP|JPY|SAR|AED|CAD|AUD|CHF)\b", re.IGNORECASE)
CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY"}
SUMMARY_LABEL_RE = re.compile(
    r"^\s*(?:sub\s*total|subtotal|net\s+amount|tax|vat|gst|discount|grand\s+total|"
    r"total|amount\s+due|balance\s+due)\b",
    re.IGNORECASE,
)
HEADER_RE = re.compile(
    r"\b(?:description|item|service)\b.*\b(?:qty|quantity)\b.*\b(?:amount|total|price)\b",
    re.IGNORECASE,
)


def _normalize_line(value: str) -> str:
    return SPACE_RE.sub(" ", value.strip())


def _source_lines(text: str, ocr_lines: Sequence[OCRLine]) -> list[OCRLine]:
    if ocr_lines:
        return [
            OCRLine(
                text=_normalize_line(line.text),
                confidence=line.confidence,
                bounding_box=line.bounding_box,
            )
            for line in ocr_lines
            if _normalize_line(line.text)
        ]
    return [
        OCRLine(text=_normalize_line(line), confidence=None, bounding_box=None)
        for line in text.splitlines()
        if _normalize_line(line)
    ]


def _evidence(line: OCRLine, method: str) -> FieldEvidence:
    return FieldEvidence(
        source_text=line.text,
        method=method,
        confidence=line.confidence,
        bounding_box=line.bounding_box,
    )


def _parse_decimal(value: str) -> Decimal | None:
    cleaned = value.strip()
    negative = cleaned.startswith("-") or (cleaned.startswith("(") and cleaned.endswith(")"))
    cleaned = re.sub(r"[^\d,.]", "", cleaned)
    if not cleaned:
        return None

    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        groups = cleaned.split(",")
        if len(groups) == 2 and len(groups[-1]) in (1, 2):
            cleaned = ".".join(groups)
        else:
            cleaned = "".join(groups)
    elif cleaned.count(".") > 1:
        groups = cleaned.split(".")
        if len(groups[-1]) in (1, 2):
            cleaned = "".join(groups[:-1]) + "." + groups[-1]
        else:
            cleaned = "".join(groups)

    try:
        number = Decimal(cleaned)
    except InvalidOperation:
        return None
    return -number if negative else number


def _last_amount(value: str) -> Decimal | None:
    matches = [
        match
        for match in MONEY_TOKEN_RE.finditer(value)
        if not value[match.end() :].lstrip().startswith("%")
    ]
    if not matches:
        return None
    return _parse_decimal(matches[-1].group(0))


def _parse_date(value: str) -> tuple[date | None, bool]:
    cleaned = re.sub(r"(?<=\d)(?:st|nd|rd|th)\b", "", value.strip(), flags=re.IGNORECASE)
    cleaned = cleaned.replace(",", "")
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%b %d %Y", "%B %d %Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(cleaned, fmt).date(), False
        except ValueError:
            continue

    match = re.fullmatch(r"(\d{1,2})[\-/](\d{1,2})[\-/](\d{4})", cleaned)
    if not match:
        return None, False
    first, second, year = (int(part) for part in match.groups())
    ambiguous = first <= 12 and second <= 12 and first != second
    if first > 12:
        day, month = first, second
    else:
        month, day = first, second
    try:
        return date(year, month, day), ambiguous
    except ValueError:
        return None, ambiguous


def _match_text_field(
    lines: Sequence[OCRLine], pattern: re.Pattern[str]
) -> tuple[str | None, OCRLine | None]:
    for line in lines:
        if match := pattern.match(line.text):
            return match.group("value").strip(), line
    return None, None


def _looks_like_vendor(line: str) -> bool:
    lowered = line.lower()
    rejected_prefixes = (
        "invoice",
        "date",
        "due",
        "bill to",
        "ship to",
        "description",
        "item",
        "subtotal",
        "tax",
        "total",
    )
    return (
        2 <= len(line) <= 100
        and any(character.isalpha() for character in line)
        and not lowered.startswith(rejected_prefixes)
    )


def _money_field(
    lines: Sequence[OCRLine], labels: Sequence[re.Pattern[str]]
) -> tuple[Decimal | None, OCRLine | None]:
    for label in labels:
        candidates: list[tuple[Decimal, OCRLine]] = []
        for line in lines:
            if label.match(line.text) and (amount := _last_amount(line.text)) is not None:
                candidates.append((amount, line))
        if candidates:
            return candidates[-1]
    return None, None


def _extract_line_items(lines: Sequence[OCRLine]) -> tuple[list[LineItem], OCRLine | None]:
    header_index = next(
        (index for index, line in enumerate(lines) if HEADER_RE.search(line.text)),
        None,
    )
    if header_index is None:
        legacy_items: list[LineItem] = []
        first_line: OCRLine | None = None
        for line in lines:
            if match := re.match(r"^item\s+\d+\s+(.+)$", line.text, re.IGNORECASE):
                legacy_items.append(LineItem(description=match.group(1)))
                first_line = first_line or line
        return legacy_items, first_line

    items: list[LineItem] = []
    first_line = None
    pending_description: str | None = None
    for line in lines[header_index + 1 :]:
        if SUMMARY_LABEL_RE.match(line.text):
            break
        if match := LINE_ITEM_RE.match(line.text):
            description = match.group("description").strip()
            if pending_description:
                description = f"{pending_description} {description}"
                pending_description = None
            quantity = _parse_decimal(match.group("quantity"))
            unit_price = _parse_decimal(match.group("unit_price"))
            total = _parse_decimal(match.group("total"))
            items.append(
                LineItem(
                    description=description,
                    quantity=quantity,
                    unit_price=unit_price,
                    total=total,
                )
            )
            first_line = first_line or line
            continue
        if pending_description and (match := NUMERIC_ITEM_RE.match(line.text)):
            items.append(
                LineItem(
                    description=pending_description,
                    quantity=_parse_decimal(match.group("quantity")),
                    unit_price=_parse_decimal(match.group("unit_price")),
                    total=_parse_decimal(match.group("total")),
                )
            )
            first_line = first_line or line
            pending_description = None
            continue
        if any(character.isalpha() for character in line.text):
            pending_description = (
                line.text if pending_description is None else f"{pending_description} {line.text}"
            )
    return items, first_line


def extract_fields(text: str, *, ocr_lines: Sequence[OCRLine] = ()) -> InvoiceData:
    """Extract normalized fields and attach evidence plus an audit report."""

    normalized_text = "\n".join(
        _normalize_line(line) for line in text.splitlines() if _normalize_line(line)
    )
    lines = _source_lines(normalized_text, ocr_lines)
    invoice = InvoiceData(raw_text=normalized_text)
    evidence: dict[str, FieldEvidence] = {}
    warnings: list[str] = []

    vendor, vendor_line = _match_text_field(lines, VENDOR_RE)
    vendor_method = "label"
    if vendor is None:
        vendor_line = next((line for line in lines if _looks_like_vendor(line.text)), None)
        vendor = vendor_line.text if vendor_line else None
        vendor_method = "layout"
    if vendor and vendor_line:
        invoice.vendor_name = vendor
        evidence["vendor_name"] = _evidence(vendor_line, vendor_method)

    invoice_number, invoice_line = _match_text_field(lines, INVOICE_NUMBER_RE)
    if invoice_number and invoice_line:
        invoice.invoice_number = invoice_number
        evidence["invoice_number"] = _evidence(invoice_line, "label")

    for field_name, pattern in (("invoice_date", INVOICE_DATE_RE), ("due_date", DUE_DATE_RE)):
        raw_date, source_line = _match_text_field(lines, pattern)
        if raw_date and source_line:
            parsed_date, ambiguous = _parse_date(raw_date)
            setattr(invoice, field_name, parsed_date)
            if parsed_date:
                evidence[field_name] = _evidence(source_line, "label")
            if ambiguous:
                warnings.append(
                    f"{field_name} used ambiguous numeric date {raw_date!r}; "
                    "month-first interpretation applied."
                )

    money_patterns = {
        "subtotal": (re.compile(r"^\s*(?:sub\s*total|subtotal|net\s+amount)\b", re.IGNORECASE),),
        "tax_amount": (
            re.compile(
                r"^\s*(?:tax|vat|gst)\b"
                r"(?!\s*(?:id|number|no\.?|registration|rate)\b)",
                re.IGNORECASE,
            ),
        ),
        "discount_amount": (re.compile(r"^\s*(?:discount|less)\b", re.IGNORECASE),),
        "total_amount": (
            re.compile(
                r"^\s*(?:grand\s+total|amount\s+due|balance\s+due|total\s+amount)\b",
                re.IGNORECASE,
            ),
            re.compile(
                r"^\s*total\b(?!\s+(?:tax|vat|discount|before)\b)",
                re.IGNORECASE,
            ),
        ),
    }
    total_line: OCRLine | None = None
    for field_name, patterns in money_patterns.items():
        value, source_line = _money_field(lines, patterns)
        if field_name == "discount_amount" and value is not None:
            value = abs(value)
        setattr(invoice, field_name, value)
        if value is not None and source_line:
            evidence[field_name] = _evidence(source_line, "label")
            if field_name == "total_amount":
                total_line = source_line

    currency_sources = ([total_line] if total_line else []) + list(lines)
    for line in currency_sources:
        if line is None:
            continue
        if match := CURRENCY_CODE_RE.search(line.text):
            invoice.currency = match.group(1).upper()
            evidence["currency"] = _evidence(line, "currency_code")
            break
        if symbol := next((symbol for symbol in CURRENCY_SYMBOLS if symbol in line.text), None):
            invoice.currency = CURRENCY_SYMBOLS[symbol]
            evidence["currency"] = _evidence(line, "currency_symbol")
            if symbol == "$":
                warnings.append("Currency inferred as USD from an ambiguous dollar symbol.")
            break

    invoice.line_items, item_line = _extract_line_items(lines)
    if invoice.line_items and item_line:
        evidence["line_items"] = _evidence(item_line, "table_row")

    invoice.quality = audit_invoice(invoice, evidence=evidence, warnings=warnings)
    return invoice
