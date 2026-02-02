# Invoice Scanner & Data Extractor (PyTorch)

A portfolio-ready, production-style project that scans invoices, runs OCR, extracts structured fields, and uses a small PyTorch classifier to enrich results. The project includes:

- **OCR pipeline** with pluggable engines and fallback behavior.
- **Structured extraction** via regex + heuristics.
- **PyTorch classifier** stub to show model training, export, and inference patterns.
- **FastAPI service** for inference.
- **CLI** for batch scanning.

> This project is intentionally simple but uses professional structure, typing, configuration, and logging.

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .

# Generate a sample invoice image
python scripts/generate_sample_invoice.py

# Run the CLI
invoice-scanner scan data/sample_invoice.png

# Run the API
uvicorn invoice_scanner.api:app --reload
```

## Project Layout

```
.
├── data/
│   └── sample_invoice.png (generated locally)
├── scripts/
│   └── generate_sample_invoice.py
├── src/
│   └── invoice_scanner/
│       ├── api.py
│       ├── cli.py
│       ├── config.py
│       ├── extraction.py
│       ├── ocr.py
│       ├── pipeline.py
│       ├── schema.py
│       ├── training.py
│       └── utils.py
└── README.md
```

## API Usage

```bash
curl -X POST "http://localhost:8000/scan" \
  -F "file=@data/sample_invoice.png"
```

## Training Demo

```bash
python -m invoice_scanner.training --epochs 2
```

## Notes

- `pytesseract` requires the **Tesseract OCR** binary installed in your environment.
- If OCR is unavailable, the pipeline will still produce a structured response with partial data.
