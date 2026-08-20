from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from invoice_scanner.schema import InvoiceData, LineItem


@pytest.fixture
def reconciled_invoice() -> InvoiceData:
    return InvoiceData(
        vendor_name="Northstar Cloud Ltd",
        invoice_number="LL-2026-1042",
        invoice_date=date(2026, 8, 18),
        due_date=date(2026, 9, 17),
        subtotal=Decimal("477.00"),
        tax_amount=Decimal("47.70"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("524.70"),
        currency="USD",
        line_items=[
            LineItem(
                description="Analytics workspace",
                quantity=Decimal("8"),
                unit_price=Decimal("24.00"),
                total=Decimal("192.00"),
            ),
            LineItem(
                description="Implementation support",
                quantity=Decimal("3"),
                unit_price=Decimal("95.00"),
                total=Decimal("285.00"),
            ),
        ],
    )
