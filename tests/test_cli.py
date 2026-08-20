from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from invoice_scanner import cli
from invoice_scanner.ocr import OCRUnavailableError
from invoice_scanner.schema import InvoiceData

runner = CliRunner()


def test_cli_without_command_shows_help() -> None:
    result = runner.invoke(cli.app, [])

    assert result.exit_code == 2
    assert "Usage" in result.output
    assert "Extract and validate invoice data" in result.output


def test_scan_command_emits_single_private_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    image_path = tmp_path / "invoice.png"
    image_path.write_bytes(b"placeholder")
    scan_invoice = MagicMock(return_value=InvoiceData(invoice_number="INV-1", raw_text="sensitive"))
    monkeypatch.setattr(cli, "scan_invoice", scan_invoice)

    result = runner.invoke(cli.app, ["scan", str(image_path)])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["raw_text"] is None
    scan_invoice.assert_called_once_with(image_path, source_name="invoice.png")


def test_scan_command_can_include_raw_text(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    image_path = tmp_path / "invoice.png"
    image_path.write_bytes(b"placeholder")
    monkeypatch.setattr(
        cli,
        "scan_invoice",
        MagicMock(return_value=InvoiceData(raw_text="included")),
    )

    result = runner.invoke(
        cli.app,
        ["scan", "--include-raw-text", str(image_path)],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["raw_text"] == "included"


def test_scan_command_emits_a_json_array_for_multiple_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    first = tmp_path / "one.png"
    second = tmp_path / "two.png"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    scan_invoice = MagicMock(
        side_effect=[InvoiceData(invoice_number="1"), InvoiceData(invoice_number="2")]
    )
    monkeypatch.setattr(cli, "scan_invoice", scan_invoice)

    result = runner.invoke(cli.app, ["scan", str(first), str(second)])

    assert result.exit_code == 0
    assert [item["invoice_number"] for item in json.loads(result.stdout)] == ["1", "2"]
    assert [call.kwargs["source_name"] for call in scan_invoice.call_args_list] == [
        "one.png",
        "two.png",
    ]


def test_scan_command_returns_nonzero_for_expected_ocr_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    image_path = tmp_path / "invoice.png"
    image_path.write_bytes(b"placeholder")
    monkeypatch.setattr(
        cli,
        "scan_invoice",
        MagicMock(side_effect=OCRUnavailableError("Tesseract is missing")),
    )

    result = runner.invoke(cli.app, ["scan", str(image_path)])

    assert result.exit_code == 1
    assert f"Could not scan {image_path}: Tesseract is missing" in result.output


def test_scan_command_rejects_a_missing_path() -> None:
    result = runner.invoke(cli.app, ["scan", "/definitely/missing/invoice.png"])

    assert result.exit_code == 2
    assert "Invalid value for 'paths'" in result.output
    assert "/definitely/missing/invoice.png" in result.output


def test_extract_text_command_reads_utf8_and_outputs_invoice(tmp_path: Path) -> None:
    text_path = tmp_path / "provider.txt"
    text_path.write_text("Vendor: Café Ltd\nInvoice: UTF-8\nTotal EUR 5.00", encoding="utf-8")

    result = runner.invoke(cli.app, ["extract-text", str(text_path)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["vendor_name"] == "Café Ltd"
    assert payload["invoice_number"] == "UTF-8"
    assert payload["processing"]["source_name"] == "provider.txt"


def test_demo_command_outputs_deterministic_sample() -> None:
    result = runner.invoke(cli.app, ["demo"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["invoice_number"] == "LL-2026-1042"
    assert payload["quality"]["score"] == 100
