import pytest

from bsap.models import (
    AlternativeHypothesis,
    BsapReport,
    CompletionContract,
    Evidence,
    Finding,
)
from bsap.reporting import ReportValidationError, validate_report


def valid_report() -> BsapReport:
    return BsapReport(
        agent_id="BSA-1",
        status="completed",
        findings=(Finding(id="F-1", claim="conversion is missing"),),
        evidence=(Evidence(finding_id="F-1", source="settings.py", observation="milliseconds copied into seconds field"),),
        alternative_hypotheses=(
            AlternativeHypothesis(
                claim="client converts later",
                disposition="rejected",
                basis="client consumes value directly",
            ),
        ),
        uncertainties=(),
        recommended_next_action=("fix conversion boundary",),
    )


def test_valid_report_satisfies_completion_contract() -> None:
    contract = CompletionContract(require=("findings", "evidence", "alternative_hypotheses", "uncertainties", "recommended_next_action"))
    validate_report(valid_report(), contract)


def test_evidence_free_report_is_rejected() -> None:
    report = valid_report()
    report = BsapReport(
        agent_id=report.agent_id,
        status=report.status,
        findings=report.findings,
        evidence=(),
        alternative_hypotheses=report.alternative_hypotheses,
        uncertainties=report.uncertainties,
        recommended_next_action=report.recommended_next_action,
    )
    with pytest.raises(ReportValidationError):
        validate_report(report, CompletionContract(require=("findings", "evidence")))


def test_finding_without_linked_evidence_is_rejected() -> None:
    report = valid_report()
    report = BsapReport(
        agent_id=report.agent_id,
        status=report.status,
        findings=(Finding(id="F-2", claim="different finding"),),
        evidence=report.evidence,
        alternative_hypotheses=report.alternative_hypotheses,
        uncertainties=report.uncertainties,
        recommended_next_action=report.recommended_next_action,
    )
    with pytest.raises(ReportValidationError):
        validate_report(report, CompletionContract(require=("findings", "evidence")))


def test_unknown_required_field_is_rejected() -> None:
    with pytest.raises(ReportValidationError):
        validate_report(valid_report(), CompletionContract(require=("imaginary_field",)))


def test_noncompleted_status_is_rejected() -> None:
    report = valid_report()
    report = BsapReport(
        agent_id=report.agent_id,
        status="draft",
        findings=report.findings,
        evidence=report.evidence,
        alternative_hypotheses=report.alternative_hypotheses,
        uncertainties=report.uncertainties,
        recommended_next_action=report.recommended_next_action,
    )
    with pytest.raises(ReportValidationError):
        validate_report(report, CompletionContract(require=("findings", "evidence")))
