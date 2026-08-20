from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from invoice_scanner import api
from invoice_scanner.config import Settings
from invoice_scanner.ocr import (
    ImageTooLargeError,
    InvalidImageError,
    OCRError,
    OCRTimeoutError,
    OCRUnavailableError,
)
from invoice_scanner.pipeline import NoTextDetectedError
from invoice_scanner.schema import InvoiceData


@pytest.fixture
def client() -> TestClient:
    with TestClient(api.app) as test_client:
        yield test_client


def test_dashboard_and_openapi_are_available(client: TestClient) -> None:
    dashboard = client.get("/")
    schema = client.get("/openapi.json").json()

    assert dashboard.status_code == 200
    assert "LedgerLens" in dashboard.text
    assert schema["info"]["title"] == "LedgerLens"
    assert "/api/v1/scan" in schema["paths"]


@pytest.mark.parametrize(
    ("executable", "expected"),
    [("/usr/bin/tesseract", "available"), (None, "unavailable")],
)
def test_health_reports_ocr_runtime(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    executable: str | None,
    expected: str,
) -> None:
    which = MagicMock(return_value=executable)
    monkeypatch.setattr(api.shutil, "which", which)

    assert client.get("/api/v1/health").json() == {
        "status": "ok",
        "service": "ledgerlens",
        "ocr": expected,
    }
    assert client.get("/health").json()["ocr"] == expected
    which.assert_called_with("tesseract")


def test_demo_returns_the_audited_sample(client: TestClient) -> None:
    response = client.get("/api/v1/demo")

    assert response.status_code == 200
    payload = response.json()
    assert payload["vendor_name"] == "Northstar Cloud Ltd"
    assert payload["total_amount"] == "524.70"
    assert payload["quality"]["review_required"] is False
    assert payload["processing"]["source_name"] == "northstar-cloud-demo.txt"


def test_text_extraction_hides_raw_text_by_default_and_allows_opt_in(
    client: TestClient,
) -> None:
    request = {"text": "Vendor: Example Ltd\nTotal USD 12.00", "source_name": "input.txt"}

    private_response = client.post("/api/v1/extract", json=request)
    opted_in_response = client.post("/api/v1/extract?include_raw_text=true", json=request)

    assert private_response.status_code == 200
    assert private_response.json()["raw_text"] is None
    assert private_response.json()["processing"]["source_name"] == "input.txt"
    assert opted_in_response.json()["raw_text"] == request["text"]


@pytest.mark.parametrize(
    "payload",
    [
        {"text": ""},
        {"text": "x" * 50_001},
        {"text": "valid", "source_name": "x" * 256},
        {},
    ],
)
def test_text_extraction_validates_request_limits(
    client: TestClient, payload: dict[str, str]
) -> None:
    assert client.post("/api/v1/extract", json=payload).status_code == 422


@pytest.mark.parametrize(
    ("media_type", "expected_suffix"),
    [
        ("image/png", ".png"),
        ("image/jpeg", ".jpg"),
        ("image/tiff", ".tiff"),
        ("image/webp", ".webp"),
        ("image/bmp", ".bmp"),
    ],
)
def test_scan_accepts_supported_types_sanitizes_name_and_cleans_temp_file(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    media_type: str,
    expected_suffix: str,
) -> None:
    settings = Settings(max_upload_bytes=100)
    calls: list[dict[str, Any]] = []

    def fake_scan(
        image_path: Path,
        *,
        source_name: str,
        settings: Settings,
    ) -> InvoiceData:
        calls.append(
            {
                "path": image_path,
                "source_name": source_name,
                "settings": settings,
                "content": image_path.read_bytes(),
            }
        )
        return InvoiceData(vendor_name="Uploaded Vendor", raw_text="sensitive OCR")

    monkeypatch.setattr(api, "get_settings", MagicMock(return_value=settings))
    monkeypatch.setattr(api, "scan_invoice", fake_scan)

    response = client.post(
        "/api/v1/scan",
        files={"file": ("..\\..\\private.png", b"image bytes", media_type)},
    )

    assert response.status_code == 200
    assert response.json()["vendor_name"] == "Uploaded Vendor"
    assert response.json()["raw_text"] is None
    assert calls[0]["source_name"] == "private.png"
    assert calls[0]["settings"] is settings
    assert calls[0]["content"] == b"image bytes"
    assert calls[0]["path"].suffix == expected_suffix
    assert not calls[0]["path"].exists()


def test_scan_can_include_raw_text_when_explicitly_requested(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(api, "get_settings", MagicMock(return_value=Settings()))
    monkeypatch.setattr(
        api,
        "scan_invoice",
        MagicMock(return_value=InvoiceData(raw_text="OCR text")),
    )

    response = client.post(
        "/api/v1/scan?include_raw_text=true",
        files={"file": ("invoice.png", b"bytes", "image/png")},
    )

    assert response.status_code == 200
    assert response.json()["raw_text"] == "OCR text"


def test_scan_rejects_unsupported_empty_and_oversized_uploads(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    scan_invoice = MagicMock()
    monkeypatch.setattr(api, "scan_invoice", scan_invoice)
    monkeypatch.setattr(
        api,
        "get_settings",
        MagicMock(return_value=Settings(max_upload_bytes=3)),
    )

    unsupported = client.post(
        "/api/v1/scan",
        files={"file": ("invoice.gif", b"GIF89", "image/gif")},
    )
    empty = client.post(
        "/api/v1/scan",
        files={"file": ("invoice.png", b"", "image/png")},
    )
    oversized = client.post(
        "/api/v1/scan",
        files={"file": ("invoice.png", b"1234", "image/png")},
    )

    assert unsupported.status_code == 415
    assert "Supported file types" in unsupported.json()["detail"]
    assert empty.status_code == 422
    assert empty.json()["detail"] == "The uploaded file is empty."
    assert oversized.status_code == 413
    assert "Upload exceeds" in oversized.json()["detail"]
    scan_invoice.assert_not_called()


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (ImageTooLargeError("too many pixels"), 413),
        (InvalidImageError("not an image"), 422),
        (NoTextDetectedError("blank"), 422),
        (OCRUnavailableError("tesseract missing"), 503),
        (OCRTimeoutError("too slow"), 504),
        (OCRError("engine failure"), 502),
    ],
)
def test_scan_maps_expected_errors_and_still_removes_temp_file(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected_status: int,
) -> None:
    temp_paths: list[Path] = []

    def fail_scan(image_path: Path, **_: object) -> InvoiceData:
        assert image_path.exists()
        temp_paths.append(image_path)
        raise error

    monkeypatch.setattr(api, "get_settings", MagicMock(return_value=Settings()))
    monkeypatch.setattr(api, "scan_invoice", fail_scan)

    response = client.post(
        "/api/v1/scan",
        files={"file": ("invoice.png", b"image", "image/png")},
    )

    assert response.status_code == expected_status
    assert response.json()["detail"] == str(error)
    assert len(temp_paths) == 1
    assert not temp_paths[0].exists()


def test_legacy_scan_route_delegates_to_current_scanner(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    scan_invoice = MagicMock(return_value=InvoiceData(invoice_number="LEGACY"))
    monkeypatch.setattr(api, "get_settings", MagicMock(return_value=Settings()))
    monkeypatch.setattr(api, "scan_invoice", scan_invoice)

    response = client.post(
        "/scan",
        files={"file": ("legacy.jpg", b"image", "image/jpeg")},
    )

    assert response.status_code == 200
    assert response.json()["invoice_number"] == "LEGACY"
    scan_invoice.assert_called_once()
