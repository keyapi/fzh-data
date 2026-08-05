"""ExportLizardUploadService / ImportLizardTrackingService tests."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from sellfox_shipping.carriers.lizard.dims import CartonDims, StaticDimsLookup
from sellfox_shipping.lizard_batch import (
    ExportLizardUploadService,
    ImportLizardTrackingService,
    LizardExportRequest,
    LizardImportRequest,
)
from sellfox_shipping.package_models import (
    SellfoxPackageAddress,
    SellfoxPackageItemRecord,
    SellfoxPackageLogistics,
    SellfoxPackageRecord,
)
from sellfox_shipping.package_repository import PackageRepository


def _seed_approved(repo: PackageRepository, sn: str = "P2ATEST001") -> None:
    repo.upsert(
        SellfoxPackageRecord(
            account_key="sellfox-main",
            package_sn=sn,
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
        account_key="sellfox-main",
        package_sn=sn,
        local_review_status="approved",
    )


def test_export_service_writes_xlsx_and_audit(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed_approved(repo)
    dims = StaticDimsLookup(
        {
            "KS0248-HLR-60-BLACK": CartonDims(
                weight_kg=2.5, length_cm=60, width_cm=55, height_cm=5
            )
        }
    )
    out = tmp_path / "out.xlsx"
    result = ExportLizardUploadService(repo, dims).export(
        LizardExportRequest(
            account_key="sellfox-main",
            actor="user-1",
            output_path=out,
        )
    )
    assert result.exported == 1
    assert result.skipped == 0
    assert result.artifact_id is not None
    assert Path(result.output_path).is_file()
    assert len(result.file_md5) == 32
    df = pd.read_excel(out)
    assert df.iloc[0]["参考编号/Reference Code"] == "P2ATEST001"
    arts = repo.list_artifacts(account_key="sellfox-main", kind="lizard_upload_export")
    assert len(arts) == 1
    assert arts[0].id == result.artifact_id
    assert arts[0].content_hash == result.file_md5
    assert len(arts[0].content_hash) == 32
    events = repo.list_audit_events(limit=10)
    assert any(e.action == "lizard.upload_export" for e in events)
    assert any(e.action == "artifacts.register" for e in events)


def test_import_service_reconciles_known_sns(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed_approved(repo)
    ret = tmp_path / "return.xlsx"
    pd.DataFrame(
        [
            {
                "参考编号/Reference Code": "P2ATEST001",
                "物流单号": "TN1",
                "订单号": "M1",
                "运费": 12.5,
            },
            {
                "参考编号/Reference Code": "NOPE",
                "物流单号": "TN2",
                "订单号": "M2",
            },
        ]
    ).to_excel(ret, index=False)

    result = ImportLizardTrackingService(repo).import_file(
        LizardImportRequest(
            account_key="sellfox-main",
            actor="user-1",
            input_path=ret,
        )
    )
    assert result.matched == 1
    assert result.unmatched == 1
    assert result.persisted == 1
    assert result.matched_rows[0]["tracking_number"] == "TN1"
    saved = repo.get("sellfox-main", "P2ATEST001")
    assert saved is not None
    assert saved.logistics.tracking_number == "TN1"
    assert saved.logistics.estimated_cost == 12.5


def test_import_conflict_does_not_overwrite_different_tracking(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed_approved(repo)
    repo.set_tracking_number(
        account_key="sellfox-main",
        package_sn="P2ATEST001",
        tracking_number="OLD-TN",
    )
    ret = tmp_path / "return.xlsx"
    pd.DataFrame(
        [
            {
                "参考编号/Reference Code": "P2ATEST001",
                "物流单号": "NEW-TN",
                "订单号": "M1",
            }
        ]
    ).to_excel(ret, index=False)
    result = ImportLizardTrackingService(repo).import_file(
        LizardImportRequest(
            account_key="sellfox-main",
            actor="user-1",
            input_path=ret,
        )
    )
    assert result.persisted == 0
    assert result.conflicts == 1
    assert repo.get("sellfox-main", "P2ATEST001").logistics.tracking_number == "OLD-TN"


def test_import_overwrites_package_sn_placeholder_tracking(tmp_path: Path) -> None:
    """Sellfox trackNo often equals packageSn before real carrier tracking exists."""
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed_approved(repo)
    repo.set_tracking_number(
        account_key="sellfox-main",
        package_sn="P2ATEST001",
        tracking_number="P2ATEST001",
    )
    ret = tmp_path / "return.xlsx"
    pd.DataFrame(
        [
            {
                "参考编号/Reference Code": "P2ATEST001",
                "物流单号": "8822446688",
                "订单号": "M1",
                "运费": 9.9,
            }
        ]
    ).to_excel(ret, index=False)
    result = ImportLizardTrackingService(repo).import_file(
        LizardImportRequest(
            account_key="sellfox-main",
            actor="user-1",
            input_path=ret,
        )
    )
    assert result.persisted == 1
    assert result.conflicts == 0
    saved = repo.get("sellfox-main", "P2ATEST001")
    assert saved is not None
    assert saved.logistics.tracking_number == "8822446688"
