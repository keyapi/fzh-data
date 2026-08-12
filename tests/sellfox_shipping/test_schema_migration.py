from __future__ import annotations

import sqlite3

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
        claim_fence_col = connection.exec_driver_sql(
            "SELECT 1 FROM pragma_table_info('shipping_label_operations') "
            "WHERE name='claim_token'"
        ).scalar_one()
        resolution_evidence = connection.exec_driver_sql(
            "SELECT 1 FROM pragma_table_info('shipping_label_operations') "
            "WHERE name='resolution_evidence_id'"
        ).scalar_one()
        conclusion = connection.exec_driver_sql(
            "SELECT 1 FROM pragma_table_info('shipping_label_investigations') "
            "WHERE name='conclusion'"
        ).scalar_one()
        evidence_provider_id = connection.exec_driver_sql(
            "SELECT 1 FROM pragma_table_info('shipping_label_investigations') "
            "WHERE name='provider_order_id'"
        ).scalar_one()
        outbox_ddl = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type='table' "
            "AND name='shipping_sellfox_outbox'"
        ).scalar_one()
        policy_ddl = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type='table' "
            "AND name='shipping_sellfox_writeback_policies'"
        ).scalar_one()

    assert version == "0023_tongtool_mark"
    assert packages == "shipping_packages"
    assert audit == "shipping_audit_events"
    assert claim_fence_col == 1
    assert resolution_evidence == 1
    assert conclusion == 1
    assert evidence_provider_id == 1
    assert "ck_sellfox_outbox_status" in outbox_ddl
    assert "ck_sellfox_outbox_generation_positive" in outbox_ddl
    assert "ck_sellfox_writeback_policy_scope_gate" in policy_ddl


def test_repository_upgrades_historical_0015_database_through_head(tmp_path) -> None:
    db_path = tmp_path / "shipping-0015.db"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE alembic_version (version_num VARCHAR(64) NOT NULL);
            INSERT INTO alembic_version VALUES ('0015_label_acquisition_safety');
            CREATE TABLE shipping_accounts (id INTEGER PRIMARY KEY);
            CREATE TABLE shipping_packages (id INTEGER PRIMARY KEY);
            CREATE TABLE shipping_labels (
                id INTEGER PRIMARY KEY,
                package_id INTEGER,
                status VARCHAR NOT NULL DEFAULT 'pending',
                operation_id INTEGER,
                is_active INTEGER NOT NULL DEFAULT 1
            );
            CREATE UNIQUE INDEX uq_shipping_labels_one_active_per_package
            ON shipping_labels(package_id) WHERE is_active = 1;
            CREATE TABLE shipping_label_operations (
                id INTEGER PRIMARY KEY,
                account_id INTEGER NOT NULL,
                package_id INTEGER NOT NULL,
                generation INTEGER NOT NULL,
                carrier VARCHAR NOT NULL DEFAULT '',
                service_level VARCHAR NOT NULL DEFAULT '',
                idempotency_key VARCHAR NOT NULL DEFAULT '',
                request_hash VARCHAR NOT NULL DEFAULT '',
                status VARCHAR NOT NULL DEFAULT 'RESERVED',
                provider_order_id VARCHAR NOT NULL DEFAULT '',
                tracking_number VARCHAR NOT NULL DEFAULT '',
                attempt_count INTEGER NOT NULL DEFAULT 0,
                error_class VARCHAR NOT NULL DEFAULT '',
                error_summary TEXT NOT NULL DEFAULT '',
                created_by VARCHAR NOT NULL DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(account_id) REFERENCES shipping_accounts(id) ON DELETE CASCADE,
                FOREIGN KEY(package_id) REFERENCES shipping_packages(id) ON DELETE CASCADE
            );
            CREATE UNIQUE INDEX uq_label_operations_one_active_per_package
            ON shipping_label_operations(package_id)
            WHERE status IN ('RESERVED', 'SENT', 'ACCEPTED', 'LABEL_PENDING', 'UNKNOWN_BLOCKED');
            """
        )

    repository = PackageRepository(db_path)

    with repository.engine.connect() as connection:
        version = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one()
        resolution_evidence = connection.exec_driver_sql(
            "SELECT 1 FROM pragma_table_info('shipping_label_operations') "
            "WHERE name='resolution_evidence_id'"
        ).scalar_one()
        evidence_foreign_key = connection.exec_driver_sql(
            "SELECT 1 FROM pragma_foreign_key_list('shipping_label_operations') "
            "WHERE `table`='shipping_label_investigations' "
            "AND `from`='resolution_evidence_id' AND `to`='id' "
            "AND on_delete='SET NULL'"
        ).scalar_one()
        existing_foreign_keys = {
            (row[2], row[3], row[4], row[6])
            for row in connection.exec_driver_sql(
                "PRAGMA foreign_key_list('shipping_label_operations')"
            )
        }
        active_index = connection.exec_driver_sql(
            "SELECT 1 FROM pragma_index_list('shipping_label_operations') "
            "WHERE name='uq_label_operations_one_active_per_package' "
            "AND `unique`=1"
        ).scalar_one()

    assert version == "0023_tongtool_mark"
    assert resolution_evidence == 1
    assert evidence_foreign_key == 1
    assert ("shipping_accounts", "account_id", "id", "CASCADE") in existing_foreign_keys
    assert ("shipping_packages", "package_id", "id", "CASCADE") in existing_foreign_keys
    assert active_index == 1


def test_repository_repairs_partially_applied_0018_foreign_key(tmp_path) -> None:
    db_path = tmp_path / "shipping-partial-0018.db"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE alembic_version (version_num VARCHAR(64) NOT NULL);
            INSERT INTO alembic_version VALUES ('0018_resume_fencing_and_evidence_link');
            CREATE TABLE shipping_label_investigations (
                id INTEGER PRIMARY KEY
            );
            CREATE TABLE shipping_labels (
                id INTEGER PRIMARY KEY,
                package_id INTEGER,
                status VARCHAR NOT NULL DEFAULT 'pending',
                operation_id INTEGER,
                is_active INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE shipping_label_operations (
                id INTEGER PRIMARY KEY,
                resolution_evidence_id INTEGER
            );
            """
        )

    repository = PackageRepository(db_path)

    with repository.engine.connect() as connection:
        version = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one()
        evidence_foreign_key = connection.exec_driver_sql(
            "SELECT 1 FROM pragma_foreign_key_list('shipping_label_operations') "
            "WHERE `table`='shipping_label_investigations' "
            "AND `from`='resolution_evidence_id' AND `to`='id' "
            "AND on_delete='SET NULL'"
        ).scalar_one()

    assert version == "0023_tongtool_mark"
    assert evidence_foreign_key == 1


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

    assert version == "0023_tongtool_mark"
    assert review_col == 1
    assert repository.count_rows()["packages"] == 0
