"""
Seed script (decisions.md #8, #33, #43, #46, #50).

Run manually from backend/:
    python -m app.database.seed

Idempotent: safe to re-run.
- Users/services/agents: existing rows are never duplicated. A user's password
  hash is replaced ONLY when it is not already an argon2 hash and
  SEED_USER_PASSWORD is set (#43); valid argon2 hashes are never overwritten.
- Policies: RECONCILED to SEED_POLICIES (#46): missing rows inserted, flags
  updated, rows outside the matrix deleted. Requires the tool registry to be seeded.
"""
import os

from app.database.base import SessionLocal
from app.database.enums import Environment, Role
from app.database.models import Agent, Policy, Service, Tool, User
from app.gateway.auth import hash_password, is_argon2_hash

SEED_PASSWORD_ENV = "SEED_USER_PASSWORD"
# Not an argon2 hash, so login is impossible until the seed is re-run with
# SEED_USER_PASSWORD set (which then upgrades it).
UNUSABLE_PASSWORD_HASH = "!unusable"

# decisions.md #8: one owner per (service, environment) row.
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

SEED_AGENTS = [
    # (agent_name, status) -- decisions.md #33. agents.agent_name has no
    # UNIQUE constraint, so lookups use .first(), not .one_or_none().
    ("AG001", "active"),
]


def _build_policies() -> dict[tuple[Role, str, Environment], bool]:
    """decisions.md #46. Key = (role, tool_name, environment); value =
    requires_approval. Default-deny: a missing key means the action is not permitted.
    Only production deploy carries the approval flag."""
    s, p = Environment.STAGING, Environment.PRODUCTION
    matrix: dict[tuple[Role, str, Environment], bool] = {}

    def permit(role: Role, tool: str, envs: tuple[Environment, ...], approval: bool = False) -> None:
        for env in envs:
            matrix[(role, tool, env)] = approval

    for role in (Role.JUNIOR_DEVELOPER, Role.SENIOR_DEVELOPER, Role.ADMIN):
        permit(role, "get_logs", (s, p))
        permit(role, "get_metrics", (s, p))
    permit(Role.JUNIOR_DEVELOPER, "restart_service", (s,))
    for role in (Role.SENIOR_DEVELOPER, Role.ADMIN):
        permit(role, "restart_service", (s, p))
        permit(role, "rollback_deployment", (s, p))
        permit(role, "deploy_service", (s,))
        permit(role, "deploy_service", (p,), approval=True)
    return matrix


SEED_POLICIES = _build_policies()


def seed_users(db, password: str | None = None) -> dict[str, User]:
    users_by_username: dict[str, User] = {}
    for username, role in SEED_USERS:
        existing = db.query(User).filter_by(username=username).one_or_none()
        if existing:
            if password and not is_argon2_hash(existing.hashed_password):
                existing.hashed_password = hash_password(password)
            users_by_username[username] = existing
            continue
        user = User(
            username=username,
            hashed_password=hash_password(password) if password else UNUSABLE_PASSWORD_HASH,
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


def seed_agents(db) -> None:
    for agent_name, status in SEED_AGENTS:
        if db.query(Agent).filter_by(agent_name=agent_name).first():
            continue
        db.add(Agent(agent_name=agent_name, status=status))


def seed_policies(db) -> int:
    """Reconcile `policies` to SEED_POLICIES (#46, #50). Returns the row count."""
    tools_by_name = {t.tool_name: t for t in db.query(Tool).all()}
    needed = {name for (_role, name, _env) in SEED_POLICIES}
    missing = sorted(needed - tools_by_name.keys())
    if missing:
        raise RuntimeError(
            f"Cannot seed policies: tools not in the registry: {missing}. "
            "Seed the tool registry first (decisions.md #11)."
        )
    name_by_id = {t.id: t.tool_name for t in tools_by_name.values()}

    kept: set[tuple[Role, str, Environment]] = set()
    for row in db.query(Policy).all():
        key = (row.role, name_by_id.get(row.tool_id), row.environment)
        if key not in SEED_POLICIES or key in kept:
            db.delete(row)  # stray or duplicate: a stale permit must not survive
            continue
        kept.add(key)
        row.allowed = True
        row.requires_approval = SEED_POLICIES[key]
        row.action = key[1]

    for key, requires_approval in SEED_POLICIES.items():
        if key in kept:
            continue
        role, tool_name, environment = key
        db.add(
            Policy(
                role=role,
                tool_id=tools_by_name[tool_name].id,
                environment=environment,
                action=tool_name,
                allowed=True,
                requires_approval=requires_approval,
            )
        )
    return len(SEED_POLICIES)


def run() -> None:
    password = os.getenv(SEED_PASSWORD_ENV) or None
    if password is None:
        print(
            f"WARNING: {SEED_PASSWORD_ENV} is not set. New users get an unusable "
            "password hash and cannot log in; existing hashes are left alone."
        )
    db = SessionLocal()
    try:
        users_by_username = seed_users(db, password)
        db.commit()  # users must be committed before services reference their id
        seed_services(db, users_by_username)
        seed_agents(db)
        policy_count = seed_policies(db)
        db.commit()
        print(
            f"Seed complete: {len(SEED_USERS)} users, {len(SEED_SERVICES)} services, "
            f"{len(SEED_AGENTS)} agents, {policy_count} policies (idempotent)."
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run()