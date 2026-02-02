from __future__ import annotations

import re
from datetime import datetime

from invoice_scanner.schema import InvoiceData, LineItem

TOTAL_RE = re.compile(r"total\s*[:$]?\s*(\d+[\d,]*\.?\d*)", re.IGNORECASE)
DATE_RE = re.compile(r"date\s*[:]?\s*([\d\-/]+)", re.IGNORECASE)
INVOICE_RE = re.compile(r"invoice\s*#?\s*([A-Z0-9\-]+)", re.IGNORECASE)
VENDOR_RE = re.compile(r"vendor\s*[:]?\s*(.+)", re.IGNORECASE)
CURRENCY_RE = re.compile(r"\b(USD|EUR|GBP|JPY|SAR|AED)\b")


def _parse_date(value: str):
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def extract_fields(text: str) -> InvoiceData:
    invoice = InvoiceData(raw_text=text)

    if match := VENDOR_RE.search(text):
        invoice.vendor_name = match.group(1).strip()

    if match := INVOICE_RE.search(text):
        invoice.invoice_number = match.group(1).strip()

    if match := DATE_RE.search(text):
        invoice.invoice_date = _parse_date(match.group(1).strip())

    if match := TOTAL_RE.search(text):
        invoice.total_amount = float(match.group(1).replace(",", ""))

    if match := CURRENCY_RE.search(text):
        invoice.currency = match.group(1)

    invoice.line_items = _extract_line_items(text)
    return invoice


def _extract_line_items(text: str) -> list[LineItem]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    items = []
    for line in lines:
        if line.lower().startswith("item"):
            parts = re.split(r"\s{2,}", line)
            if len(parts) >= 2:
                items.append(LineItem(description=parts[1]))
    return items
