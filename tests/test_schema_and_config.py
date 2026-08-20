from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from invoice_scanner import config
from invoice_scanner.config import Settings
from invoice_scanner.schema import (
    BoundingBox,
    FieldEvidence,
    LineItem,
    ProcessingMetadata,
    QualityReport,
)


def test_settings_read_prefixed_environment_and_are_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config.get_settings.cache_clear()
    monkeypatch.setenv("LEDGERLENS_OCR_LANG", "spa")
    monkeypatch.setenv("LEDGERLENS_EXPOSE_RAW_TEXT", "false")
    try:
        first = config.get_settings()
        second = config.get_settings()

        assert first is second
        assert first.ocr_lang == "spa"
        assert first.expose_raw_text is False
    finally:
        config.get_settings.cache_clear()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"ocr_timeout_seconds": 0},
        {"ocr_timeout_seconds": 121},
        {"max_upload_bytes": 0},
        {"max_image_pixels": -1},
    ],
)
def test_settings_reject_unsafe_limits(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        Settings(**kwargs)


def test_schema_constraints_reject_invalid_operational_values() -> None:
    with pytest.raises(ValidationError):
        BoundingBox(x=-1, y=0, width=1, height=1)
    with pytest.raises(ValidationError):
        FieldEvidence(source_text="x", method="ocr", confidence=1.01)
    with pytest.raises(ValidationError):
        QualityReport(score=101, review_required=False)
    with pytest.raises(ValidationError):
        ProcessingMetadata(source_name=None, ocr_engine="test", duration_ms=-0.1)


def test_line_item_strips_description_and_preserves_decimal_precision() -> None:
    item = LineItem(description="  Consulting  ", quantity=Decimal("1.50"))

    assert item.description == "Consulting"
    assert item.quantity == Decimal("1.50")
    with pytest.raises(ValidationError):
        LineItem(description="   ")
