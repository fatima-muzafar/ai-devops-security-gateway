"""
Tests for restart_service() and rollback_deployment()
(backend/mock_devops_env/services/actions.py).

Uses the throwaway `test_service` fixture from conftest.py — never
touches real seeded services.
"""
from app.database.enums import ChangeType
from app.database.models import ServiceStateHistory
from mock_devops_env.services.actions import restart_service, rollback_deployment


def test_restart_sets_status_healthy_and_never_touches_version(db, test_service):
    test_service.status = "degraded"
    db.commit()

    history = restart_service(db, test_service)
    db.commit()

    assert test_service.status == "healthy"
    assert history.change_type == ChangeType.RESTART
    assert history.version_before is None
    assert history.version_after is None
    assert history.status_before == "degraded"
    assert history.status_after == "healthy"


def test_restart_writes_exactly_one_history_row(db, test_service):
    restart_service(db, test_service)
    db.commit()

    rows = (
        db.query(ServiceStateHistory)
        .filter_by(service_id=test_service.id, change_type=ChangeType.RESTART)
        .all()
    )
    assert len(rows) == 1


def test_rollback_reverts_current_version_to_known_good(db, test_service):
    # Simulate a prior deploy having already moved current_version ahead
    # of known_good_version, without going through deploy_service() —
    # this test is about rollback in isolation.
    test_service.current_version = 5
    test_service.known_good_version = 3
    db.commit()

    history = rollback_deployment(db, test_service)
    db.commit()

    assert test_service.current_version == 3
    # decisions.md #9: rollback must NOT change known_good_version itself.
    assert test_service.known_good_version == 3
    assert history.version_before == 5
    assert history.version_after == 3


def test_rollback_when_already_on_known_good_still_logs_a_row(db, test_service):
    assert test_service.current_version == test_service.known_good_version == 1

    history = rollback_deployment(db, test_service)
    db.commit()

    assert history.version_before == 1
    assert history.version_after == 1