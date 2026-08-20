from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from invoice_scanner.extraction import (
    _last_amount,
    _looks_like_vendor,
    _parse_date,
    _parse_decimal,
    _source_lines,
    extract_fields,
)
from invoice_scanner.ocr import OCRLine
from invoice_scanner.schema import BoundingBox, CheckStatus


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("$1,234.56", Decimal("1234.56")),
        ("EUR 1.234,56", Decimal("1234.56")),
        ("(EUR 1.234,56)", Decimal("-1234.56")),
        ("- 42.5", Decimal("-42.5")),
        ("1,234", Decimal("1234")),
        ("12,5", Decimal("12.5")),
        ("1.234.567", Decimal("1234567")),
        ("1.234.56", Decimal("1234.56")),
        ("not money", None),
        (".", None),
    ],
)
def test_parse_decimal_accepts_common_invoice_formats(raw: str, expected: Decimal | None) -> None:
    assert _parse_decimal(raw) == expected


def test_last_amount_uses_the_final_money_token() -> None:
    assert _last_amount("Tax 10% on 1,000.00 = $100.00") == Decimal("100.00")
    assert _last_amount("nothing to parse") is None


@pytest.mark.parametrize(
    ("raw", "expected", "ambiguous"),
    [
        ("2026-08-18", date(2026, 8, 18), False),
        ("2026/08/18", date(2026, 8, 18), False),
        ("Aug 18th, 2026", date(2026, 8, 18), False),
        ("18 August 2026", date(2026, 8, 18), False),
        ("18/08/2026", date(2026, 8, 18), False),
        ("02/03/2026", date(2026, 2, 3), True),
        ("2026.08.18", None, False),
        ("31/31/2026", None, False),
    ],
)
def test_parse_date_formats(raw: str, expected: date | None, ambiguous: bool) -> None:
    assert _parse_date(raw) == (expected, ambiguous)


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("Northstar Cloud Ltd", True),
        ("Vendor: Northstar", True),
        ("Invoice Number: 123", False),
        ("Total USD 100.00", False),
        ("X", False),
        ("12345", False),
        ("A" * 101, False),
    ],
)
def test_vendor_layout_heuristic_rejects_non_vendor_lines(line: str, expected: bool) -> None:
    assert _looks_like_vendor(line) is expected


def test_source_lines_normalizes_ocr_data_and_falls_back_to_text() -> None:
    box = BoundingBox(x=1, y=2, width=3, height=4)
    ocr_lines = (
        OCRLine("  Vendor:\tAcme\u00a0Ltd  ", 0.91, box),
        OCRLine("   ", 0.2, None),
    )

    normalized_ocr = _source_lines("ignored", ocr_lines)
    normalized_text = _source_lines(" first\n\n second\tvalue ", ())

    assert normalized_ocr == [OCRLine("Vendor: Acme Ltd", 0.91, box)]
    assert normalized_text == [
        OCRLine("first", None, None),
        OCRLine("second value", None, None),
    ]


def test_extract_fields_handles_localized_money_multiline_items_and_dates() -> None:
    invoice = extract_fields(
        """
        Vendor: Contoso Europe GmbH
        Inv No.: EU-2026/17
        Invoice Date: 18th August, 2026
        Payment Due Date: 09/17/2026
        Description Quantity Unit Price Total
        Enterprise consulting
        2 1.234,50 2.469,00 EUR
        Sub total EUR 2.469,00
        VAT 246,90
        Discount (49,00)
        Grand Total EUR 2.666,90
        """
    )

    assert invoice.vendor_name == "Contoso Europe GmbH"
    assert invoice.invoice_number == "EU-2026/17"
    assert invoice.invoice_date == date(2026, 8, 18)
    assert invoice.due_date == date(2026, 9, 17)
    assert invoice.subtotal == Decimal("2469.00")
    assert invoice.tax_amount == Decimal("246.90")
    assert invoice.discount_amount == Decimal("49.00")
    assert invoice.total_amount == Decimal("2666.90")
    assert invoice.currency == "EUR"
    assert invoice.line_items[0].description == "Enterprise consulting"
    assert invoice.line_items[0].quantity == Decimal("2")
    assert invoice.quality is not None
    assert all(check.status == CheckStatus.PASS for check in invoice.quality.checks)


def test_extract_fields_preserves_ocr_evidence_and_prefers_ocr_lines() -> None:
    box = BoundingBox(x=10, y=20, width=100, height=15)
    lines = (
        OCRLine("Supplier: OCR Supplies", 0.93, box),
        OCRLine("Invoice # OCR-42", 0.88, None),
        OCRLine("Date: 2026-08-20", 0.85, None),
        OCRLine("Total $42.00", 0.80, None),
    )

    invoice = extract_fields("Vendor: Wrong Plain Text", ocr_lines=lines)

    assert invoice.vendor_name == "OCR Supplies"
    assert invoice.invoice_number == "OCR-42"
    assert invoice.currency == "USD"
    assert invoice.raw_text == "Vendor: Wrong Plain Text"
    assert invoice.quality is not None
    vendor_evidence = invoice.quality.evidence["vendor_name"]
    assert vendor_evidence.confidence == pytest.approx(0.93)
    assert vendor_evidence.bounding_box == box
    assert "ambiguous dollar symbol" in invoice.quality.warnings[0]


def test_extract_fields_warns_for_ambiguous_date_and_ignores_invalid_date() -> None:
    invoice = extract_fields(
        """Example Ltd
        Invoice: INV-9
        Invoice Date: 02/03/2026
        Due Date: impossible
        Total GBP 20.00
        """
    )

    assert invoice.invoice_date == date(2026, 2, 3)
    assert invoice.due_date is None
    assert invoice.quality is not None
    assert invoice.quality.warnings == [
        "invoice_date used ambiguous numeric date '02/03/2026'; month-first interpretation applied."
    ]
    assert "due_date" not in invoice.quality.evidence


def test_extract_fields_supports_legacy_items_and_last_summary_value() -> None:
    invoice = extract_fields(
        """Old Shop
        Invoice No LEG-100
        Date: 2026-08-18
        Item 1 Widget A
        Item 2 Widget B
        Total 10.00
        Amount Due GBP 12.00
        """
    )

    assert [item.description for item in invoice.line_items] == ["Widget A", "Widget B"]
    assert invoice.total_amount == Decimal("12.00")
    assert invoice.currency == "GBP"


def test_extract_fields_accepts_a_single_character_invoice_number() -> None:
    invoice = extract_fields(
        """Vendor: Small IDs Ltd
        Invoice # 7
        Date: 2026-08-20
        Total USD 10.00
        """
    )

    assert invoice.invoice_number == "7"
    assert invoice.quality is not None
    assert invoice.quality.evidence["invoice_number"].source_text == "Invoice # 7"


def test_extract_fields_ignores_standalone_invoice_heading_before_number() -> None:
    invoice = extract_fields(
        """INVOICE
        Vendor: Northstar Cloud Ltd
        Invoice Number: LL-2026-1042
        Date: 2026-08-20
        Total USD 10.00
        """
    )

    assert invoice.invoice_number == "LL-2026-1042"
    assert invoice.quality is not None
    assert invoice.quality.evidence["invoice_number"].source_text == "Invoice Number: LL-2026-1042"


def test_extract_fields_does_not_treat_tax_percentage_as_a_money_amount() -> None:
    invoice = extract_fields(
        """Vendor: Percentage Tax Ltd
        Invoice # TAX-1
        Date: 2026-08-20
        Subtotal USD 10.00
        Tax (10%)
        Total USD 11.00
        """
    )

    assert invoice.tax_amount is None
    assert invoice.quality is not None
    assert "tax_amount" not in invoice.quality.evidence


def test_extract_fields_combines_wrapped_description_with_full_item_row() -> None:
    invoice = extract_fields(
        """Vendor: Wrapped Rows Ltd
        Description Qty Unit Price Total
        Annual premium
        support plan 2 10.00 20.00
        Total £20.00
        """
    )

    assert len(invoice.line_items) == 1
    assert invoice.line_items[0].description == "Annual premium support plan"
    assert invoice.currency == "GBP"
    assert invoice.quality is not None
    assert invoice.quality.evidence["currency"].method == "currency_symbol"


def test_extract_fields_allows_an_empty_table() -> None:
    invoice = extract_fields("Vendor: Empty Table Ltd\nDescription Qty Price Total")

    assert invoice.line_items == []


def test_extract_fields_empty_input_returns_reviewable_partial_result() -> None:
    invoice = extract_fields(" \n\t")

    assert invoice.raw_text == ""
    assert invoice.vendor_name is None
    assert invoice.line_items == []
    assert invoice.quality is not None
    assert invoice.quality.review_required is True
    assert set(invoice.quality.missing_fields) == {
        "vendor_name",
        "invoice_number",
        "invoice_date",
        "total_amount",
        "currency",
    }
    assert not invoice.quality.evidence
