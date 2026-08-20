from __future__ import annotations

import warnings
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean

from PIL import Image, ImageOps, UnidentifiedImageError

try:
    import pytesseract
except ImportError:  # pragma: no cover - optional dependency at runtime
    pytesseract = None

from invoice_scanner.config import Settings, get_settings
from invoice_scanner.schema import BoundingBox


class OCRError(RuntimeError):
    """Base class for expected OCR failures."""


class OCRUnavailableError(OCRError):
    """The Tesseract runtime is not installed or cannot be started."""


class OCRTimeoutError(OCRError):
    """OCR exceeded the configured processing deadline."""


class InvalidImageError(OCRError):
    """The input is missing, corrupt, or is not a supported image."""


class ImageTooLargeError(InvalidImageError):
    """The decoded image exceeds the pixel safety limit."""


@dataclass(frozen=True, slots=True)
class OCRLine:
    text: str
    confidence: float | None
    bounding_box: BoundingBox | None


@dataclass(frozen=True, slots=True)
class OCRResult:
    text: str
    lines: tuple[OCRLine, ...]
    confidence: float | None
    engine: str = "tesseract"


def _load_image(image_path: Path, settings: Settings) -> Image.Image:
    if not image_path.is_file():
        raise InvalidImageError(f"Image not found: {image_path}")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(image_path) as source:
                width, height = source.size
                if width * height > settings.max_image_pixels:
                    raise ImageTooLargeError(
                        f"Image has {width * height:,} pixels; the limit is "
                        f"{settings.max_image_pixels:,}."
                    )
                source.load()
                image = ImageOps.exif_transpose(source).convert("L")
                return ImageOps.autocontrast(image)
    except ImageTooLargeError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageTooLargeError(
            f"The decoded image exceeds the {settings.max_image_pixels:,}-pixel safety limit."
        ) from exc
    except (
        UnidentifiedImageError,
        OSError,
    ) as exc:
        raise InvalidImageError("The uploaded file is not a readable image.") from exc


def _lines_from_data(data: dict[str, list[object]]) -> tuple[OCRLine, ...]:
    grouped: OrderedDict[tuple[int, int, int, int], list[dict[str, object]]] = OrderedDict()
    texts = data.get("text", [])

    for index, raw_text in enumerate(texts):
        text = str(raw_text).strip()
        if not text:
            continue

        def value(key: str, default: object = 0, *, row: int = index) -> object:
            values = data.get(key, [])
            return values[row] if row < len(values) else default

        key = tuple(int(value(name)) for name in ("page_num", "block_num", "par_num", "line_num"))
        try:
            confidence = float(value("conf", -1))
        except (TypeError, ValueError):
            confidence = -1
        grouped.setdefault(key, []).append(
            {
                "text": text,
                "confidence": confidence,
                "left": int(value("left")),
                "top": int(value("top")),
                "width": int(value("width")),
                "height": int(value("height")),
            }
        )

    lines: list[OCRLine] = []
    for words in grouped.values():
        confidences = [
            float(word["confidence"]) for word in words if float(word["confidence"]) >= 0
        ]
        left = min(int(word["left"]) for word in words)
        top = min(int(word["top"]) for word in words)
        right = max(int(word["left"]) + int(word["width"]) for word in words)
        bottom = max(int(word["top"]) + int(word["height"]) for word in words)
        lines.append(
            OCRLine(
                text=" ".join(str(word["text"]) for word in words),
                confidence=(fmean(confidences) / 100 if confidences else None),
                bounding_box=BoundingBox(x=left, y=top, width=right - left, height=bottom - top),
            )
        )
    return tuple(lines)


def extract_document(image_path: Path, *, settings: Settings | None = None) -> OCRResult:
    """Extract text, line confidence, and bounding boxes from one image."""

    active_settings = settings or get_settings()
    if pytesseract is None:
        raise OCRUnavailableError("pytesseract is not installed.")

    image = _load_image(image_path, active_settings)
    try:
        data = pytesseract.image_to_data(
            image,
            lang=active_settings.ocr_lang,
            output_type=pytesseract.Output.DICT,
            timeout=active_settings.ocr_timeout_seconds,
        )
    except getattr(pytesseract, "TesseractNotFoundError", RuntimeError) as exc:
        raise OCRUnavailableError("Tesseract OCR is not installed or is not on PATH.") from exc
    except RuntimeError as exc:
        if "timeout" in str(exc).lower():
            raise OCRTimeoutError(
                f"OCR exceeded {active_settings.ocr_timeout_seconds} seconds."
            ) from exc
        raise OCRError("Tesseract could not process this image.") from exc
    finally:
        image.close()

    lines = _lines_from_data(data)
    confidences = [line.confidence for line in lines if line.confidence is not None]
    return OCRResult(
        text="\n".join(line.text for line in lines),
        lines=lines,
        confidence=fmean(confidences) if confidences else None,
    )


def extract_text(image_path: Path) -> str:
    """Backward-compatible text-only OCR helper."""

    return extract_document(image_path).text
