"""
Autonomous DevOps agent (Section 6/7; decisions.md #19-#23, #26-#30).

The agent PROPOSES a structured tool request and submits it to the Gateway
through GatewayClient. It never imports MCP and never decides anything.
"""
import json
import logging
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from app.agent.gateway_client import GatewayClient, GatewayResponse
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.tools import build_tool_specs

logger = logging.getLogger(__name__)

AGENT_ID = "AG001"  # decisions.md #19
MAX_HISTORY_MESSAGES = 20  # decisions.md #29


class AgentLLMError(Exception):
    """An LLM call failed (rate limit, network, ...)."""


@dataclass(frozen=True)
class AgentReply:
    reply: str
    tool_request: dict[str, Any] | None = None
    decision: str | None = None


def _text(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content.strip()
    parts = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "".join(parts).strip()


def _relay_non_allow(gw: GatewayResponse) -> str:
    """decisions.md #23/#27: Gateway's own words, no LLM involved."""
    if gw.status_code == 200:
        return f"The Security Gateway returned {gw.body.get('decision')}: {gw.body.get('reason')}"
    return (
        f"The Security Gateway could not process the request "
        f"(HTTP {gw.status_code}): {gw.body.get('detail')}"
    )


class DevOpsAgent:
    def __init__(self, llm: Any, gateway: GatewayClient):
        self._llm = llm.bind_tools(build_tool_specs())
        self._gateway = gateway
        self._history: dict[str, list[BaseMessage]] = {}

    # ------------------------------------------------------------------
    def handle_message(self, *, user_id: str, request_id: str, message: str) -> AgentReply:
        history = self._history.get(user_id, [])
        messages: list[BaseMessage] = [
            SystemMessage(content=SYSTEM_PROMPT),
            *history,
            HumanMessage(content=message),
        ]
        ai = self._invoke(messages)  # AgentLLMError propagates: nothing executed yet

        if not ai.tool_calls:
            reply = _text(ai) or "(no response)"
            self._remember(user_id, message, reply)
            return AgentReply(reply=reply)

        call = ai.tool_calls[0]
        dropped = len(ai.tool_calls) - 1
        tool_request = {
            "request_id": request_id,
            "user_id": user_id,
            "agent_id": AGENT_ID,
            "tool": call["name"],
            "arguments": call["args"],
        }
        gw = self._gateway.submit(tool_request)

        decision = gw.body.get("decision") if gw.status_code == 200 else None
        if decision == "ALLOW":
            reply = self._summarize_allowed(messages, call, gw)
        else:
            reply = _relay_non_allow(gw)

        if dropped:
            reply += (
                f"\n\n(Note: I proposed {dropped + 1} actions but only one is "
                f"submitted per message; the other {dropped} was not sent.)"
            )

        self._remember(user_id, message, reply)
        return AgentReply(reply=reply, tool_request=tool_request, decision=decision)

    # ------------------------------------------------------------------
    def _summarize_allowed(self, messages: list[BaseMessage], call: Any, gw: GatewayResponse) -> str:
        proposal = AIMessage(content="", tool_calls=[call])
        tool_msg = ToolMessage(
            content=json.dumps(gw.body.get("result"), default=str),
            tool_call_id=call.get("id") or "call_0",
            name=call["name"],
        )
        try:
            final = self._invoke([*messages, proposal, tool_msg])
        except AgentLLMError:
            # The tool already ran (#27): never surface a 5xx here.
            logger.exception("LLM summary failed after an ALLOWED execution")
            return (
                "The Security Gateway ALLOWED this request and the tool was "
                "executed, but I could not generate a summary of the result "
                "(the language model call failed)."
            )
        if final.tool_calls:
            logger.warning("Ignoring tool call(s) in post-result response: %s", final.tool_calls)
        return _text(final) or "The Security Gateway ALLOWED this request and the tool was executed."

    def _invoke(self, messages: list[BaseMessage]) -> AIMessage:
        try:
            return self._llm.invoke(messages)
        except Exception as exc:  # noqa: BLE001 - any provider error is an LLM failure
            raise AgentLLMError(str(exc)) from exc

    def _remember(self, user_id: str, human_text: str, reply: str) -> None:
        history = self._history.setdefault(user_id, [])
        history.extend([HumanMessage(content=human_text), AIMessage(content=reply)])
        del history[:-MAX_HISTORY_MESSAGES]