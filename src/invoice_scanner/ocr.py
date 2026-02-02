from __future__ import annotations

from pathlib import Path

from PIL import Image

try:
    import pytesseract
except ImportError:  # pragma: no cover - optional dependency at runtime
    pytesseract = None

from invoice_scanner.config import settings


class OCRError(RuntimeError):
    pass


def extract_text(image_path: Path) -> str:
    if pytesseract is None:
        raise OCRError("pytesseract is not installed.")

    try:
        image = Image.open(image_path)
    except FileNotFoundError as exc:
        raise OCRError(f"Image not found: {image_path}") from exc

    return pytesseract.image_to_string(image, lang=settings.ocr_lang)
