"""
Tests for backend/app/database/seed.py.

Unlike the other two test files, this one runs against the REAL seed
data (SEED_USERS / SEED_SERVICES) rather than throwaway rows — testing
idempotency of the actual seed script against real data is the point.
Safe to run repeatedly against your dev DB.
"""
from app.database.models import Service, User
from app.database.seed import SEED_SERVICES, SEED_USERS, run


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