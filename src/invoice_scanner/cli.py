from __future__ import annotations

from pathlib import Path

import typer
from rich import print

from invoice_scanner.pipeline import scan_invoice

app = typer.Typer(help="Scan invoices and extract data.")


@app.command()
def scan(path: Path) -> None:
    """Scan a single invoice image."""
    invoice = scan_invoice(path)
    print(invoice.model_dump())


if __name__ == "__main__":
    app()
