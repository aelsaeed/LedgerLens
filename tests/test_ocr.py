from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PIL import Image

from invoice_scanner import ocr
from invoice_scanner.config import Settings
from invoice_scanner.ocr import (
    ImageTooLargeError,
    InvalidImageError,
    OCRError,
    OCRLine,
    OCRResult,
    OCRTimeoutError,
    OCRUnavailableError,
)


def test_load_image_normalizes_a_valid_image(tmp_path: Path) -> None:
    image_path = tmp_path / "invoice.png"
    source = Image.new("RGB", (2, 1))
    source.putdata([(50, 50, 50), (100, 100, 100)])
    source.save(image_path)
    source.close()

    loaded = ocr._load_image(image_path, Settings(max_image_pixels=2))
    try:
        assert loaded.mode == "L"
        assert loaded.size == (2, 1)
        low, high = loaded.getextrema()
        assert low == 0
        assert high >= 254
    finally:
        loaded.close()


def test_load_image_rejects_missing_corrupt_and_oversized_files(tmp_path: Path) -> None:
    with pytest.raises(InvalidImageError, match="Image not found"):
        ocr._load_image(tmp_path / "missing.png", Settings())

    corrupt = tmp_path / "corrupt.png"
    corrupt.write_bytes(b"this is not an image")
    with pytest.raises(InvalidImageError, match="not a readable image"):
        ocr._load_image(corrupt, Settings())

    large = tmp_path / "large.png"
    Image.new("RGB", (3, 2), "white").save(large)
    with pytest.raises(ImageTooLargeError, match="6 pixels; the limit is 5"):
        ocr._load_image(large, Settings(max_image_pixels=5))


def test_load_image_maps_pillow_decompression_bomb_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    image_path = tmp_path / "bomb.png"
    image_path.touch()
    monkeypatch.setattr(
        ocr.Image,
        "open",
        MagicMock(side_effect=Image.DecompressionBombError("unsafe image dimensions")),
    )

    with pytest.raises(ImageTooLargeError, match="25,000,000-pixel safety limit"):
        ocr._load_image(image_path, Settings(max_image_pixels=25_000_000))


def test_lines_from_data_groups_words_and_builds_bounding_boxes() -> None:
    data: dict[str, list[object]] = {
        "text": ["  Invoice", "#42 ", "", "Total"],
        "conf": ["90", 70, 99, "bad"],
        "page_num": [1, 1, 1, 1],
        "block_num": [1, 1, 1, 2],
        "par_num": [1, 1, 1, 1],
        "line_num": [1, 1, 1, 1],
        "left": [10, 65, 0, 5],
        "top": [20, 20, 0, 50],
        "width": [50, 25, 0, 30],
        "height": [10, 12, 0, 10],
    }

    lines = ocr._lines_from_data(data)

    assert len(lines) == 2
    assert lines[0].text == "Invoice #42"
    assert lines[0].confidence == pytest.approx(0.8)
    assert lines[0].bounding_box is not None
    assert lines[0].bounding_box.model_dump() == {
        "x": 10,
        "y": 20,
        "width": 80,
        "height": 12,
    }
    assert lines[1].confidence is None


def test_lines_from_data_tolerates_missing_columns_and_empty_text() -> None:
    lines = ocr._lines_from_data({"text": ["Hello"]})

    assert lines == (
        OCRLine(
            text="Hello",
            confidence=None,
            bounding_box=ocr.BoundingBox(x=0, y=0, width=0, height=0),
        ),
    )
    assert ocr._lines_from_data({}) == ()


class FakeTesseractNotFoundError(RuntimeError):
    pass


def _fake_tesseract(result: object = None, error: Exception | None = None) -> SimpleNamespace:
    image_to_data = MagicMock(return_value=result)
    if error is not None:
        image_to_data.side_effect = error
    return SimpleNamespace(
        Output=SimpleNamespace(DICT="DICT"),
        TesseractNotFoundError=FakeTesseractNotFoundError,
        image_to_data=image_to_data,
    )


def test_extract_document_calls_tesseract_and_aggregates_confidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_image = MagicMock()
    data = {
        "text": ["Invoice", "Total"],
        "conf": [80, 60],
        "page_num": [1, 1],
        "block_num": [1, 1],
        "par_num": [1, 1],
        "line_num": [1, 2],
        "left": [0, 0],
        "top": [0, 20],
        "width": [20, 20],
        "height": [10, 10],
    }
    fake_tesseract = _fake_tesseract(data)
    monkeypatch.setattr(ocr, "pytesseract", fake_tesseract)
    monkeypatch.setattr(ocr, "_load_image", MagicMock(return_value=fake_image))
    settings = Settings(ocr_lang="deu", ocr_timeout_seconds=7)

    result = ocr.extract_document(tmp_path / "input.png", settings=settings)

    assert result.text == "Invoice\nTotal"
    assert result.confidence == pytest.approx(0.7)
    assert result.engine == "tesseract"
    fake_tesseract.image_to_data.assert_called_once_with(
        fake_image,
        lang="deu",
        output_type="DICT",
        timeout=7,
    )
    fake_image.close.assert_called_once_with()


def test_extract_document_uses_default_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(ocr_lang="fra")
    fake_image = MagicMock()
    fake_tesseract = _fake_tesseract({"text": []})
    monkeypatch.setattr(ocr, "pytesseract", fake_tesseract)
    monkeypatch.setattr(ocr, "get_settings", MagicMock(return_value=settings))
    monkeypatch.setattr(ocr, "_load_image", MagicMock(return_value=fake_image))

    result = ocr.extract_document(Path("unused.png"))

    assert result == OCRResult(text="", lines=(), confidence=None)
    fake_tesseract.image_to_data.assert_called_once()


def test_extract_document_reports_missing_python_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ocr, "pytesseract", None)

    with pytest.raises(OCRUnavailableError, match="pytesseract is not installed"):
        ocr.extract_document(Path("unused.png"), settings=Settings())


@pytest.mark.parametrize(
    ("error", "expected_type", "message"),
    [
        (
            FakeTesseractNotFoundError("missing"),
            OCRUnavailableError,
            "not installed or is not on PATH",
        ),
        (RuntimeError("Tesseract process timeout"), OCRTimeoutError, "exceeded 3 seconds"),
        (RuntimeError("engine crashed"), OCRError, "could not process"),
    ],
)
def test_extract_document_maps_runtime_errors_and_always_closes_image(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected_type: type[Exception],
    message: str,
) -> None:
    fake_image = MagicMock()
    monkeypatch.setattr(ocr, "pytesseract", _fake_tesseract(error=error))
    monkeypatch.setattr(ocr, "_load_image", MagicMock(return_value=fake_image))

    with pytest.raises(expected_type, match=message):
        ocr.extract_document(Path("unused.png"), settings=Settings(ocr_timeout_seconds=3))

    fake_image.close.assert_called_once_with()


def test_extract_text_is_a_backward_compatible_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    extract = MagicMock(return_value=OCRResult(text="recognized", lines=(), confidence=None))
    monkeypatch.setattr(ocr, "extract_document", extract)
    path = Path("invoice.png")

    assert ocr.extract_text(path) == "recognized"
    extract.assert_called_once_with(path)
