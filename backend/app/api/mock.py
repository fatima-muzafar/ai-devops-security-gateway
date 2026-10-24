"""
Mock environment state for the dashboard (Section 17 GET /api/mock/services, FR-19;
decisions.md #91, #94, #101).

READ ONLY and admin only (require_admin reads the role from the DB, #44). Returns the
service/environment rows with their current state and the owner's USERNAME (no ids, no
history: service_state_history is Optional later, #94).

Keep this route sync `def` like the other routes (#26, #37).
"""
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.approvals import require_admin
from app.database.base import get_db
from app.database.models import Service, User

router = APIRouter()


@router.get("/api/mock/services")
def list_services(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    rows = (
        db.query(
            Service.service_name,
            Service.environment,
            Service.current_version,
            Service.known_good_version,
            Service.status,
            User.username,
        )
        .join(User, User.id == Service.owner_id)
        .order_by(Service.service_name, Service.environment)
        .all()
    )
    return [
        {
            "service_name": service_name,
            "environment": environment.value,
            "current_version": current_version,
            "known_good_version": known_good_version,
            "status": status,
            "owner": owner,
        }
        for service_name, environment, current_version, known_good_version, status, owner in rows
    ]
