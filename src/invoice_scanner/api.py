"""FastAPI application and safe upload boundary for LedgerLens."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from invoice_scanner.config import get_settings
from invoice_scanner.ocr import (
    ImageTooLargeError,
    InvalidImageError,
    OCRError,
    OCRTimeoutError,
    OCRUnavailableError,
)
from invoice_scanner.pipeline import NoTextDetectedError, extract_invoice_text, scan_invoice
from invoice_scanner.sample import DEMO_INVOICE_TEXT
from invoice_scanner.schema import InvoiceData

STATIC_DIR = Path(__file__).with_name("static")
SUPPORTED_MEDIA_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/tiff": ".tiff",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
}


class TextExtractionRequest(BaseModel):
    text: str = Field(min_length=1, max_length=50_000)
    source_name: str | None = Field(default=None, max_length=255)


app = FastAPI(
    title="LedgerLens",
    summary="Explainable invoice extraction and arithmetic validation",
    description=(
        "Convert invoice images or existing OCR text into normalized, auditable JSON. "
        "Every result includes source evidence, deterministic checks, and a review decision."
    ),
    version="0.2.0",
    contact={"name": "LedgerLens contributors"},
    license_info={"name": "MIT"},
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def dashboard() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/v1/health", tags=["operations"])
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "ledgerlens",
        "ocr": "available" if shutil.which("tesseract") else "unavailable",
    }


@app.get("/health", include_in_schema=False)
async def legacy_health() -> dict[str, str]:
    return await health()


@app.get("/api/v1/demo", response_model=InvoiceData, tags=["demo"])
async def demo() -> InvoiceData:
    """Return a deterministic example so the product can be explored without OCR."""

    return await run_in_threadpool(
        extract_invoice_text,
        DEMO_INVOICE_TEXT,
        source_name="northstar-cloud-demo.txt",
    )


@app.post("/api/v1/extract", response_model=InvoiceData, tags=["extraction"])
async def extract_text(
    payload: TextExtractionRequest,
    include_raw_text: Annotated[
        bool,
        Query(description="Include potentially sensitive source text in the response."),
    ] = False,
) -> InvoiceData:
    """Normalize and audit text produced by an external OCR provider."""

    invoice = await run_in_threadpool(
        extract_invoice_text,
        payload.text,
        source_name=payload.source_name,
    )
    if not include_raw_text:
        invoice.raw_text = None
    return invoice


async def _read_upload(file: UploadFile, limit: int) -> bytes:
    content = bytearray()
    while chunk := await file.read(min(1024 * 1024, limit - len(content) + 1)):
        content.extend(chunk)
        if len(content) > limit:
            raise HTTPException(
                status_code=413,
                detail=f"Upload exceeds the {limit // (1024 * 1024)} MB limit.",
            )
    return bytes(content)


@app.post("/api/v1/scan", response_model=InvoiceData, tags=["extraction"])
async def scan(
    file: Annotated[UploadFile, File()],
    include_raw_text: Annotated[
        bool,
        Query(description="Include potentially sensitive OCR text in the response."),
    ] = False,
) -> InvoiceData:
    """OCR and audit a PNG, JPEG, TIFF, WebP, or BMP invoice image."""

    media_type = (file.content_type or "").lower()
    if media_type not in SUPPORTED_MEDIA_TYPES:
        await file.close()
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Supported file types: PNG, JPEG, TIFF, WebP, and BMP.",
        )

    settings = get_settings()
    temp_path: Path | None = None
    try:
        content = await _read_upload(file, settings.max_upload_bytes)
        if not content:
            raise HTTPException(
                status_code=422,
                detail="The uploaded file is empty.",
            )
        with tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=SUPPORTED_MEDIA_TYPES[media_type],
            delete=False,
        ) as temporary_file:
            temp_path = Path(temporary_file.name)
            temporary_file.write(content)

        source_name = Path((file.filename or "invoice-upload").replace("\\", "/")).name
        invoice = await run_in_threadpool(
            scan_invoice,
            temp_path,
            source_name=source_name,
            settings=settings,
        )
        if not include_raw_text:
            invoice.raw_text = None
        return invoice
    except ImageTooLargeError as exc:
        raise HTTPException(
            status_code=413,
            detail=str(exc),
        ) from exc
    except (InvalidImageError, NoTextDetectedError) as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc
    except OCRUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except OCRTimeoutError as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except OCRError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    finally:
        await file.close()
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


@app.post("/scan", response_model=InvoiceData, include_in_schema=False)
async def legacy_scan(file: Annotated[UploadFile, File()]) -> InvoiceData:
    return await scan(file)
