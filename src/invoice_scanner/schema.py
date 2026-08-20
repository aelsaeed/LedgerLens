"""Public response models for extracted and audited invoices."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class BoundingBox(BaseModel):
    """Pixel coordinates for evidence found by the OCR engine."""

    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(ge=0)
    height: int = Field(ge=0)


class FieldEvidence(BaseModel):
    """Trace an extracted value back to the line that produced it."""

    source_text: str
    method: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    bounding_box: BoundingBox | None = None


class CheckStatus(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    SKIPPED = "skipped"


class AuditCheck(BaseModel):
    """One deterministic validation performed on an invoice."""

    code: str
    status: CheckStatus
    message: str
    expected: Decimal | None = None
    actual: Decimal | None = None
    delta: Decimal | None = None


class QualityReport(BaseModel):
    """Explain why an invoice is safe to automate or needs review."""

    score: int = Field(ge=0, le=100)
    review_required: bool
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checks: list[AuditCheck] = Field(default_factory=list)
    evidence: dict[str, FieldEvidence] = Field(default_factory=dict)


class ProcessingMetadata(BaseModel):
    """Operational details about a scan, without retaining the source file."""

    source_name: str | None = None
    ocr_engine: str
    duration_ms: float = Field(ge=0)
    ocr_confidence: float | None = Field(default=None, ge=0, le=1)


class LineItem(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    description: str = Field(min_length=1)
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    total: Decimal | None = None


class InvoiceData(BaseModel):
    """Normalized invoice fields plus evidence and deterministic audit results."""

    vendor_name: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    subtotal: Decimal | None = None
    tax_amount: Decimal | None = None
    discount_amount: Decimal | None = None
    total_amount: Decimal | None = None
    currency: str | None = None
    line_items: list[LineItem] = Field(default_factory=list)
    raw_text: str | None = None
    quality: QualityReport | None = None
    processing: ProcessingMetadata | None = None
