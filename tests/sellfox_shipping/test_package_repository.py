from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from sellfox_shipping.package_models import (
    SellfoxPackageItemRecord,
    SellfoxPackageLogistics,
    SellfoxPackageOrderRecord,
    SellfoxPackageRecord,
)
from sellfox_shipping.package_repository import PackageRepository


def _record(
    *,
    account_key: str = "sellfox-main",
    package_sn: str = "P10001",
    package_status: str = "to_audit",
) -> SellfoxPackageRecord:
    return SellfoxPackageRecord(
        account_key=account_key,
        package_sn=package_sn,
        shop_id="shop-1",
        package_status=package_status,
        logistics=SellfoxPackageLogistics(channel_name="蜴国际"),
        orders=[
            SellfoxPackageOrderRecord(external_order_id="ORDER-1"),
            SellfoxPackageOrderRecord(external_order_id="ORDER-2"),
        ],
        items=[
            SellfoxPackageItemRecord(
                external_order_id="ORDER-1",
                order_item_id="ITEM-1",
                seller_sku="SKU-1",
                quantity=2,
            ),
            SellfoxPackageItemRecord(
                external_order_id="ORDER-2",
                order_item_id="ITEM-2",
                seller_sku="SKU-2",
                quantity=1,
            ),
        ],
    )


def test_repository_preserves_package_order_many_to_many(tmp_path) -> None:
    repository = PackageRepository(tmp_path / "shipping.db")

    outcome = repository.upsert(_record())
    saved = repository.get("sellfox-main", "P10001")

    assert outcome.created is True
    assert saved is not None
    assert [order.external_order_id for order in saved.orders] == [
        "ORDER-1",
        "ORDER-2",
    ]
    assert [
        (item.external_order_id, item.order_item_id)
        for item in saved.items
    ] == [
        ("ORDER-1", "ITEM-1"),
        ("ORDER-2", "ITEM-2"),
    ]


def test_repeated_upsert_updates_without_duplicate_relationships(tmp_path) -> None:
    repository = PackageRepository(tmp_path / "shipping.db")
    repository.upsert(_record())

    outcome = repository.upsert(_record(package_status="to_process"))
    saved = repository.get("sellfox-main", "P10001")
    counts = repository.count_rows()

    assert outcome.created is False
    assert saved is not None
    assert saved.package_status == "to_process"
    assert counts == {
        "accounts": 1,
        "packages": 1,
        "orders": 2,
        "package_orders": 2,
        "package_items": 2,
    }


def test_package_number_is_unique_only_within_account(tmp_path) -> None:
    repository = PackageRepository(tmp_path / "shipping.db")

    repository.upsert(_record(account_key="sellfox-main"))
    repository.upsert(_record(account_key="sellfox-us-2"))

    assert repository.count_rows()["packages"] == 2


def test_duplicate_order_entries_do_not_duplicate_package_relationships(
    tmp_path,
) -> None:
    repository = PackageRepository(tmp_path / "shipping.db")
    record = _record()
    record.orders.append(record.orders[0].model_copy())

    repository.upsert(record)

    assert repository.count_rows()["package_orders"] == 2


def test_concurrent_upserts_keep_one_account_scoped_package(tmp_path) -> None:
    db_path = tmp_path / "shipping.db"
    repository = PackageRepository(db_path)

    def upsert_once() -> None:
        repository.upsert(_record())

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda _: upsert_once(), range(8)))

    assert repository.count_rows() == {
        "accounts": 1,
        "packages": 1,
        "orders": 2,
        "package_orders": 2,
        "package_items": 2,
    }


def test_sqlite_enables_wal_foreign_keys_and_busy_timeout(tmp_path) -> None:
    db_path = tmp_path / "shipping.db"
    repository = PackageRepository(db_path)

    with repository.engine.connect() as connection:
        journal_mode = connection.exec_driver_sql("PRAGMA journal_mode").scalar_one()
        foreign_keys = connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one()
        busy_timeout = connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one()

    assert journal_mode == "wal"
    assert foreign_keys == 1
    assert busy_timeout >= 5000
