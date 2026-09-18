from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from bsap.models import (
    AlternativeHypothesis,
    BsapReport,
    Evidence,
    Finding,
)


class ModelProtocolError(ValueError):
    def __init__(self, code: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ToolRequestAction:
    tool: str
    arguments: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "arguments", MappingProxyType(dict(self.arguments)))


@dataclass(frozen=True, slots=True)
class FinalReportAction:
    report: BsapReport


_TOOL_ARGUMENTS = {
    "repository.read": ("path",),
    "repository.search": ("query",),
    "tests.run": ("name",),
}

_REPORT_KEYS = {
    "status",
    "findings",
    "evidence",
    "alternative_hypotheses",
    "uncertainties",
    "recommended_next_action",
}


def _require_exact_keys(
    value: Mapping[str, object],
    expected: set[str],
    *,
    code: str,
) -> None:
    if set(value) != expected:
        raise ModelProtocolError(code, "Model output does not match the required schema")


def _require_string(value: object, *, code: str) -> str:
    if not isinstance(value, str):
        raise ModelProtocolError(code, "Model output contains an invalid string field")
    return value


def _require_string_list(value: object, *, code: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ModelProtocolError(code, "Model output contains an invalid string list")
    return tuple(value)


def _require_object_list(value: object, *, code: str) -> list[Mapping[str, object]]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ModelProtocolError(code, "Model output contains an invalid object list")
    return list(value)


class ActionParser:
    def parse(
        self,
        text: str,
        *,
        agent_id: str,
    ) -> ToolRequestAction | FinalReportAction:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ModelProtocolError("invalid_json", "Model output is not valid JSON") from exc

        if not isinstance(payload, Mapping):
            raise ModelProtocolError("invalid_envelope", "Model output must be a JSON object")

        envelope_type = payload.get("type")
        if envelope_type == "tool_request":
            return self._parse_tool_request(payload)
        if envelope_type == "final_report":
            return self._parse_final_report(payload, agent_id=agent_id)
        raise ModelProtocolError("unknown_type", "Model output has an unknown envelope type")

    def _parse_tool_request(self, payload: Mapping[str, object]) -> ToolRequestAction:
        _require_exact_keys(
            payload,
            {"type", "tool", "arguments"},
            code="invalid_envelope",
        )
        tool = _require_string(payload["tool"], code="unknown_tool")
        expected_arguments = _TOOL_ARGUMENTS.get(tool)
        if expected_arguments is None:
            raise ModelProtocolError("unknown_tool", "Model requested an unknown tool")

        arguments = payload["arguments"]
        if not isinstance(arguments, Mapping):
            raise ModelProtocolError("invalid_arguments", "Tool arguments must be a JSON object")
        _require_exact_keys(
            arguments,
            set(expected_arguments),
            code="invalid_arguments",
        )
        normalized = {
            name: _require_string(arguments[name], code="invalid_arguments")
            for name in expected_arguments
        }
        return ToolRequestAction(tool=tool, arguments=normalized)

    def _parse_final_report(
        self,
        payload: Mapping[str, object],
        *,
        agent_id: str,
    ) -> FinalReportAction:
        _require_exact_keys(
            payload,
            {"type", "report"},
            code="invalid_envelope",
        )
        report_payload = payload["report"]
        if not isinstance(report_payload, Mapping):
            raise ModelProtocolError("invalid_report", "Final report must be a JSON object")
        _require_exact_keys(report_payload, _REPORT_KEYS, code="invalid_report")

        status = _require_string(report_payload["status"], code="invalid_report")
        findings = tuple(
            self._parse_finding(item)
            for item in _require_object_list(
                report_payload["findings"],
                code="invalid_report",
            )
        )
        evidence = tuple(
            self._parse_evidence(item)
            for item in _require_object_list(
                report_payload["evidence"],
                code="invalid_report",
            )
        )
        alternatives = tuple(
            self._parse_alternative(item)
            for item in _require_object_list(
                report_payload["alternative_hypotheses"],
                code="invalid_report",
            )
        )
        uncertainties = _require_string_list(
            report_payload["uncertainties"],
            code="invalid_report",
        )
        recommended = _require_string_list(
            report_payload["recommended_next_action"],
            code="invalid_report",
        )

        return FinalReportAction(
            report=BsapReport(
                agent_id=agent_id,
                status=status,
                findings=findings,
                evidence=evidence,
                alternative_hypotheses=alternatives,
                uncertainties=uncertainties,
                recommended_next_action=recommended,
            )
        )

    @staticmethod
    def _parse_finding(item: Mapping[str, object]) -> Finding:
        _require_exact_keys(item, {"id", "claim"}, code="invalid_report")
        return Finding(
            id=_require_string(item["id"], code="invalid_report"),
            claim=_require_string(item["claim"], code="invalid_report"),
        )

    @staticmethod
    def _parse_evidence(item: Mapping[str, object]) -> Evidence:
        _require_exact_keys(
            item,
            {"finding_id", "source", "observation"},
            code="invalid_report",
        )
        return Evidence(
            finding_id=_require_string(item["finding_id"], code="invalid_report"),
            source=_require_string(item["source"], code="invalid_report"),
            observation=_require_string(item["observation"], code="invalid_report"),
        )

    @staticmethod
    def _parse_alternative(item: Mapping[str, object]) -> AlternativeHypothesis:
        _require_exact_keys(
            item,
            {"claim", "disposition", "basis"},
            code="invalid_report",
        )
        return AlternativeHypothesis(
            claim=_require_string(item["claim"], code="invalid_report"),
            disposition=_require_string(item["disposition"], code="invalid_report"),
            basis=_require_string(item["basis"], code="invalid_report"),
        )
