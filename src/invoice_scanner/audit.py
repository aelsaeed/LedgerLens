"""Deterministic invoice validation and review scoring."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from statistics import fmean

from invoice_scanner.schema import (
    AuditCheck,
    CheckStatus,
    FieldEvidence,
    InvoiceData,
    QualityReport,
)

CENT = Decimal("0.01")
TOLERANCE = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _reconciliation_check(
    *,
    code: str,
    label: str,
    expected: Decimal | None,
    actual: Decimal | None,
) -> AuditCheck:
    if expected is None or actual is None:
        return AuditCheck(
            code=code,
            status=CheckStatus.SKIPPED,
            message=f"{label} could not be checked because supporting values are missing.",
        )

    expected = _money(expected)
    actual = _money(actual)
    delta = _money(actual - expected)
    if abs(delta) <= TOLERANCE:
        return AuditCheck(
            code=code,
            status=CheckStatus.PASS,
            message=f"{label} reconciles within {TOLERANCE}.",
            expected=expected,
            actual=actual,
            delta=delta,
        )
    return AuditCheck(
        code=code,
        status=CheckStatus.WARNING,
        message=f"{label} differs by {delta}.",
        expected=expected,
        actual=actual,
        delta=delta,
    )


def _line_item_arithmetic(invoice: InvoiceData) -> AuditCheck:
    testable = [
        item
        for item in invoice.line_items
        if item.quantity is not None and item.unit_price is not None and item.total is not None
    ]
    if not invoice.line_items:
        return AuditCheck(
            code="LINE_ITEM_ARITHMETIC",
            status=CheckStatus.SKIPPED,
            message="No line items were available for arithmetic checks.",
        )
    if len(testable) != len(invoice.line_items):
        missing_count = len(invoice.line_items) - len(testable)
        return AuditCheck(
            code="LINE_ITEM_ARITHMETIC",
            status=CheckStatus.WARNING,
            message=(
                f"{missing_count} of {len(invoice.line_items)} line items "
                f"{'is' if missing_count == 1 else 'are'} missing quantity, unit price, or total."
            ),
        )

    mismatches = [
        item
        for item in testable
        if abs(_money(item.quantity * item.unit_price) - _money(item.total)) > TOLERANCE
    ]
    if mismatches:
        return AuditCheck(
            code="LINE_ITEM_ARITHMETIC",
            status=CheckStatus.WARNING,
            message=f"{len(mismatches)} of {len(testable)} line items do not reconcile.",
        )
    return AuditCheck(
        code="LINE_ITEM_ARITHMETIC",
        status=CheckStatus.PASS,
        message=f"All {len(testable)} testable line items reconcile.",
    )


def _date_order(invoice: InvoiceData) -> AuditCheck:
    if invoice.invoice_date is None or invoice.due_date is None:
        return AuditCheck(
            code="DATE_ORDER_VALID",
            status=CheckStatus.SKIPPED,
            message="Date order could not be checked.",
        )
    if invoice.due_date >= invoice.invoice_date:
        return AuditCheck(
            code="DATE_ORDER_VALID",
            status=CheckStatus.PASS,
            message="The due date is on or after the invoice date.",
        )
    return AuditCheck(
        code="DATE_ORDER_VALID",
        status=CheckStatus.WARNING,
        message="The due date is before the invoice date.",
    )


def audit_invoice(
    invoice: InvoiceData,
    *,
    evidence: dict[str, FieldEvidence] | None = None,
    warnings: list[str] | None = None,
) -> QualityReport:
    """Build a transparent automation-readiness report for an invoice."""

    evidence = evidence or {}
    report_warnings = list(dict.fromkeys(warnings or []))
    required_fields = ("vendor_name", "invoice_number", "invoice_date", "total_amount", "currency")
    missing_fields = [field for field in required_fields if getattr(invoice, field) is None]

    item_totals = [item.total for item in invoice.line_items if item.total is not None]
    calculated_subtotal = (
        sum(item_totals, Decimal("0"))
        if invoice.line_items and len(item_totals) == len(invoice.line_items)
        else None
    )
    subtotal_check = _reconciliation_check(
        code="SUBTOTAL_RECONCILED",
        label="Declared subtotal versus line items",
        expected=calculated_subtotal,
        actual=invoice.subtotal,
    )

    total_base = invoice.subtotal if invoice.subtotal is not None else calculated_subtotal
    calculated_total = None
    if total_base is not None:
        calculated_total = (
            total_base
            + (invoice.tax_amount or Decimal("0"))
            - (invoice.discount_amount or Decimal("0"))
        )
    total_check = _reconciliation_check(
        code="TOTAL_RECONCILED",
        label="Grand total versus subtotal, tax, and discount",
        expected=calculated_total,
        actual=invoice.total_amount,
    )
    checks = [_line_item_arithmetic(invoice), subtotal_check, total_check, _date_order(invoice)]

    weights = {
        "vendor_name": 15,
        "invoice_number": 15,
        "invoice_date": 10,
        "due_date": 5,
        "subtotal": 5,
        "total_amount": 25,
        "currency": 10,
        "line_items": 15,
    }
    completeness = sum(
        weight
        for field, weight in weights.items()
        if (value := getattr(invoice, field)) is not None and value != []
    )
    confidences = [item.confidence for item in evidence.values() if item.confidence is not None]
    score = float(completeness)
    if confidences:
        score = (score * 0.7) + (fmean(confidences) * 100 * 0.3)

    warning_checks = [check for check in checks if check.status == CheckStatus.WARNING]
    score -= len(warning_checks) * 15
    score -= len(report_warnings) * 5
    score = max(0, min(100, round(score)))
    review_required = bool(missing_fields or warning_checks or report_warnings or score < 75)

    return QualityReport(
        score=score,
        review_required=review_required,
        missing_fields=missing_fields,
        warnings=report_warnings,
        checks=checks,
        evidence=evidence,
    )
