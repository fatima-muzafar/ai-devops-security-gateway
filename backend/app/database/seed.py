"""
Phase 3 seed script: creates the fixed set of users and services required
by the mock DevOps environment (decisions.md #8).

Run manually from backend/:
    python -m app.database.seed

Idempotent: safe to re-run. Existing rows (matched by username, or by
service_name+environment) are left untouched — never duplicated, never
overwritten.
"""
from app.database.base import SessionLocal
from app.database.enums import Environment, Role
from app.database.models import Service, User

# decisions.md #8: one owner per (service, environment) row. The planning
# doc's two-name "seeded owner example" per service is split across the
# staging/production rows, not modeled as two owners of one row.
SEED_USERS = [
    # (username, role)
    ("junior_developer_1", Role.JUNIOR_DEVELOPER),
    ("senior_developer_1", Role.SENIOR_DEVELOPER),
    ("senior_developer_2", Role.SENIOR_DEVELOPER),
    ("admin", Role.ADMIN),
]

SEED_SERVICES = [
    # (service_name, environment, owner_username)
    ("auth-service", Environment.STAGING, "senior_developer_1"),
    ("auth-service", Environment.PRODUCTION, "admin"),
    ("payment-service", Environment.STAGING, "senior_developer_2"),
    ("payment-service", Environment.PRODUCTION, "admin"),
    ("notification-service", Environment.STAGING, "junior_developer_1"),
    ("notification-service", Environment.PRODUCTION, "senior_developer_1"),
]

# Phase 8 (Authentication) replaces this with real password hashing.
# Phase 3 has no auth logic at all — this is a placeholder value, never
# a real hash, and must not be treated as one anywhere downstream.
PLACEHOLDER_HASHED_PASSWORD = "phase8-not-yet-implemented"


def seed_users(db) -> dict[str, User]:
    users_by_username: dict[str, User] = {}
    for username, role in SEED_USERS:
        existing = db.query(User).filter_by(username=username).one_or_none()
        if existing:
            users_by_username[username] = existing
            continue
        user = User(
            username=username,
            hashed_password=PLACEHOLDER_HASHED_PASSWORD,
            role=role,
        )
        db.add(user)
        db.flush()  # populate user.id without committing yet
        users_by_username[username] = user
    return users_by_username


def seed_services(db, users_by_username: dict[str, User]) -> None:
    for service_name, environment, owner_username in SEED_SERVICES:
        existing = (
            db.query(Service)
            .filter_by(service_name=service_name, environment=environment)
            .one_or_none()
        )
        if existing:
            continue
        owner = users_by_username[owner_username]
        db.add(
            Service(
                service_name=service_name,
                environment=environment,
                current_version=1,
                known_good_version=1,
                owner_id=owner.id,
                status="healthy",
            )
        )


def run() -> None:
    db = SessionLocal()
    try:
        users_by_username = seed_users(db)
        db.commit()  # users must be committed before services reference their id
        seed_services(db, users_by_username)
        db.commit()
        print(f"Seed complete: {len(SEED_USERS)} users, {len(SEED_SERVICES)} services (idempotent).")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run()