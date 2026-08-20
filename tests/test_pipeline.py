from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from invoice_scanner import pipeline
from invoice_scanner.config import Settings
from invoice_scanner.ocr import OCRLine, OCRResult, OCRUnavailableError
from invoice_scanner.sample import DEMO_INVOICE_TEXT
from invoice_scanner.schema import CheckStatus, InvoiceData


def test_extract_invoice_text_adds_metadata_and_can_hide_raw_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    times = iter((10.0, 10.125))
    monkeypatch.setattr(pipeline, "perf_counter", lambda: next(times))

    invoice = pipeline.extract_invoice_text(
        DEMO_INVOICE_TEXT,
        source_name="provider.txt",
        settings=Settings(expose_raw_text=False),
    )

    assert invoice.raw_text is None
    assert invoice.processing is not None
    assert invoice.processing.source_name == "provider.txt"
    assert invoice.processing.ocr_engine == "provided_text"
    assert invoice.processing.duration_ms == pytest.approx(125)
    assert invoice.processing.ocr_confidence is None


def test_extract_invoice_text_uses_default_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings = MagicMock(return_value=Settings(expose_raw_text=True))
    monkeypatch.setattr(pipeline, "get_settings", get_settings)

    invoice = pipeline.extract_invoice_text("Vendor: Example")

    get_settings.assert_called_once_with()
    assert invoice.raw_text == "Vendor: Example"
    assert invoice.processing is not None
    assert invoice.processing.source_name is None


def test_scan_invoice_enriches_ocr_result_and_warns_on_low_confidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ocr_result = OCRResult(
        text=DEMO_INVOICE_TEXT,
        lines=(OCRLine("Northstar Cloud Ltd", 0.5, None),),
        confidence=0.5,
        engine="mock-ocr",
    )
    extract_document = MagicMock(return_value=ocr_result)
    monkeypatch.setattr(pipeline, "extract_document", extract_document)
    times = iter((20.0, 20.25))
    monkeypatch.setattr(pipeline, "perf_counter", lambda: next(times))
    path = Path("/tmp/scanned-invoice.png")
    settings = Settings(expose_raw_text=True)

    invoice = pipeline.scan_invoice(path, settings=settings)

    extract_document.assert_called_once_with(path, settings=settings)
    assert invoice.processing is not None
    assert invoice.processing.source_name == "scanned-invoice.png"
    assert invoice.processing.ocr_engine == "mock-ocr"
    assert invoice.processing.ocr_confidence == 0.5
    assert invoice.processing.duration_ms == pytest.approx(250)
    assert invoice.quality is not None
    assert invoice.quality.review_required is True
    assert any("Average OCR confidence is low (50%)" in item for item in invoice.quality.warnings)


def test_scan_invoice_accepts_high_confidence_and_explicit_source_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pipeline,
        "extract_document",
        MagicMock(
            return_value=OCRResult(
                text=DEMO_INVOICE_TEXT,
                lines=(),
                confidence=0.95,
                engine="custom",
            )
        ),
    )

    invoice = pipeline.scan_invoice(
        Path("opaque.tmp"),
        source_name="customer.png",
        settings=Settings(expose_raw_text=False),
    )

    assert invoice.raw_text is None
    assert invoice.processing is not None
    assert invoice.processing.source_name == "customer.png"
    assert invoice.quality is not None
    assert not invoice.quality.warnings
    assert all(check.status == CheckStatus.PASS for check in invoice.quality.checks)


def test_scan_invoice_rejects_whitespace_only_ocr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pipeline,
        "extract_document",
        MagicMock(return_value=OCRResult(text=" \n", lines=(), confidence=None)),
    )

    with pytest.raises(pipeline.NoTextDetectedError, match="No readable text"):
        pipeline.scan_invoice(Path("blank.png"), settings=Settings())


def test_scan_invoice_propagates_ocr_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pipeline,
        "extract_document",
        MagicMock(side_effect=OCRUnavailableError("missing runtime")),
    )

    with pytest.raises(OCRUnavailableError, match="missing runtime"):
        pipeline.scan_invoice(Path("invoice.png"), settings=Settings())


def test_scan_invoice_handles_extractor_without_an_initial_quality_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pipeline,
        "extract_document",
        MagicMock(return_value=OCRResult(text="anything", lines=(), confidence=None)),
    )
    monkeypatch.setattr(pipeline, "extract_fields", MagicMock(return_value=InvoiceData()))

    invoice = pipeline.scan_invoice(Path("invoice.png"), settings=Settings())

    assert invoice.quality is not None
    assert invoice.quality.review_required is True
