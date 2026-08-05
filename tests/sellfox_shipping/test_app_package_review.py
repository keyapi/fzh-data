from __future__ import annotations

from fastapi.testclient import TestClient

from sellfox_shipping import app as app_module
from sellfox_shipping.package_models import SellfoxPackageRecord
from sellfox_shipping.package_repository import PackageRepository


def test_review_package_api_approves(tmp_path, monkeypatch) -> None:
    repository = PackageRepository(tmp_path / "shipping.db")
    account = app_module.config["sellfox"]["proxy_account"]
    repository.upsert(
        SellfoxPackageRecord(
            account_key=account,
            package_sn="P-REV-1",
            package_status="to_audit",
        )
    )
    monkeypatch.setattr(app_module, "_get_package_repository", lambda: repository)

    response = TestClient(app_module.app).post(
        "/api/packages/P-REV-1/review",
        json={"actor": "user-1", "decision": "approved", "note": "ready"},
    )

    assert response.status_code == 200
    assert response.json()["local_review_status"] == "approved"
    assert repository.get(account, "P-REV-1").local_review_status == "approved"
