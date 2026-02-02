from __future__ import annotations

from pathlib import Path
import tempfile

from fastapi import FastAPI, File, UploadFile

from invoice_scanner.pipeline import scan_invoice

app = FastAPI(title="Invoice Scanner")


@app.post("/scan")
async def scan(file: UploadFile = File(...)):
    suffix = Path(file.filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        temp_path = Path(tmp.name)

    invoice = scan_invoice(temp_path)
    return invoice.model_dump()
