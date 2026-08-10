"""Web UI: lizard Excel export + tracking import reconciliation report."""

from __future__ import annotations

from io import BytesIO

import pandas as pd
from fastapi.testclient import TestClient

from sellfox_shipping import app as app_module
from sellfox_shipping.carriers.lizard.dims import CartonDims, StaticDimsLookup
from sellfox_shipping.package_models import (
    SellfoxPackageAddress,
    SellfoxPackageItemRecord,
    SellfoxPackageLogistics,
    SellfoxPackageRecord,
)
from sellfox_shipping.package_repository import PackageRepository


def _seed_approved(tmp_path, monkeypatch, sn: str = "P2AWEB001") -> PackageRepository:
    repository = PackageRepository(tmp_path / "shipping.db")
    account = app_module.config["sellfox"]["proxy_account"]
    repository.upsert(
        SellfoxPackageRecord(
            account_key=account,
            package_sn=sn,
            package_status="to_process",
            local_review_status="approved",
            address=SellfoxPackageAddress(
                name="Test Buyer",
                address_line_1="1 Main St",
                city="Newark",
                state_or_region="NJ",
                postal_code="07101",
                country_code="US",
                phone="5551234567",
            ),
            logistics=SellfoxPackageLogistics(channel_name="蜴国际-FedEx"),
            items=[
                SellfoxPackageItemRecord(
                    external_order_id="O1",
                    order_item_id="I1",
                    seller_sku="SKU-A",
                    commodity_sku="KS0248-HLR-60-BLACK",
                    quantity=1,
                )
            ],
        )
    )
    repository.set_local_review_status(
        account_key=account,
        package_sn=sn,
        local_review_status="approved",
    )
    monkeypatch.setattr(app_module, "_get_package_repository", lambda: repository)
    monkeypatch.setattr(
        app_module,
        "_get_lizard_dims_lookup",
        lambda: StaticDimsLookup(
            {
                "KS0248-HLR-60-BLACK": CartonDims(
                    weight_kg=2.5, length_cm=60, width_cm=55, height_cm=5
                )
            }
        ),
    )
    return repository


def test_lizard_export_page_get(tmp_path, monkeypatch) -> None:
    _seed_approved(tmp_path, monkeypatch)
    response = TestClient(app_module.app).get("/lizard/export")
    assert response.status_code == 200
    assert "导出" in response.text
    assert "蜴国际" in response.text


def test_lizard_export_post_downloads_xlsx(tmp_path, monkeypatch) -> None:
    _seed_approved(tmp_path, monkeypatch)
    response = TestClient(app_module.app).post(
        "/lizard/export",
        data={"actor": "web-tester", "limit": "50", "shipper_code": "S0143"},
    )
    assert response.status_code == 200
    assert (
        "spreadsheet"
        in response.headers.get("content-type", "").lower()
        or "octet-stream" in response.headers.get("content-type", "").lower()
        or response.headers.get("content-type", "").endswith("xlsx")
        or "application/vnd.openxmlformats" in response.headers.get("content-type", "")
    )
    assert "attachment" in response.headers.get("content-disposition", "").lower()
    assert response.content[:2] == b"PK"  # zip/xlsx magic


def test_lizard_import_page_get(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        app_module,
        "_get_package_repository",
        lambda: PackageRepository(tmp_path / "shipping.db"),
    )
    response = TestClient(app_module.app).get("/lizard/import")
    assert response.status_code == 200
    assert "追踪号" in response.text
    assert "submitToPlatform" in response.text or "不写回" in response.text


def test_submit_label_tracking_web_route_is_side_effect_free(tmp_path, monkeypatch) -> None:
    repo = _seed_approved(tmp_path, monkeypatch, sn="P2AWRITEBACKPAUSED")

    class _UnexpectedClient:
        def quick_outbound(self, package_list):
            raise AssertionError("Web route must not call quickOutbound")

    monkeypatch.setattr(app_module, "get_sellfox_client", lambda: _UnexpectedClient())
    response = TestClient(app_module.app).post(
        "/packages/P2AWRITEBACKPAUSED/submit-label-tracking",
        data={"actor": "web-tester"},
    )

    assert response.status_code == 200
    assert "quickOutbound" in response.text
    assert repo.get("sellfox-main", "P2AWRITEBACKPAUSED") is not None


def test_lizard_import_post_shows_reconciliation_report(tmp_path, monkeypatch) -> None:
    repo = _seed_approved(tmp_path, monkeypatch, sn="P2AWEBIMP")
    buf = BytesIO()
    pd.DataFrame(
        [
            {
                "参考编号/Reference Code": "P2AWEBIMP",
                "物流单号": "TN-WEB-1",
                "订单号": "M1",
                "运费": 11.5,
            },
            {
                "参考编号/Reference Code": "UNKNOWN-SN",
                "物流单号": "TN-X",
                "订单号": "M2",
            },
        ]
    ).to_excel(buf, index=False)
    buf.seek(0)

    response = TestClient(app_module.app).post(
        "/lizard/import",
        data={"actor": "web-tester"},
        files={
            "file": (
                "return.xlsx",
                buf.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert response.status_code == 200
    assert "matched" in response.text.lower() or "匹配" in response.text
    assert "P2AWEBIMP" in response.text
    assert "UNKNOWN-SN" in response.text
    assert "TN-WEB-1" in response.text
    saved = repo.get(app_module.config["sellfox"]["proxy_account"], "P2AWEBIMP")
    assert saved is not None
    assert saved.logistics.tracking_number == "TN-WEB-1"
    arts = repo.list_artifacts(
        account_key=app_module.config["sellfox"]["proxy_account"],
        kind="lizard_tracking_import",
    )
    assert len(arts) == 1


def test_artifacts_page_lists_registered_file(tmp_path, monkeypatch) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    account = app_module.config["sellfox"]["proxy_account"]
    art = repo.register_artifact(
        account_key=account,
        kind="lizard_upload_export",
        file_name="demo.xlsx",
        content=b"PK-demo",
        actor="web-tester",
        virtual_folder="lizard/export",
        summary="demo",
    )
    monkeypatch.setattr(app_module, "_get_package_repository", lambda: repo)

    page = TestClient(app_module.app).get("/lizard/artifacts")
    assert page.status_code == 200
    assert "demo.xlsx" in page.text
    assert "content_hash" in page.text

    dl = TestClient(app_module.app).get(f"/lizard/artifacts/{art.id}/download")
    assert dl.status_code == 200
    assert dl.content == b"PK-demo"


def test_batches_page_lists_export_batch(tmp_path, monkeypatch) -> None:
    from sellfox_shipping.carriers.lizard.dims import CartonDims, StaticDimsLookup
    from sellfox_shipping.lizard_batch import (
        ExportLizardUploadService,
        LizardExportRequest,
    )
    from sellfox_shipping.package_models import (
        SellfoxPackageAddress,
        SellfoxPackageItemRecord,
        SellfoxPackageLogistics,
        SellfoxPackageRecord,
    )

    repo = PackageRepository(tmp_path / "shipping.db")
    account = app_module.config["sellfox"]["proxy_account"]
    repo.upsert(
        SellfoxPackageRecord(
            account_key=account,
            package_sn="P2ABATCHWEB",
            local_review_status="approved",
            address=SellfoxPackageAddress(
                name="Test",
                address_line_1="1 Main",
                city="Newark",
                state_or_region="NJ",
                postal_code="07101",
                country_code="US",
                phone="5551234567",
            ),
            logistics=SellfoxPackageLogistics(channel_name="蜴国际-FedEx"),
            items=[
                SellfoxPackageItemRecord(
                    external_order_id="O1",
                    order_item_id="I1",
                    seller_sku="SKU-A",
                    commodity_sku="KS0248-HLR-60-BLACK",
                    quantity=1,
                )
            ],
        )
    )
    repo.set_local_review_status(
        account_key=account,
        package_sn="P2ABATCHWEB",
        local_review_status="approved",
    )
    dims = StaticDimsLookup(
        {
            "KS0248-HLR-60-BLACK": CartonDims(
                weight_kg=2.5, length_cm=60, width_cm=55, height_cm=5
            )
        }
    )
    exported = ExportLizardUploadService(repo, dims).export(
        LizardExportRequest(
            account_key=account,
            actor="web-tester",
            output_path=tmp_path / "out.xlsx",
        )
    )
    monkeypatch.setattr(app_module, "_get_package_repository", lambda: repo)

    page = TestClient(app_module.app).get("/lizard/batches")
    assert page.status_code == 200
    assert f"#{exported.batch_id}" in page.text

    detail = TestClient(app_module.app).get(
        f"/lizard/batches/{exported.batch_id}"
    )
    assert detail.status_code == 200
    assert "P2ABATCHWEB" in detail.text
    assert "exported" in detail.text
