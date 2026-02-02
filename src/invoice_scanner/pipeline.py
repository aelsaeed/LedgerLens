from __future__ import annotations

from pathlib import Path

import torch

from invoice_scanner.config import settings
from invoice_scanner.extraction import extract_fields
from invoice_scanner.ocr import OCRError, extract_text
from invoice_scanner.schema import InvoiceData


class ClassifierNotAvailable(RuntimeError):
    pass


def scan_invoice(image_path: Path) -> InvoiceData:
    try:
        text = extract_text(image_path)
    except OCRError:
        text = ""

    invoice = extract_fields(text)
    _maybe_enrich_with_classifier(invoice)
    return invoice


def _maybe_enrich_with_classifier(invoice: InvoiceData) -> None:
    if not invoice.vendor_name:
        return

    model_path = Path(settings.model_path)
    if not model_path.exists():
        return

    checkpoint = torch.load(model_path, map_location=settings.device)
    vocab = checkpoint["vocab"]
    vector = torch.zeros(len(vocab))
    token = invoice.vendor_name.split()[0].lower()
    if token in vocab:
        vector[vocab[token]] = 1.0

    from invoice_scanner.training import VendorClassifier

    model = VendorClassifier(input_dim=len(vocab), num_classes=3)
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()

    with torch.no_grad():
        logits = model(vector)
        probs = torch.softmax(logits, dim=0)
        label_idx = int(torch.argmax(probs).item())
        invoice.classifier_label = f"vendor_{label_idx}"
        invoice.classifier_score = float(probs[label_idx].item())
