from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from PIL import Image

from invoice_scanner import ocr
from invoice_scanner.config import Settings
from invoice_scanner.pipeline import extract_invoice_text, scan_invoice
from invoice_scanner.sample import DEMO_INVOICE_TEXT
from invoice_scanner.schema import CheckStatus


def _tesseract_data(text: str) -> dict[str, list[object]]:
    data: dict[str, list[object]] = {
        key: []
        for key in (
            "text",
            "conf",
            "page_num",
            "block_num",
            "par_num",
            "line_num",
            "left",
            "top",
            "width",
            "height",
        )
    }
    for line_number, line in enumerate(text.splitlines(), start=1):
        left = 10
        for word in line.split():
            width = max(len(word) * 7, 7)
            data["text"].append(word)
            data["conf"].append(96)
            data["page_num"].append(1)
            data["block_num"].append(1)
            data["par_num"].append(1)
            data["line_num"].append(line_number)
            data["left"].append(left)
            data["top"].append(line_number * 20)
            data["width"].append(width)
            data["height"].append(12)
            left += width + 5
    return data


def test_demo_text_runs_end_to_end_with_reconciled_evidence() -> None:
    invoice = extract_invoice_text(DEMO_INVOICE_TEXT, source_name="demo.txt")

    assert invoice.invoice_number == "LL-2026-1042"
    assert len(invoice.line_items) == 2
    assert invoice.quality is not None
    assert invoice.quality.score == 100
    assert invoice.quality.review_required is False
    assert all(check.status == CheckStatus.PASS for check in invoice.quality.checks)
    assert {
        "vendor_name",
        "invoice_number",
        "invoice_date",
        "due_date",
        "subtotal",
        "tax_amount",
        "total_amount",
        "currency",
        "line_items",
    } <= invoice.quality.evidence.keys()


def test_image_to_ocr_to_audit_flow_with_only_tesseract_mocked(monkeypatch, tmp_path: Path) -> None:
    image_path = tmp_path / "sample-invoice.png"
    image = Image.new("RGB", (800, 600), "white")
    image.save(image_path)
    image.close()
    image_to_data = MagicMock(return_value=_tesseract_data(DEMO_INVOICE_TEXT))
    fake_tesseract = SimpleNamespace(
        Output=SimpleNamespace(DICT="DICT"),
        TesseractNotFoundError=type("TesseractNotFoundError", (RuntimeError,), {}),
        image_to_data=image_to_data,
    )
    monkeypatch.setattr(ocr, "pytesseract", fake_tesseract)

    invoice = scan_invoice(
        image_path,
        source_name="portfolio-demo.png",
        settings=Settings(ocr_timeout_seconds=5),
    )

    assert invoice.vendor_name == "Northstar Cloud Ltd"
    assert invoice.total_amount is not None
    assert str(invoice.total_amount) == "524.70"
    assert invoice.quality is not None
    assert invoice.quality.review_required is False
    assert invoice.quality.evidence["vendor_name"].confidence == 0.96
    assert invoice.quality.evidence["vendor_name"].bounding_box is not None
    assert invoice.processing is not None
    assert invoice.processing.source_name == "portfolio-demo.png"
    assert invoice.processing.ocr_confidence == 0.96
    image_to_data.assert_called_once()
