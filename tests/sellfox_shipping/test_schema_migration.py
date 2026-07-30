from __future__ import annotations

from sellfox_shipping.package_repository import PackageRepository


def test_repository_applies_alembic_migration_on_empty_db(tmp_path) -> None:
    db_path = tmp_path / "shipping.db"
    repository = PackageRepository(db_path)

    with repository.engine.connect() as connection:
        version = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one()
        packages = connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='shipping_packages'"
        ).scalar_one()
        audit = connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='shipping_audit_events'"
        ).scalar_one()

    assert version == "0014_carton_override_item_name"

    assert packages == "shipping_packages"
    assert audit == "shipping_audit_events"


def test_repository_stamps_existing_create_all_database(tmp_path) -> None:
    """DBs created before Alembic still get a version stamp without failing."""
    from sqlalchemy import create_engine
    from sellfox_shipping.package_repository import Base

    db_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    engine.dispose()

    repository = PackageRepository(db_path)
    with repository.engine.connect() as connection:
        version = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one()
        review_col = connection.exec_driver_sql(
            "SELECT 1 FROM pragma_table_info('shipping_packages') "
            "WHERE name='local_review_status'"
        ).scalar()

    assert version == "0014_carton_override_item_name"

    assert review_col == 1
    assert repository.count_rows()["packages"] == 0
