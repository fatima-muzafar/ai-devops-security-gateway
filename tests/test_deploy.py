"""
Tests for deploy_service() (backend/mock_devops_env/services/actions.py).

Covers decisions.md #9: deploy must set known_good_version to the
version being *replaced*, never to the newly deployed version and never
left unchanged.
"""
import pytest

from app.database.enums import ChangeType
from app.database.models import ServiceStateHistory
from mock_devops_env.services.actions import deploy_service


def test_deploy_advances_current_version(db, test_service):
    history = deploy_service(db, test_service, target_version=2)
    db.commit()

    assert test_service.current_version == 2
    assert history.change_type == ChangeType.DEPLOY
    assert history.version_before == 1
    assert history.version_after == 2


def test_deploy_sets_known_good_to_the_replaced_version(db, test_service):
    # decisions.md #9: after deploying v2, known_good becomes 1 (the
    # replaced version) — not 2, and not left at whatever it was before.
    deploy_service(db, test_service, target_version=2)
    db.commit()
    assert test_service.known_good_version == 1

    # A second deploy: known_good should now become 2 (what deploy #1
    # left running), proving this tracks "one step behind" continuously,
    # not just on the very first deploy.
    deploy_service(db, test_service, target_version=5)
    db.commit()
    assert test_service.known_good_version == 2
    assert test_service.current_version == 5


def test_deploy_rejects_zero_or_negative_version(db, test_service):
    with pytest.raises(ValueError):
        deploy_service(db, test_service, target_version=0)

    with pytest.raises(ValueError):
        deploy_service(db, test_service, target_version=-3)


def test_deploy_writes_history_row_with_matching_versions(db, test_service):
    deploy_service(db, test_service, target_version=7)
    db.commit()

    row = (
        db.query(ServiceStateHistory)
        .filter_by(service_id=test_service.id, change_type=ChangeType.DEPLOY)
        .one()
    )
    assert row.version_before == 1
    assert row.version_after == 7