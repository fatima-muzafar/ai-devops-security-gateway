"""
Phase 6: POST /api/chat end-to-end through the real Phase 5 Gateway
skeleton. The LLM is scripted (decisions.md #24) -- no Gemini calls.

The agent's GatewayClient is backed by an in-process TestClient(app), so
chat -> agent -> HTTP -> /api/gateway/tool-request -> execute_tool -> DB
is the real path.
"""
import re

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import Field

from app.agent.devops_agent import DevOpsAgent
from app.agent.gateway_client import GatewayClient
from app.agent.tools import build_tool_specs
from app.api.chat import get_agent
from app.database.models import ServiceStateHistory
from app.main import app
from app.mcp.schemas import TOOL_ARG_SCHEMAS


class ScriptedToolCallingLLM(GenericFakeChatModel):
    """Fake chat model: returns scripted AIMessages in order, records the
    messages it was shown. bind_tools is a no-op (the base fake raises)."""

    seen: list = Field(default_factory=list)

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(list(messages))
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def tool_call_msg(name, **args):
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": "call_1", "type": "tool_call"}],
    )


@pytest.fixture
def make_chat():
    def make(script):
        llm = ScriptedToolCallingLLM(messages=iter(script))
        agent = DevOpsAgent(llm, GatewayClient(TestClient(app)))
        app.dependency_overrides[get_agent] = lambda: agent
        return TestClient(app), llm

    yield make
    app.dependency_overrides.clear()


def history_count(db, service_id, change_type=None):
    q = db.query(ServiceStateHistory).filter_by(service_id=service_id)
    if change_type is not None:
        q = q.filter_by(change_type=change_type)
    return q.count()


def post(client, message, user_id="qa_test_owner"):
    return client.post("/api/chat", json={"user_id": user_id, "message": message})


# ---------------------------------------------------------------- tool specs
def test_tool_specs_cover_all_five_tools_and_have_no_refs():
    specs = build_tool_specs()
    assert {s["name"] for s in specs} == set(TOOL_ARG_SCHEMAS)
    assert len(specs) == 5
    assert "$ref" not in str(specs) and "$defs" not in str(specs)


# ------------------------------------------------------------ restart_service
def test_restart_staging_is_allowed_and_changes_state(db, test_service, make_chat):
    client, _ = make_chat(
        [
            tool_call_msg("restart_service", service_name=test_service.service_name, environment="staging"),
            AIMessage(content="Restarted qa-test-service in staging."),
        ]
    )
    before = history_count(db, test_service.id, "restart")

    res = post(client, "Restart qa-test-service in staging")

    assert res.status_code == 200
    body = res.json()
    assert body["decision"] == "ALLOW"
    assert body["reply"] == "Restarted qa-test-service in staging."
    assert body["tool_request"]["tool"] == "restart_service"
    assert body["tool_request"]["agent_id"] == "AG001"
    assert body["tool_request"]["user_id"] == "qa_test_owner"
    assert re.fullmatch(r"[0-9a-f]{32}", body["request_id"])
    assert body["tool_request"]["request_id"] == body["request_id"]
    assert history_count(db, test_service.id, "restart") == before + 1


def test_restart_production_is_blocked_and_reason_relayed_verbatim(db, test_service, make_chat):
    # Only ONE scripted message: a second LLM call on a BLOCK would raise.
    client, _ = make_chat(
        [tool_call_msg("restart_service", service_name=test_service.service_name, environment="production")]
    )
    before = history_count(db, test_service.id)

    res = post(client, "Restart qa-test-service in production")

    assert res.status_code == 200
    body = res.json()
    assert body["decision"] == "BLOCK"
    # Replay the same request straight at the Gateway (BLOCK is side-effect
    # free) and require its reason verbatim -- not coupled to Phase 5 wording.
    expected = TestClient(app).post("/api/gateway/tool-request", json=body["tool_request"]).json()["reason"]
    assert expected in body["reply"]
    assert history_count(db, test_service.id) == before


# ------------------------------------------------------------------- get_logs
def test_get_logs_staging_is_allowed_without_state_change(db, test_service, make_chat):
    client, _ = make_chat(
        [
            tool_call_msg("get_logs", service_name=test_service.service_name, environment="staging"),
            AIMessage(content="Here are the latest logs."),
        ]
    )
    before = history_count(db, test_service.id)

    res = post(client, "Show me the logs for qa-test-service in staging")

    assert res.status_code == 200
    body = res.json()
    assert body["decision"] == "ALLOW"
    assert body["tool_request"]["tool"] == "get_logs"
    assert body["reply"] == "Here are the latest logs."
    assert history_count(db, test_service.id) == before  # read-only


# ------------------------------------------------------------ agent behaviour
def test_chitchat_makes_no_tool_request(db, test_service, make_chat):
    client, _ = make_chat([AIMessage(content="I can restart, roll back and deploy services.")])
    before = history_count(db, test_service.id)

    body = post(client, "What can you do?").json()

    assert body["tool_request"] is None and body["decision"] is None
    assert body["reply"].startswith("I can restart")
    assert history_count(db, test_service.id) == before


def test_only_first_of_several_tool_calls_is_submitted(db, test_service, make_chat):
    args = {"service_name": test_service.service_name, "environment": "staging"}
    two_calls = AIMessage(
        content="",
        tool_calls=[
            {"name": "restart_service", "args": args, "id": "c1", "type": "tool_call"},
            {"name": "restart_service", "args": args, "id": "c2", "type": "tool_call"},
        ],
    )
    client, _ = make_chat([two_calls, AIMessage(content="Restarted.")])
    before = history_count(db, test_service.id, "restart")

    body = post(client, "Restart it twice").json()

    assert history_count(db, test_service.id, "restart") == before + 1
    assert "only one is submitted" in body["reply"]


def test_gateway_http_error_is_relayed_without_second_llm_call(db, test_service, make_chat):
    # LLM omits `environment` -> Gateway 422 -> relayed; one scripted message only.
    client, _ = make_chat([tool_call_msg("restart_service", service_name=test_service.service_name)])

    body = post(client, "Restart qa-test-service").json()

    assert body["decision"] is None
    assert "HTTP 422" in body["reply"]


def test_history_is_kept_per_user(make_chat):
    client, llm = make_chat([AIMessage(content="first reply"), AIMessage(content="second reply")])

    post(client, "first", user_id="qa_a")
    post(client, "second", user_id="qa_a")

    shown = [m.content for m in llm.seen[1]]
    assert "first" in shown and "first reply" in shown and "second" in shown


# ------------------------------------------------------------ LLM failure paths
def test_llm_failure_before_execution_returns_502(db, test_service, make_chat):
    def boom():
        raise RuntimeError("429 quota exceeded")
        yield  # pragma: no cover

    client, _ = make_chat(boom())
    before = history_count(db, test_service.id)

    res = post(client, "Restart qa-test-service in staging")

    assert res.status_code == 502
    assert "Nothing was executed" in res.json()["detail"]
    assert history_count(db, test_service.id) == before


def test_llm_failure_after_allow_still_reports_execution(db, test_service, make_chat):
    def script():
        yield tool_call_msg("restart_service", service_name=test_service.service_name, environment="staging")
        raise RuntimeError("429 quota exceeded")

    client, _ = make_chat(script())
    before = history_count(db, test_service.id, "restart")

    res = post(client, "Restart qa-test-service in staging")

    assert res.status_code == 200  # never 5xx after a state change: avoids retries
    body = res.json()
    assert body["decision"] == "ALLOW"
    assert "executed" in body["reply"]
    assert history_count(db, test_service.id, "restart") == before + 1