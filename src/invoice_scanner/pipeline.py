"""Orchestration for OCR, extraction, and deterministic invoice auditing."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter

from invoice_scanner.audit import audit_invoice
from invoice_scanner.config import Settings, get_settings
from invoice_scanner.extraction import extract_fields
from invoice_scanner.ocr import OCRError, extract_document
from invoice_scanner.schema import InvoiceData, ProcessingMetadata


class NoTextDetectedError(OCRError):
    """OCR completed, but the image did not contain readable text."""


def extract_invoice_text(
    text: str,
    *,
    source_name: str | None = None,
    settings: Settings | None = None,
) -> InvoiceData:
    """Run extraction and audit on text supplied by another OCR system."""

    active_settings = settings or get_settings()
    started = perf_counter()
    invoice = extract_fields(text)
    invoice.processing = ProcessingMetadata(
        source_name=source_name,
        ocr_engine="provided_text",
        duration_ms=(perf_counter() - started) * 1000,
    )
    if not active_settings.expose_raw_text:
        invoice.raw_text = None
    return invoice


def scan_invoice(
    image_path: Path,
    *,
    source_name: str | None = None,
    settings: Settings | None = None,
) -> InvoiceData:
    """Scan one image and return structured fields with evidence and checks."""

    active_settings = settings or get_settings()
    started = perf_counter()
    ocr_result = extract_document(image_path, settings=active_settings)
    if not ocr_result.text.strip():
        raise NoTextDetectedError("No readable text was detected in the image.")

    invoice = extract_fields(ocr_result.text, ocr_lines=ocr_result.lines)
    warnings = list(invoice.quality.warnings if invoice.quality else [])
    if ocr_result.confidence is not None and ocr_result.confidence < 0.60:
        warnings.append(
            f"Average OCR confidence is low ({ocr_result.confidence:.0%}); "
            "manual review is recommended."
        )
    evidence = invoice.quality.evidence if invoice.quality else {}
    invoice.quality = audit_invoice(invoice, evidence=evidence, warnings=warnings)
    invoice.processing = ProcessingMetadata(
        source_name=source_name or image_path.name,
        ocr_engine=ocr_result.engine,
        duration_ms=(perf_counter() - started) * 1000,
        ocr_confidence=ocr_result.confidence,
    )
    if not active_settings.expose_raw_text:
        invoice.raw_text = None
    return invoice
