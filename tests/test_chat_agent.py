"""
Phase 6/8: POST /api/chat end-to-end through the real Gateway pipeline. The LLM is
scripted (decisions.md #24) -- no Gemini calls.

Phase 8 Stage 2 (#44, #51): every chat call carries a bearer token; the agent forwards
it to the Gateway; identity comes from the token, never from the body.

The agent's GatewayClient is backed by an in-process TestClient(app), so
chat -> agent -> HTTP -> /api/gateway/tool-request -> execute_tool -> DB
is the real path.
"""
import re
import uuid

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from pydantic import Field

from app.agent.devops_agent import DevOpsAgent
from app.agent.gateway_client import GatewayClient
from app.agent.tools import build_tool_specs
from app.api.chat import get_agent
from app.database.models import ServiceStateHistory
from app.gateway.auth import issue_token
from app.main import app
from app.mcp.schemas import TOOL_ARG_SCHEMAS

OWNER = "qa_test_owner"


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
    app.dependency_overrides.pop(get_agent, None)


def history_count(db, service_id, change_type=None):
    q = db.query(ServiceStateHistory).filter_by(service_id=service_id)
    if change_type is not None:
        q = q.filter_by(change_type=change_type)
    return q.count()


def post(client, message, headers):
    return client.post("/api/chat", json={"message": message}, headers=headers)


# ---------------------------------------------------------------- tool specs
def test_tool_specs_cover_all_five_tools_and_have_no_refs():
    specs = build_tool_specs()
    assert {s["name"] for s in specs} == set(TOOL_ARG_SCHEMAS)
    assert len(specs) == 5
    assert "$ref" not in str(specs) and "$defs" not in str(specs)


# ------------------------------------------------------------ restart_service
def test_restart_staging_is_allowed_and_changes_state(db, test_service, make_chat, auth_headers):
    client, _ = make_chat(
        [
            tool_call_msg("restart_service", service_name=test_service.service_name, environment="staging"),
            AIMessage(content="Restarted qa-test-service in staging."),
        ]
    )
    before = history_count(db, test_service.id, "restart")

    res = post(client, "Restart qa-test-service in staging", auth_headers(OWNER))

    assert res.status_code == 200
    body = res.json()
    assert body["decision"] == "ALLOW"
    assert body["reply"] == "Restarted qa-test-service in staging."
    assert body["tool_request"]["tool"] == "restart_service"
    assert body["tool_request"]["agent_id"] == "AG001"
    assert body["tool_request"]["user_id"] == OWNER
    assert re.fullmatch(r"[0-9a-f]{32}", body["request_id"])
    assert body["tool_request"]["request_id"] == body["request_id"]
    assert history_count(db, test_service.id, "restart") == before + 1


def test_restart_production_is_blocked_and_reason_relayed_verbatim(
    db, test_service, test_service_production, make_chat, auth_headers
):
    # Only ONE scripted message: a second LLM call on a BLOCK would raise.
    client, _ = make_chat(
        [tool_call_msg("restart_service", service_name=test_service.service_name, environment="production")]
    )
    headers = auth_headers(OWNER)
    before = history_count(db, test_service_production.id)

    res = post(client, "Restart qa-test-service in production", headers)

    assert res.status_code == 200
    body = res.json()
    assert body["decision"] == "BLOCK"
    # Replay the same request at the Gateway under a NEW request_id (a reused id
    # is a 409, #36) and require its reason verbatim.
    replay = dict(body["tool_request"], request_id=uuid.uuid4().hex)
    expected = (
        TestClient(app).post("/api/gateway/tool-request", json=replay, headers=headers).json()["reason"]
    )
    assert expected in body["reply"]
    assert history_count(db, test_service_production.id) == before


# ------------------------------------------------------------------- get_logs
def test_get_logs_staging_is_allowed_without_state_change(db, test_service, make_chat, auth_headers):
    client, _ = make_chat(
        [
            tool_call_msg("get_logs", service_name=test_service.service_name, environment="staging"),
            AIMessage(content="Here are the latest logs."),
        ]
    )
    before = history_count(db, test_service.id)

    res = post(client, "Show me the logs for qa-test-service in staging", auth_headers(OWNER))

    assert res.status_code == 200
    body = res.json()
    assert body["decision"] == "ALLOW"
    assert body["tool_request"]["tool"] == "get_logs"
    assert body["reply"] == "Here are the latest logs."
    assert history_count(db, test_service.id) == before  # read-only


# ------------------------------------------------------------ agent behaviour
def test_chitchat_makes_no_tool_request(db, test_service, make_chat, auth_headers):
    client, _ = make_chat([AIMessage(content="I can restart, roll back and deploy services.")])
    before = history_count(db, test_service.id)

    body = post(client, "What can you do?", auth_headers(OWNER)).json()

    assert body["tool_request"] is None and body["decision"] is None
    assert body["reply"].startswith("I can restart")
    assert history_count(db, test_service.id) == before


def test_only_first_of_several_tool_calls_is_submitted(db, test_service, make_chat, auth_headers):
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

    body = post(client, "Restart it twice", auth_headers(OWNER)).json()

    assert history_count(db, test_service.id, "restart") == before + 1
    assert "only one is submitted" in body["reply"]


def test_gateway_block_for_missing_argument_is_relayed_without_second_llm_call(
    db, test_service, make_chat, auth_headers
):
    # LLM omits `environment` -> Gateway BLOCK (Arguments stage, #34) -> relayed
    # verbatim; one scripted message only, so a second LLM call would raise.
    client, _ = make_chat([tool_call_msg("restart_service", service_name=test_service.service_name)])

    body = post(client, "Restart qa-test-service", auth_headers(OWNER)).json()

    assert body["decision"] == "BLOCK"
    assert "Arguments stage" in body["reply"]


# ------------------------------------- Gateway HTTP errors + token forwarding
class _FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body
        self.text = str(body)

    def json(self):
        return self._body


class _FakeHttp:
    """Stands in for the Gateway transport; records the headers it was sent."""

    def __init__(self, status_code, body):
        self._response = _FakeResponse(status_code, body)
        self.last_headers = None

    def post(self, path, json=None, headers=None):
        self.last_headers = headers
        return self._response


@pytest.mark.parametrize(
    "status, detail",
    [
        (422, "unprocessable"),
        (502, "MCP execution failed (HTTP 500): boom"),
        (409, "request_id 'x' already exists; the original request is unchanged."),
    ],
)
def test_gateway_http_error_is_relayed_without_second_llm_call_and_token_is_forwarded(
    test_service, make_chat, auth_headers, status, detail
):
    # The Gateway now BLOCKs most bad input, so real HTTP errors (422/409/502) are
    # simulated with a fake transport (#27). One scripted message only.
    client, llm = make_chat(
        [tool_call_msg("restart_service", service_name=test_service.service_name, environment="staging")]
    )
    fake = _FakeHttp(status, {"detail": detail})
    agent = DevOpsAgent(llm, GatewayClient(fake))
    app.dependency_overrides[get_agent] = lambda: agent  # make_chat teardown clears it
    headers = auth_headers(OWNER)

    res = post(client, "Restart qa-test-service in staging", headers)

    assert res.status_code == 200
    body = res.json()
    assert body["decision"] is None
    assert f"HTTP {status}" in body["reply"]
    assert detail in body["reply"]
    assert fake.last_headers == headers  # the caller's token reached the Gateway client


# ------------------------------------------------------------------- history
def test_history_is_kept_per_user(make_chat, make_user, auth_headers):
    make_user("qa_a")
    client, llm = make_chat([AIMessage(content="first reply"), AIMessage(content="second reply")])
    headers = auth_headers("qa_a")

    post(client, "first", headers)
    post(client, "second", headers)

    shown = [m.content for m in llm.seen[1]]
    assert "first" in shown and "first reply" in shown and "second" in shown


def test_history_is_not_shared_between_users(make_chat, make_user, auth_headers):
    make_user("qa_a")
    make_user("qa_b")
    client, llm = make_chat([AIMessage(content="reply a"), AIMessage(content="reply b")])

    post(client, "private-a-message", auth_headers("qa_a"))
    post(client, "hello from b", auth_headers("qa_b"))

    shown_to_b = [m.content for m in llm.seen[1]]
    assert "hello from b" in shown_to_b
    assert "private-a-message" not in shown_to_b and "reply a" not in shown_to_b


# ------------------------------------------------------------ LLM failure paths
def test_llm_failure_before_execution_returns_502(db, test_service, make_chat, auth_headers):
    def boom():
        raise RuntimeError("429 quota exceeded")
        yield  # pragma: no cover

    client, _ = make_chat(boom())
    before = history_count(db, test_service.id)

    res = post(client, "Restart qa-test-service in staging", auth_headers(OWNER))

    assert res.status_code == 502
    assert "Nothing was executed" in res.json()["detail"]
    assert history_count(db, test_service.id) == before


def test_llm_failure_after_allow_still_reports_execution(db, test_service, make_chat, auth_headers):
    def script():
        yield tool_call_msg("restart_service", service_name=test_service.service_name, environment="staging")
        raise RuntimeError("429 quota exceeded")

    client, _ = make_chat(script())
    before = history_count(db, test_service.id, "restart")

    res = post(client, "Restart qa-test-service in staging", auth_headers(OWNER))

    assert res.status_code == 200  # never 5xx after a state change: avoids retries
    body = res.json()
    assert body["decision"] == "ALLOW"
    assert "executed" in body["reply"]
    assert history_count(db, test_service.id, "restart") == before + 1


# ------------------------------------------------ authentication on /api/chat
def _bad_headers(kind):
    if kind == "missing":
        return {}
    if kind == "wrong-scheme":
        return {"Authorization": f"Basic {issue_token('qa_chat_user')[0]}"}
    if kind == "garbage":
        return {"Authorization": "Bearer not.a.jwt"}
    if kind == "expired":
        return {"Authorization": f"Bearer {issue_token('qa_chat_user', ttl_seconds=-10)[0]}"}
    if kind == "unknown-subject":
        return {"Authorization": f"Bearer {issue_token('qa_no_such_user')[0]}"}
    raise AssertionError(kind)


@pytest.mark.parametrize("kind", ["missing", "wrong-scheme", "garbage", "expired", "unknown-subject"])
def test_chat_rejects_bad_credentials_without_calling_the_llm(make_user, make_chat, kind):
    make_user("qa_chat_user")
    client, llm = make_chat([])  # an LLM call would raise -> 502, not 401

    res = client.post("/api/chat", json={"message": "hi"}, headers=_bad_headers(kind))

    assert res.status_code == 401
    assert res.json() == {"detail": "Not authenticated."}
    assert llm.seen == []


def test_chat_with_unconfigured_secret_is_503(make_user, make_chat, auth_headers, monkeypatch):
    make_user("qa_chat_user")
    headers = auth_headers("qa_chat_user")
    monkeypatch.setenv("JWT_SECRET", "changeme")
    client, llm = make_chat([])

    res = client.post("/api/chat", json={"message": "hi"}, headers=headers)

    assert res.status_code == 503
    assert llm.seen == []


def test_user_id_in_the_chat_body_is_ignored(test_service, make_user, make_chat, auth_headers):
    make_user("qa_other")
    client, _ = make_chat(
        [
            tool_call_msg("restart_service", service_name=test_service.service_name, environment="staging"),
            AIMessage(content="done"),
        ]
    )

    res = client.post(
        "/api/chat",
        json={"message": "Restart it", "user_id": "qa_other"},  # spoof attempt
        headers=auth_headers(OWNER),
    )

    assert res.status_code == 200
    assert res.json()["tool_request"]["user_id"] == OWNER


def test_token_never_reaches_the_llm_or_the_reply(test_service, make_chat, auth_headers):
    headers = auth_headers(OWNER)
    token = headers["Authorization"].split(" ", 1)[1]
    client, llm = make_chat(
        [
            tool_call_msg("get_logs", service_name=test_service.service_name, environment="staging"),
            AIMessage(content="Here are the logs."),
        ]
    )

    res = post(client, "Show logs", headers)

    assert res.status_code == 200
    assert token not in res.text
    assert token not in str(llm.seen)