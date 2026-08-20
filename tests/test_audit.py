from __future__ import annotations

from datetime import date
from decimal import Decimal

from invoice_scanner.audit import audit_invoice
from invoice_scanner.schema import (
    CheckStatus,
    FieldEvidence,
    InvoiceData,
    LineItem,
)


def _checks_by_code(report: object) -> dict[str, object]:
    return {check.code: check for check in report.checks}  # type: ignore[attr-defined]


def test_reconciled_invoice_passes_every_check(reconciled_invoice: InvoiceData) -> None:
    report = audit_invoice(reconciled_invoice)
    checks = _checks_by_code(report)

    assert report.score == 100
    assert report.review_required is False
    assert report.missing_fields == []
    assert {check.status for check in report.checks} == {CheckStatus.PASS}
    assert checks["SUBTOTAL_RECONCILED"].expected == Decimal("477.00")
    assert checks["TOTAL_RECONCILED"].delta == Decimal("0.00")


def test_reconciliation_allows_one_cent_and_rounds_half_up(
    reconciled_invoice: InvoiceData,
) -> None:
    reconciled_invoice.line_items[0].total = Decimal("192.009")
    reconciled_invoice.subtotal = Decimal("477.014")
    reconciled_invoice.total_amount = Decimal("524.714")

    report = audit_invoice(reconciled_invoice)

    assert all(check.status == CheckStatus.PASS for check in report.checks)


def test_mismatches_and_reversed_dates_force_manual_review(
    reconciled_invoice: InvoiceData,
) -> None:
    reconciled_invoice.line_items[0].total = Decimal("100")
    reconciled_invoice.subtotal = Decimal("500")
    reconciled_invoice.total_amount = Decimal("600")
    reconciled_invoice.due_date = date(2026, 1, 1)

    report = audit_invoice(reconciled_invoice)
    checks = _checks_by_code(report)

    assert report.review_required is True
    assert report.score == 40
    assert checks["LINE_ITEM_ARITHMETIC"].status == CheckStatus.WARNING
    assert "1 of 2" in checks["LINE_ITEM_ARITHMETIC"].message
    assert checks["SUBTOTAL_RECONCILED"].delta == Decimal("115.00")
    assert checks["TOTAL_RECONCILED"].delta == Decimal("52.30")
    assert checks["DATE_ORDER_VALID"].status == CheckStatus.WARNING


def test_missing_supporting_values_skip_checks_and_reduce_completeness() -> None:
    invoice = InvoiceData(vendor_name="Only Vendor", line_items=[LineItem(description="Unknown")])

    report = audit_invoice(invoice)

    assert report.score == 15
    assert report.review_required is True
    assert [check.status for check in report.checks] == [
        CheckStatus.WARNING,
        CheckStatus.SKIPPED,
        CheckStatus.SKIPPED,
        CheckStatus.SKIPPED,
    ]
    assert "missing quantity" in report.checks[0].message
    assert "vendor_name" not in report.missing_fields
    assert "invoice_number" in report.missing_fields


def test_calculated_line_item_subtotal_can_reconcile_total_without_declared_subtotal() -> None:
    invoice = InvoiceData(
        vendor_name="Vendor",
        invoice_number="42",
        invoice_date=date(2026, 8, 20),
        total_amount=Decimal("22.00"),
        tax_amount=Decimal("2.00"),
        currency="USD",
        line_items=[
            LineItem(
                description="Work",
                quantity=Decimal("2"),
                unit_price=Decimal("10"),
                total=Decimal("20"),
            )
        ],
    )

    report = audit_invoice(invoice)
    checks = _checks_by_code(report)

    assert checks["SUBTOTAL_RECONCILED"].status == CheckStatus.SKIPPED
    assert checks["TOTAL_RECONCILED"].status == CheckStatus.PASS
    assert checks["TOTAL_RECONCILED"].expected == Decimal("22.00")


def test_evidence_confidence_affects_score_and_warning_list_is_deduplicated(
    reconciled_invoice: InvoiceData,
) -> None:
    evidence = {
        "vendor_name": FieldEvidence(source_text="Vendor", method="label", confidence=0.5),
        "total_amount": FieldEvidence(source_text="Total", method="label", confidence=1.0),
        "without_confidence": FieldEvidence(source_text="Other", method="layout"),
    }

    report = audit_invoice(
        reconciled_invoice,
        evidence=evidence,
        warnings=["Needs review", "Needs review"],
    )

    assert report.score == 88
    assert report.review_required is True
    assert report.warnings == ["Needs review"]
    assert report.evidence == evidence
