"""
Shared pytest fixtures for Phase 3 tests.

Design choice: mutation tests (test_deploy.py, test_restart_rollback.py)
create their OWN throwaway user + service per test and delete both in
teardown. They never depend on `seed.py` having been run, and they never
touch the real 6 seeded services — so running these tests can never
corrupt or duplicate real project data.

test_seed.py is the one exception: it deliberately runs against the real
seed script and real seed data, because testing that idempotency is the
whole point of that file.
"""
import pytest

from app.database.base import SessionLocal
from app.database.enums import Environment, Role
from app.database.models import Service, ServiceStateHistory, User


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()  # catch anything a test forgot to commit/clean up
        session.close()


@pytest.fixture
def test_service(db):
    """A throwaway service + owner, deleted after the test. The username
    and service_name are prefixed qa_ / qa- specifically because
    SEED_USERS / SEED_SERVICES never use that prefix — guarantees no
    collision with real seed data even if seed.py has already run."""
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

    yield service

    # Teardown order matters: history rows reference service_id (FK),
    # service references owner_id (FK) — delete children before parents.
    db.query(ServiceStateHistory).filter_by(service_id=service.id).delete()
    db.delete(service)
    db.delete(owner)
    db.commit()