"""Command-line interface for local and batch invoice processing."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from invoice_scanner.ocr import OCRError
from invoice_scanner.pipeline import extract_invoice_text, scan_invoice
from invoice_scanner.sample import DEMO_INVOICE_TEXT

app = typer.Typer(
    name="ledgerlens",
    help="Extract and validate invoice data with review-ready evidence.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """LedgerLens invoice intelligence."""


@app.command()
def scan(
    paths: Annotated[
        list[Path],
        typer.Argument(
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            help="One or more invoice images.",
        ),
    ],
    include_raw_text: Annotated[
        bool,
        typer.Option("--include-raw-text", help="Include sensitive OCR text in JSON output."),
    ] = False,
) -> None:
    """Scan one or more invoice images and emit JSON."""

    results = []
    for path in paths:
        try:
            invoice = scan_invoice(path, source_name=path.name)
        except OCRError as exc:
            typer.echo(f"Could not scan {path}: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        if not include_raw_text:
            invoice.raw_text = None
        results.append(invoice)

    if len(results) == 1:
        typer.echo(results[0].model_dump_json(indent=2))
    else:
        typer.echo("[" + ",\n".join(result.model_dump_json(indent=2) for result in results) + "]")


@app.command("extract-text")
def extract_text(
    path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            help="UTF-8 text file produced by another OCR provider.",
        ),
    ],
) -> None:
    """Normalize and audit an existing OCR text file."""

    invoice = extract_invoice_text(path.read_text(encoding="utf-8"), source_name=path.name)
    typer.echo(invoice.model_dump_json(indent=2))


@app.command()
def demo() -> None:
    """Print a deterministic audited sample response."""

    invoice = extract_invoice_text(DEMO_INVOICE_TEXT, source_name="northstar-cloud-demo.txt")
    typer.echo(invoice.model_dump_json(indent=2))


if __name__ == "__main__":
    app()
