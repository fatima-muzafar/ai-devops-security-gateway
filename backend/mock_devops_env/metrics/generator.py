"""
Phase 4: simulated metrics content for the mock DevOps environment.

Placement note: see mock_devops_env/logs/generator.py's docstring — same
Section 28 reasoning applies. Moved here from app/mcp/simulated_data.py,
logic unchanged.
"""
import random

from app.database.models import Service


def generate_metrics(service: Service) -> dict:
    """Return a simulated point-in-time metrics snapshot.

    `status`-aware: a "degraded" service reports worse numbers than a
    "healthy" one, so Demo/E4 scenarios (Section 18/29) that flip status
    have something observable to check via get_metrics().
    """
    rng = random.Random(f"{service.id}-{service.current_version}-metrics")
    degraded = service.status != "healthy"

    return {
        "service": service.service_name,
        "environment": service.environment.value,
        "status": service.status,
        "current_version": service.current_version,
        "cpu_percent": rng.randint(55, 90) if degraded else rng.randint(5, 40),
        "memory_percent": rng.randint(60, 95) if degraded else rng.randint(20, 55),
        "error_rate_percent": round(rng.uniform(2.0, 12.0), 2) if degraded else round(rng.uniform(0.0, 0.5), 2),
        "p95_latency_ms": rng.randint(400, 1500) if degraded else rng.randint(50, 250),
        "requests_per_minute": rng.randint(50, 500),
    }