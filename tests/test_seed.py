"""
Tests for backend/app/database/seed.py.

The idempotency/ownership/policy tests run against the REAL seed data and are safe
to run repeatedly against your dev DB (seed_policies converges to the same set).
Password tests use a throwaway qa_seed_user via a patched SEED_USERS so the real
users' hashes are never touched.
"""
import secrets

import pytest

import app.database.seed as seed_module
from app.database.enums import Environment, Role
from app.database.models import Agent, Policy, Service, Tool, User
from app.database.seed import (
    SEED_AGENTS,
    SEED_POLICIES,
    SEED_SERVICES,
    SEED_USERS,
    UNUSABLE_PASSWORD_HASH,
    run,
    seed_users,
)
from app.gateway.auth import hash_password, is_argon2_hash, verify_password

S, P = Environment.STAGING, Environment.PRODUCTION
JR, SR, AD = Role.JUNIOR_DEVELOPER, Role.SENIOR_DEVELOPER, Role.ADMIN


def test_seed_is_idempotent_for_users(db):
    run()
    run()  # second run must not create duplicates

    for username, role in SEED_USERS:
        matches = db.query(User).filter_by(username=username).all()
        assert len(matches) == 1, f"expected exactly one {username!r}, found {len(matches)}"
        assert matches[0].role == role


def test_seed_is_idempotent_for_services(db):
    run()
    run()

    for service_name, environment, _owner_username in SEED_SERVICES:
        matches = (
            db.query(Service)
            .filter_by(service_name=service_name, environment=environment)
            .all()
        )
        assert len(matches) == 1, (
            f"expected exactly one {service_name}/{environment.value}, "
            f"found {len(matches)}"
        )


def test_seed_ownership_matches_decisions_md_8(db):
    run()

    for service_name, environment, expected_owner_username in SEED_SERVICES:
        service = (
            db.query(Service)
            .filter_by(service_name=service_name, environment=environment)
            .one()
        )
        assert service.owner.username == expected_owner_username, (
            f"{service_name}/{environment.value} expected owner "
            f"{expected_owner_username!r}, got {service.owner.username!r}"
        )


def test_seed_agent_ag001_is_idempotent(db):
    run()
    run()

    for agent_name, status in SEED_AGENTS:
        matches = db.query(Agent).filter_by(agent_name=agent_name).all()
        assert len(matches) == 1, f"expected exactly one {agent_name!r}, found {len(matches)}"
        assert matches[0].status == status


# ------------------------------------------------------------ policies (#46)
def _policy_rows(db):
    db.expire_all()
    names = {t.id: t.tool_name for t in db.query(Tool).all()}
    return {(p.role, names[p.tool_id], p.environment): p for p in db.query(Policy).all()}


def test_policy_matrix_definition_matches_decisions_46():
    assert len(SEED_POLICIES) == 25
    assert sum(1 for k in SEED_POLICIES if k[0] == JR) == 5
    assert sum(1 for k in SEED_POLICIES if k[0] == SR) == 10
    assert sum(1 for k in SEED_POLICIES if k[0] == AD) == 10
    # Only production deploy carries the approval flag.
    assert {k for k, flag in SEED_POLICIES.items() if flag} == {
        (SR, "deploy_service", P),
        (AD, "deploy_service", P),
    }


@pytest.mark.parametrize(
    "denied",
    [
        (JR, "restart_service", P),
        (JR, "rollback_deployment", S),
        (JR, "rollback_deployment", P),
        (JR, "deploy_service", S),
        (JR, "deploy_service", P),
        (SR, "deploy_service", "x"),  # sanity: nonsense keys are absent
    ],
)
def test_matrix_is_default_deny(denied):
    assert denied not in SEED_POLICIES


def test_seed_policies_match_matrix_in_the_database(db):
    run()
    rows = _policy_rows(db)

    assert set(rows) == set(SEED_POLICIES)
    for key, policy in rows.items():
        assert policy.allowed is True
        assert policy.requires_approval is SEED_POLICIES[key]
        assert policy.action == key[1]


def test_seed_policies_are_idempotent(db):
    run()
    run()
    assert db.query(Policy).count() == len(SEED_POLICIES)


def test_seed_policies_reconcile_removes_strays_and_restores_flag(db):
    run()
    deploy = db.query(Tool).filter_by(tool_name="deploy_service").one()
    db.add(
        Policy(
            role=JR,
            tool_id=deploy.id,
            environment=P,
            action="deploy_service",
            allowed=True,
            requires_approval=False,
        )
    )
    _policy_rows(db)[(SR, "deploy_service", P)].requires_approval = False
    db.commit()

    run()

    rows = _policy_rows(db)
    assert (JR, "deploy_service", P) not in rows
    assert rows[(SR, "deploy_service", P)].requires_approval is True


# ---------------------------------------------------------- passwords (#43)
QA_SEED_USER = "qa_seed_user"


@pytest.fixture
def qa_seed_user(db, monkeypatch):
    monkeypatch.setattr(seed_module, "SEED_USERS", [(QA_SEED_USER, JR)])
    db.query(User).filter_by(username=QA_SEED_USER).delete()
    db.commit()
    yield
    db.rollback()
    db.query(User).filter_by(username=QA_SEED_USER).delete()
    db.commit()


def test_new_user_without_seed_password_gets_unusable_hash(db, qa_seed_user):
    seed_users(db, None)
    db.commit()

    user = db.query(User).filter_by(username=QA_SEED_USER).one()
    assert user.hashed_password == UNUSABLE_PASSWORD_HASH
    assert verify_password("anything", user.hashed_password) is False


def test_new_user_with_seed_password_gets_argon2_hash(db, qa_seed_user):
    pw = secrets.token_urlsafe(12)
    seed_users(db, pw)
    db.commit()

    user = db.query(User).filter_by(username=QA_SEED_USER).one()
    assert is_argon2_hash(user.hashed_password)
    assert verify_password(pw, user.hashed_password)


def test_legacy_placeholder_hash_is_upgraded(db, qa_seed_user):
    db.add(User(username=QA_SEED_USER, hashed_password="phase8-not-yet-implemented", role=JR))
    db.commit()
    pw = secrets.token_urlsafe(12)

    seed_users(db, pw)
    db.commit()

    user = db.query(User).filter_by(username=QA_SEED_USER).one()
    assert is_argon2_hash(user.hashed_password)
    assert verify_password(pw, user.hashed_password)


def test_valid_argon2_hash_is_never_overwritten(db, qa_seed_user):
    original_pw = secrets.token_urlsafe(12)
    db.add(User(username=QA_SEED_USER, hashed_password=hash_password(original_pw), role=JR))
    db.commit()

    seed_users(db, secrets.token_urlsafe(12))
    db.commit()

    user = db.query(User).filter_by(username=QA_SEED_USER).one()
    assert verify_password(original_pw, user.hashed_password)


def test_seed_without_password_leaves_existing_placeholder_alone(db, qa_seed_user):
    db.add(User(username=QA_SEED_USER, hashed_password="phase8-not-yet-implemented", role=JR))
    db.commit()

    seed_users(db, None)
    db.commit()

    user = db.query(User).filter_by(username=QA_SEED_USER).one()
    assert user.hashed_password == "phase8-not-yet-implemented"