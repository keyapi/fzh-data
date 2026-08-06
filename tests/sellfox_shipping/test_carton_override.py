"""Local carton dims overrides for lizard export when pageList/ERPNext miss."""

from __future__ import annotations

from pathlib import Path

from sellfox_shipping.carriers.lizard.cascade import CascadingDimsLookup
from sellfox_shipping.carriers.lizard.dims import CartonDims, StaticDimsLookup
from sellfox_shipping.package_repository import PackageRepository


def test_set_and_get_carton_override(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    dims = CartonDims(weight_kg=4.1, length_cm=58, width_cm=19, height_cm=45)
    saved = repo.set_carton_override(
        account_key="sellfox-main",
        commodity_sku="KS0002-DL-194-BLACK",
        dims=dims,
        actor="ops-1",
        note="manual measure",
    )
    assert saved.commodity_sku == "KS0002-DL-194-BLACK"
    assert saved.dims == dims
    got = repo.get_carton_override("sellfox-main", "KS0002-DL-194-BLACK")
    assert got is not None
    assert got.dims.weight_kg == 4.1


def test_override_lookup_beats_empty_static(tmp_path: Path) -> None:
    from sellfox_shipping.carriers.lizard.override_dims import RepositoryDimsLookup

    repo = PackageRepository(tmp_path / "shipping.db")
    sku = "KS9999-XX-1-RED"
    repo.set_carton_override(
        account_key="sellfox-main",
        commodity_sku=sku,
        dims=CartonDims(weight_kg=1.2, length_cm=10, width_cm=20, height_cm=30),
        actor="ops-1",
    )
    cascade = CascadingDimsLookup(
        RepositoryDimsLookup(repo, "sellfox-main"),
        StaticDimsLookup({}),
    )
    hit = cascade.get(sku)
    assert hit is not None
    assert hit.length_cm == 10


def test_migration_head_includes_carton_overrides(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    with repo.engine.connect() as connection:
        version = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one()
        table = connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='shipping_carton_overrides'"
        ).scalar_one()
    assert version == "0021_sellfox_outbox_lease_origin"

    assert table == "shipping_carton_overrides"
