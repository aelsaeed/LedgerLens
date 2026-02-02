from __future__ import annotations

from datetime import date
from pydantic import BaseModel, Field


class LineItem(BaseModel):
    description: str
    quantity: int | None = None
    unit_price: float | None = None
    total: float | None = None


class InvoiceData(BaseModel):
    vendor_name: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    total_amount: float | None = None
    currency: str | None = None
    line_items: list[LineItem] = Field(default_factory=list)
    raw_text: str | None = None
    classifier_label: str | None = None
    classifier_score: float | None = None
