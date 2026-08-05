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
        "audit_events": 0,
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
        "audit_events": 0,
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


def test_list_packages_filters_by_status_channel_and_account(tmp_path) -> None:
    repository = PackageRepository(tmp_path / "shipping.db")
    repository.upsert(_record(package_sn="P1", package_status="to_audit"))
    other = _record(package_sn="P2", package_status="shipped")
    other.logistics.channel_name = "GLS"
    repository.upsert(other)
    repository.upsert(
        _record(account_key="sellfox-us-2", package_sn="P1", package_status="to_audit")
    )

    rows = repository.list_packages(
        account_key="sellfox-main",
        package_status="to_audit",
        channel_name="蜴国际",
        limit=50,
    )

    assert [row.package_sn for row in rows] == ["P1"]
    assert rows[0].order_count == 2
    assert rows[0].item_count == 2
    assert rows[0].channel_name == "蜴国际"


def test_append_and_list_audit_events(tmp_path) -> None:
    repository = PackageRepository(tmp_path / "shipping.db")

    event_id = repository.append_audit_event(
        actor="user-1",
        action="packages.sync",
        entity_type="account",
        entity_id="sellfox-main",
        summary='{"input_count": 2}',
    )
    events = repository.list_audit_events(limit=10)

    assert event_id > 0
    assert len(events) == 1
    assert events[0].actor == "user-1"
    assert events[0].action == "packages.sync"
    assert events[0].entity_id == "sellfox-main"
    assert repository.count_rows()["audit_events"] == 1


# ── count_packages / list_packages with date filters ──────────────

from sellfox_shipping.package_repository import (
    OrderRow,
    PackageOrderRow,
    PackageRow,
    ShippingAccountRow,
    ShippingLabelRow,
)
from datetime import datetime, timezone


def _dt(s: str) -> datetime:
    """Parse ISO datetime string."""
    return datetime.fromisoformat(s)


def _make_package(
    repo: PackageRepository,
    account_key: str = "sellfox-main",
    package_sn: str = "P10001",
    package_status: str = "to_audit",
    channel_name: str = "蜴国际",
) -> int:
    """Upsert a package and return its db id."""
    repo.upsert(
        SellfoxPackageRecord(
            account_key=account_key,
            package_sn=package_sn,
            shop_id="shop-1",
            package_status=package_status,
            logistics=SellfoxPackageLogistics(channel_name=channel_name),
            orders=[SellfoxPackageOrderRecord(external_order_id=f"ORD-{package_sn}-1")],
            items=[
                SellfoxPackageItemRecord(
                    external_order_id=f"ORD-{package_sn}-1",
                    order_item_id=f"ITEM-{package_sn}-1",
                    seller_sku="SKU-A",
                    quantity=1,
                )
            ],
        )
    )
    return repo.get_package_db_id(account_key, package_sn)


def _add_label(
    repo: PackageRepository,
    package_db_id: int,
    *,
    status: str = "active",
    created_at: str = "2026-07-15T10:00:00",
    carrier: str = "lizard",
    tracking_number: str = "",
    is_active: bool = True,
) -> int:
    """Insert a label row directly and return its id."""
    with repo._session_factory.begin() as session:
        account = repo._get_or_create_account(session, "sellfox-main")
        label = ShippingLabelRow(
            account_id=account.id,
            package_id=package_db_id,
            carrier=carrier,
            status=status,
            created_at=_dt(created_at),
            tracking_number=tracking_number or f"TRK-{package_db_id}",
            is_active=is_active,
        )
        session.add(label)
        session.flush()
        return label.id


def _add_order(
    repo: PackageRepository,
    package_db_id: int,
    *,
    external_order_id: str,
    purchase_date: str = "2026-07-15T10:00:00",
) -> None:
    """Insert an order and link it to a package."""
    with repo._session_factory.begin() as session:
        account = repo._get_or_create_account(session, "sellfox-main")
        order = OrderRow(
            account_id=account.id,
            external_order_id=external_order_id,
            purchase_date=_dt(purchase_date),
        )
        session.add(order)
        session.flush()
        link = PackageOrderRow(package_id=package_db_id, order_id=order.id)
        session.add(link)


class TestPackageCountAndPagination:
    def test_count_baseline_no_date_filter(self, tmp_path) -> None:
        repo = PackageRepository(tmp_path / "shipping.db")
        _make_package(repo, package_sn="P1")
        _make_package(repo, package_sn="P2")
        _make_package(repo, package_sn="P3")

        count = repo.count_packages(account_key="sellfox-main")
        assert count == 3

    def test_count_multi_order_date_filter_no_duplicate(self, tmp_path) -> None:
        """A package with 3 orders in range should count once, not 3 times."""
        repo = PackageRepository(tmp_path / "shipping.db")
        pkg_id = _make_package(repo, package_sn="P-MULTI")
        _add_order(repo, pkg_id, external_order_id="ORD-2", purchase_date="2026-07-20")
        _add_order(repo, pkg_id, external_order_id="ORD-3", purchase_date="2026-07-25")

        _make_package(repo, package_sn="P-OUT", package_status="shipped")
        out_id = repo.get_package_db_id("sellfox-main", "P-OUT")
        _add_order(repo, out_id, external_order_id="ORD-OUT", purchase_date="2026-06-01")

        count = repo.count_packages(
            account_key="sellfox-main",
            date_start="2026-07-01",
            date_end="2026-07-31",
            date_field="order",
        )
        assert count == 1, f"Expected 1 package with orders in July, got {count}"

    def test_count_multi_label_date_filter_no_duplicate(self, tmp_path) -> None:
        """A package with 2 non-cancelled labels (one active, one inactive) in range should count once."""
        repo = PackageRepository(tmp_path / "shipping.db")
        pkg_id = _make_package(repo, package_sn="P-LABELS")
        _add_label(repo, pkg_id, status="active", created_at="2026-07-10", is_active=True)
        _add_label(repo, pkg_id, status="active", created_at="2026-07-20", is_active=False)

        count = repo.count_packages(
            account_key="sellfox-main",
            date_start="2026-07-01",
            date_end="2026-07-31",
            date_field="label",
        )
        assert count == 1, f"Expected 1 package, got {count}"

    def test_count_only_cancelled_labels_zero(self, tmp_path) -> None:
        """Package with only cancelled labels should not be counted with label date filter."""
        repo = PackageRepository(tmp_path / "shipping.db")
        pkg_id = _make_package(repo, package_sn="P-CANCELLED")
        _add_label(repo, pkg_id, status="cancelled", created_at="2026-07-10", is_active=False)
        _add_label(repo, pkg_id, status="cancelled", created_at="2026-07-20", is_active=False)

        count = repo.count_packages(
            account_key="sellfox-main",
            date_start="2026-07-01",
            date_end="2026-07-31",
            date_field="label",
        )
        # All labels are cancelled: LEFT JOIN gives NULL label row (id IS NULL),
        # but date filter on label.created_at excludes NULL rows.
        assert count == 0, f"Expected 0 (all cancelled labels excluded), got {count}"

    def test_count_active_and_cancelled_labels(self, tmp_path) -> None:
        """Package with mix of cancelled (inactive) and active labels: count once."""
        repo = PackageRepository(tmp_path / "shipping.db")
        pkg_id = _make_package(repo, package_sn="P-MIX")
        _add_label(repo, pkg_id, status="cancelled", created_at="2026-07-05", is_active=False)
        _add_label(repo, pkg_id, status="active", created_at="2026-07-15", is_active=True)

        count = repo.count_packages(
            account_key="sellfox-main",
            date_start="2026-07-01",
            date_end="2026-07-31",
            date_field="label",
        )
        assert count == 1, f"Expected 1, got {count}"

    def test_list_count_consistency_with_pagination(self, tmp_path) -> None:
        """list_packages and count_packages should agree on total."""
        repo = PackageRepository(tmp_path / "shipping.db")
        for i in range(5):
            _make_package(repo, package_sn=f"P-{i:03d}")

        count = repo.count_packages(account_key="sellfox-main")
        page1 = repo.list_packages(account_key="sellfox-main", limit=2, offset=0)
        page2 = repo.list_packages(account_key="sellfox-main", limit=2, offset=2)
        page3 = repo.list_packages(account_key="sellfox-main", limit=2, offset=4)

        assert count == 5
        assert len(page1) == 2
        assert len(page2) == 2
        assert len(page3) == 1
        all_sns = {r.package_sn for r in page1 + page2 + page3}
        assert len(all_sns) == 5

    def test_order_date_boundary_inclusive_start_exclusive_end(self, tmp_path) -> None:
        """date_start is inclusive, date_end+T23:59:59 is inclusive end-of-day."""
        repo = PackageRepository(tmp_path / "shipping.db")
        pkg_id = _make_package(repo, package_sn="P-EDGE")
        _add_order(repo, pkg_id, external_order_id="ORD-EDGE", purchase_date="2026-07-01T00:00:00")

        # Boundary: date_start equals purchase_date
        count = repo.count_packages(
            account_key="sellfox-main",
            date_start="2026-07-01",
            date_end="2026-07-01",
            date_field="order",
        )
        assert count == 1

        # Just before: should be 0
        count = repo.count_packages(
            account_key="sellfox-main",
            date_start="2026-07-02",
            date_end="2026-07-02",
            date_field="order",
        )
        assert count == 0

    def test_label_date_boundary(self, tmp_path) -> None:
        """Label date_start inclusive, date_end inclusive end-of-day."""
        repo = PackageRepository(tmp_path / "shipping.db")
        pkg_id = _make_package(repo, package_sn="P-EDGE")
        _add_label(repo, pkg_id, status="active", created_at="2026-07-15T00:00:00")

        count = repo.count_packages(
            account_key="sellfox-main",
            date_start="2026-07-15",
            date_end="2026-07-15",
            date_field="label",
        )
        assert count == 1

        count = repo.count_packages(
            account_key="sellfox-main",
            date_start="2026-07-16",
            date_end="2026-07-16",
            date_field="label",
        )
        assert count == 0

    def test_label_date_filter_with_no_labels_package(self, tmp_path) -> None:
        """Package with zero labels: LEFT JOIN null path, date filter on label.created_at excludes NULL."""
        repo = PackageRepository(tmp_path / "shipping.db")
        _make_package(repo, package_sn="P-NO-LABEL")

        count = repo.count_packages(
            account_key="sellfox-main",
            date_start="2026-07-01",
            date_end="2026-07-31",
            date_field="label",
        )
        assert count == 0, (
            "Package with no labels: LEFT JOIN gives NULL label row, "
            "but date filter on label.created_at excludes NULL values"
        )
