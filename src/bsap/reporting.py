from __future__ import annotations

from bsap.models import BsapReport, CompletionContract


class ReportValidationError(ValueError):
    pass


_ALLOWED_FIELDS = {
    "findings",
    "evidence",
    "alternative_hypotheses",
    "uncertainties",
    "recommended_next_action",
}


def validate_report(report: BsapReport, contract: CompletionContract) -> None:
    if report.status != "completed":
        raise ReportValidationError("Report status must be completed")

    for field_name in contract.require:
        if field_name not in _ALLOWED_FIELDS:
            raise ReportValidationError(f"Unknown completion-contract field: {field_name}")
        value = getattr(report, field_name)
        if field_name != "uncertainties" and not value:
            raise ReportValidationError(f"Required report field is empty: {field_name}")

    evidence_by_finding = {evidence.finding_id for evidence in report.evidence}
    missing = [finding.id for finding in report.findings if finding.id not in evidence_by_finding]
    if missing:
        raise ReportValidationError(
            "Every finding requires linked evidence; missing: " + ", ".join(missing)
        )
