from __future__ import annotations

from bsap.model_protocol import (
    ActionParser,
    FinalReportAction,
    ModelProtocolError,
    ToolRequestAction,
)
from bsap.model_transport import (
    ModelMessage,
    ModelRequest,
    ModelTransport,
    ModelTransportError,
)
from bsap.models import BsapReport, ExecutorInfo, PreparedRequest
from bsap.prompting import PromptBuilder
from bsap.sandbox import ToolDispatcher


class ModelExecutor:
    def __init__(
        self,
        *,
        transport: ModelTransport,
        prompt_builder: PromptBuilder | None = None,
        action_parser: ActionParser | None = None,
    ) -> None:
        self._transport = transport
        self._prompt_builder = prompt_builder or PromptBuilder()
        self._action_parser = action_parser or ActionParser()

    @property
    def info(self) -> ExecutorInfo:
        return ExecutorInfo(
            type="model",
            version="0.2",
            transport=self._transport.transport_name,
            model=self._transport.model_name,
        )

    def execute(
        self,
        prepared: PreparedRequest,
        tools: ToolDispatcher,
        emit,
    ) -> BsapReport:
        system_prompt = self._prompt_builder.system_prompt(prepared)
        messages = list(self._prompt_builder.initial_messages(prepared))
        turn = 0

        while True:
            tools.consume_step()
            turn += 1
            emit("model.requested", {"turn": turn})

            try:
                response = self._transport.send(
                    ModelRequest(
                        system_prompt=system_prompt,
                        messages=tuple(messages),
                    )
                )
            except ModelTransportError as exc:
                emit(
                    "provider.failed",
                    {"turn": turn, "category": exc.category.value},
                )
                raise

            emit(
                "model.completed",
                {"turn": turn, "response_chars": len(response.text)},
            )
            messages.append(ModelMessage(role="assistant", content=response.text))

            try:
                action = self._action_parser.parse(
                    response.text,
                    agent_id=prepared.agent_id,
                )
            except ModelProtocolError as exc:
                emit(
                    "protocol.failed",
                    {"turn": turn, "code": exc.code},
                )
                raise

            if isinstance(action, ToolRequestAction):
                result = tools.call(action.tool, action.arguments)
                messages.append(
                    self._prompt_builder.tool_result_message(
                        action.tool,
                        action.arguments,
                        result,
                    )
                )
                continue

            if not isinstance(action, FinalReportAction):
                raise TypeError("Unsupported parsed model action")

            emit("report.started", {})
            emit(
                "report.completed",
                {"finding_count": len(action.report.findings)},
            )
            return action.report
