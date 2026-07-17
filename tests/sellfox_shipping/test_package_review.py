from __future__ import annotations

import pytest
from pydantic import ValidationError

from sellfox_shipping.package_models import (
    SellfoxPackageLogistics,
    SellfoxPackageOrderRecord,
    SellfoxPackageRecord,
)
from sellfox_shipping.package_repository import PackageRepository
from sellfox_shipping.package_service import (
    PackageReviewRequest,
    ReviewPackageService,
)


def _seed(repo: PackageRepository, package_sn: str = "P10001") -> None:
    repo.upsert(
        SellfoxPackageRecord(
            account_key="sellfox-main",
            package_sn=package_sn,
            package_status="to_audit",
            logistics=SellfoxPackageLogistics(channel_name="蜴国际"),
            orders=[SellfoxPackageOrderRecord(external_order_id="O-1")],
        )
    )


def test_review_approves_package_and_writes_audit(tmp_path) -> None:
    repository = PackageRepository(tmp_path / "shipping.db")
    _seed(repository)
    service = ReviewPackageService(repository)

    result = service.review(
        PackageReviewRequest(
            account_key="sellfox-main",
            package_sn="P10001",
            actor="user-1",
            decision="approved",
            note="ok for export",
        )
    )

    assert result.local_review_status == "approved"
    saved = repository.get("sellfox-main", "P10001")
    assert saved is not None
    assert saved.local_review_status == "approved"
    events = repository.list_audit_events(limit=5)
    assert events[0].actor == "user-1"
    assert events[0].action == "packages.review"
    assert "approved" in events[0].summary


def test_review_rejects_unknown_package(tmp_path) -> None:
    service = ReviewPackageService(PackageRepository(tmp_path / "shipping.db"))

    with pytest.raises(LookupError, match="not found"):
        service.review(
            PackageReviewRequest(
                account_key="sellfox-main",
                package_sn="MISSING",
                actor="user-1",
                decision="rejected",
            )
        )


def test_review_rejects_blank_actor() -> None:
    with pytest.raises(ValidationError):
        PackageReviewRequest(
            account_key="sellfox-main",
            package_sn="P10001",
            actor="  ",
            decision="approved",
        )


def test_list_packages_can_filter_by_local_review_status(tmp_path) -> None:
    repository = PackageRepository(tmp_path / "shipping.db")
    _seed(repository, "P1")
    _seed(repository, "P2")
    ReviewPackageService(repository).review(
        PackageReviewRequest(
            account_key="sellfox-main",
            package_sn="P1",
            actor="user-1",
            decision="approved",
        )
    )

    rows = repository.list_packages(
        account_key="sellfox-main",
        local_review_status="approved",
    )
    assert [row.package_sn for row in rows] == ["P1"]
    assert rows[0].local_review_status == "approved"
