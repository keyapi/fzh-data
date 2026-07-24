"""Minimal ShippingBatch create/list for lizard export/import."""

from __future__ import annotations

from pathlib import Path

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


def _seed(repo: PackageRepository, sn: str = "P2ABATCH1") -> None:
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


def test_export_creates_shipping_batch(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    _seed(repo)
    dims = StaticDimsLookup(
        {
            "KS0248-HLR-60-BLACK": CartonDims(
                weight_kg=2.5, length_cm=60, width_cm=55, height_cm=5
            )
        }
    )
    result = ExportLizardUploadService(repo, dims).export(
        LizardExportRequest(
            account_key="sellfox-main",
            actor="batch-ops",
            output_path=tmp_path / "out.xlsx",
        )
    )
    assert result.batch_id is not None
    batch = repo.get_batch(result.batch_id)
    assert batch is not None
    assert batch.status == "exported"
    assert batch.success_count == 1
    assert batch.export_artifact_id == result.artifact_id
    pkgs = repo.list_batch_packages(result.batch_id)
    assert len(pkgs) == 1
    assert pkgs[0].package_sn == "P2ABATCH1"
    assert pkgs[0].status == "exported"


def test_import_updates_batch_when_batch_id_given(tmp_path: Path) -> None:
    import pandas as pd

    repo = PackageRepository(tmp_path / "shipping.db")
    _seed(repo)
    dims = StaticDimsLookup(
        {
            "KS0248-HLR-60-BLACK": CartonDims(
                weight_kg=2.5, length_cm=60, width_cm=55, height_cm=5
            )
        }
    )
    exported = ExportLizardUploadService(repo, dims).export(
        LizardExportRequest(
            account_key="sellfox-main",
            actor="batch-ops",
            output_path=tmp_path / "out.xlsx",
        )
    )
    ret = tmp_path / "return.xlsx"
    pd.DataFrame(
        [
            {
                "参考编号/Reference Code": "P2ABATCH1",
                "物流单号": "TN-BATCH",
                "订单号": "M1",
                "运费": 1.5,
            }
        ]
    ).to_excel(ret, index=False)
    imported = ImportLizardTrackingService(repo).import_file(
        LizardImportRequest(
            account_key="sellfox-main",
            actor="batch-ops",
            input_path=ret,
            batch_id=exported.batch_id,
        )
    )
    assert imported.batch_id == exported.batch_id
    batch = repo.get_batch(exported.batch_id)
    assert batch is not None
    assert batch.status == "tracking_imported"
    assert batch.import_artifact_id == imported.artifact_id
    pkgs = repo.list_batch_packages(exported.batch_id)
    assert pkgs[0].status == "tracking_matched"


def test_migration_head_includes_batches(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    with repo.engine.connect() as connection:
        version = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one()
        table = connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='shipping_batches'"
        ).scalar_one()
    assert version == "0010_package_rates"
    assert table == "shipping_batches"
