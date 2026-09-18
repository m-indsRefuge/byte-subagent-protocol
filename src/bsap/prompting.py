from __future__ import annotations

from collections.abc import Mapping

from bsap.canonical import canonical_json
from bsap.model_transport import ModelMessage
from bsap.models import PreparedRequest


class PromptBuilder:
    def system_prompt(self, prepared: PreparedRequest) -> str:
        return (
            "You are a bounded BSAP investigator. "
            "Use only these governed tools: repository.read(path), "
            "repository.search(query), tests.run(name). "
            "You cannot write files, cannot access the network, cannot invoke providers, "
            "and cannot spawn agents. "
            "Do not reveal hidden reasoning. "
            "Return exactly one JSON object per turn and no surrounding prose. "
            'For a tool request use {"type":"tool_request","tool":"<approved tool>",'
            '"arguments":{...}}. '
            'For completion use {"type":"final_report","report":{'
            '"status":"completed","findings":[],"evidence":[],'
            '"alternative_hypotheses":[],"uncertainties":[],'
            '"recommended_next_action":[]}}. '
            "Stop when sufficient evidence supports a report that satisfies the completion "
            "contract. If evidence is insufficient, state that uncertainty instead of inventing facts."
        )

    def initial_messages(self, prepared: PreparedRequest) -> tuple[ModelMessage, ...]:
        payload = {
            "role": prepared.role,
            "objective": prepared.objective,
            "delegation_reason": prepared.delegation_reason,
            "context_manifest": prepared.context_manifest,
            "permissions": prepared.permissions,
            "budget": prepared.budget,
            "completion_contract": prepared.completion_contract,
        }
        return (ModelMessage(role="user", content=canonical_json(payload)),)

    def tool_result_message(
        self,
        tool: str,
        arguments: Mapping[str, object],
        result: Mapping[str, object],
    ) -> ModelMessage:
        return ModelMessage(
            role="user",
            content=canonical_json(
                {
                    "type": "tool_result",
                    "tool": tool,
                    "arguments": arguments,
                    "result": result,
                }
            ),
        )
