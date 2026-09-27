"""
Phase 4: simulated log content for the mock DevOps environment.

Placement note: Section 28's repository structure puts `logs/` inside
`mock_devops_env/`, alongside `services/`, `state/`, `metrics/` — not
inside `app/mcp/`. This follows the same separation Phase 3 already
established for `services/actions.py`: the mock environment owns
generating/mutating its own simulated content; `app/mcp/tools.py` only
wraps and calls it, exactly like it wraps `services.actions` for
restart/rollback/deploy. This module was previously (incorrectly)
`app/mcp/simulated_data.py`'s log half — moved here, logic unchanged.

Plain function, not a class — mirrors `services/actions.py`'s style.
Not an MCP tool and not Gateway-facing; `app/mcp/tools.get_logs()` is
the tool that calls this.
"""
import random
from datetime import datetime, timedelta, timezone

from app.database.models import Service

_LOG_LEVELS = ["INFO", "INFO", "INFO", "WARN", "ERROR"]
_LOG_MESSAGES = [
    "health check passed",
    "request handled",
    "connection pool at {pct}% capacity",
    "cache miss for key",
    "retrying upstream call",
    "slow query detected ({ms}ms)",
    "unexpected response from dependency",
]


def generate_logs(service: Service, limit: int) -> list[dict]:
    """Return `limit` simulated log lines, newest first.

    Seeded on service.id + current_version so results are stable within
    a single deployed version (useful for reproducible tests/demos)
    but still vary across services/versions.
    """
    rng = random.Random(f"{service.id}-{service.current_version}")
    now = datetime.now(timezone.utc)
    lines = []
    for i in range(limit):
        level = rng.choice(_LOG_LEVELS)
        template = rng.choice(_LOG_MESSAGES)
        message = template.format(pct=rng.randint(40, 95), ms=rng.randint(200, 900))
        lines.append(
            {
                "timestamp": (now - timedelta(seconds=i * rng.randint(5, 60))).isoformat(),
                "level": level,
                "service": service.service_name,
                "environment": service.environment.value,
                "message": message,
            }
        )
    return lines