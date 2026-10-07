"""
Shared pytest fixtures.

Mutation tests create their OWN throwaway user + service(s) and delete them in
teardown; they never depend on seed.py and never touch the 6 seeded services.
test_seed.py is the one exception (it tests the real seed).

Phase 7 Stage 3 additions (decisions.md #33, #41):
- autouse MCP seam: random token in MCP_INTERNAL_TOKEN + get_mcp_client
  override backed by an in-process TestClient;
- `ag001_agent`: get-or-create the AG001 agent (only deleted if created here);
- `test_service_production`: a production row for the same service name;
- teardown deletes audit rows (security_requests) that reference the fixture
  user/services before deleting them (FK order).

Phase 8 Stage 2 additions (decisions.md #49, #51):
- autouse JWT_SECRET seam (random per test);
- `auth_headers(username)`: bearer header minted directly (not via login);
- `make_user(username, role)`: throwaway user with a random argon2 password,
  removed (with its audit rows) in teardown.

Phase 8 Stage 3 addition (decisions.md #49, #52):
- session-scoped autouse `seed_policies`: the Policy stage reads the real
  `policies` table; reconciling it to the matrix converges to the same set.
"""
import secrets

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import or_

from app.database.base import SessionLocal
from app.database.enums import Environment, Role
from app.database.models import Agent, SecurityRequest, Service, ServiceStateHistory, User
from app.database.seed import seed_policies
from app.gateway.auth import hash_password, issue_token
from app.gateway.mcp_client import McpClient, get_mcp_client
from app.main import app


@pytest.fixture(scope="session", autouse=True)
def _seed_policy_matrix():
    session = SessionLocal()
    try:
        seed_policies(session)  # raises a clear error if the tool registry is not seeded
        session.commit()
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _wire_mcp_seam(monkeypatch):
    token = secrets.token_hex(16)
    monkeypatch.setenv("MCP_INTERNAL_TOKEN", token)
    mcp_http = TestClient(app)
    app.dependency_overrides[get_mcp_client] = lambda: McpClient(mcp_http, token=token)
    yield token
    app.dependency_overrides.pop(get_mcp_client, None)


@pytest.fixture(autouse=True)
def _wire_jwt_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", secrets.token_hex(32))


@pytest.fixture
def auth_headers():
    """auth_headers("alice") -> {"Authorization": "Bearer <jwt for alice>"}."""

    def make(username: str) -> dict[str, str]:
        token, _ = issue_token(username)
        return {"Authorization": f"Bearer {token}"}

    return make


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()  # catch anything a test forgot to commit/clean up
        session.close()


@pytest.fixture
def make_user(db):
    created: list[str] = []

    def make(username: str, role: Role = Role.JUNIOR_DEVELOPER) -> User:
        user = User(
            username=username,
            hashed_password=hash_password(secrets.token_urlsafe(16)),
            role=role,
        )
        db.add(user)
        db.commit()
        created.append(username)
        return user

    yield make

    db.rollback()
    ids = [u.id for u in db.query(User).filter(User.username.in_(created)).all()]
    if ids:
        db.query(SecurityRequest).filter(SecurityRequest.user_id.in_(ids)).delete(
            synchronize_session=False
        )
        db.query(User).filter(User.id.in_(ids)).delete(synchronize_session=False)
        db.commit()


@pytest.fixture
def ag001_agent(db):
    agent = db.query(Agent).filter_by(agent_name="AG001").order_by(Agent.id).first()
    created = agent is None
    if created:
        agent = Agent(agent_name="AG001", status="active")
        db.add(agent)
        db.commit()
    agent_id = agent.id

    yield agent

    if created:
        db.rollback()
        db.query(SecurityRequest).filter_by(agent_id=agent_id).delete()
        db.query(Agent).filter_by(id=agent_id).delete()
        db.commit()


@pytest.fixture
def test_service(db, ag001_agent):
    """A throwaway staging service + owner (user `qa_test_owner`, role ADMIN, which is
    therefore a real, owning user for the Gateway), deleted after the test.
    The qa_ / qa- prefixes never collide with SEED_USERS / SEED_SERVICES."""
    owner = User(
        username="qa_test_owner",
        hashed_password="test-placeholder",
        role=Role.ADMIN,
    )
    db.add(owner)
    db.flush()

    service = Service(
        service_name="qa-test-service",
        environment=Environment.STAGING,
        current_version=1,
        known_good_version=1,
        owner_id=owner.id,
        status="healthy",
    )
    db.add(service)
    db.commit()
    owner_id, service_id = owner.id, service.id

    yield service

    # FK order: audit rows and history rows -> service -> owner.
    db.rollback()
    db.query(SecurityRequest).filter(
        or_(SecurityRequest.user_id == owner_id, SecurityRequest.service_id == service_id)
    ).delete(synchronize_session=False)
    db.query(ServiceStateHistory).filter_by(service_id=service_id).delete()
    db.query(Service).filter_by(id=service_id).delete()
    db.query(User).filter_by(id=owner_id).delete()
    db.commit()


@pytest.fixture
def test_service_production(db, test_service):
    """Production row for the same service name, owned by the same user, so a
    production request gets PAST the service and ownership stages."""
    prod = Service(
        service_name=test_service.service_name,
        environment=Environment.PRODUCTION,
        current_version=1,
        known_good_version=1,
        owner_id=test_service.owner_id,
        status="healthy",
    )
    db.add(prod)
    db.commit()
    prod_id = prod.id

    yield prod

    db.rollback()
    db.query(SecurityRequest).filter(SecurityRequest.service_id == prod_id).delete(
        synchronize_session=False
    )
    db.query(ServiceStateHistory).filter_by(service_id=prod_id).delete()
    db.query(Service).filter_by(id=prod_id).delete()
    db.commit()