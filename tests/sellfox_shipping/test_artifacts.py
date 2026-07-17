"""shipping_artifacts: content_hash dedup + display metadata."""

from __future__ import annotations

from pathlib import Path

from sellfox_shipping.package_repository import PackageRepository


def test_register_artifact_dedups_storage_by_content_hash(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    content = b"PK\x03\x04-fake-xlsx-content-aaaa"
    a1 = repo.register_artifact(
        account_key="sellfox-main",
        kind="lizard_upload_export",
        file_name="lizard-upload-A.xlsx",
        content=content,
        actor="ops-1",
        template_version="lizard-upload-v1-2026-07",
        virtual_folder="lizard/export",
    )
    a2 = repo.register_artifact(
        account_key="sellfox-main",
        kind="lizard_upload_export",
        file_name="lizard-upload-B.xlsx",  # different display name
        content=content,  # same bytes
        actor="ops-2",
        template_version="lizard-upload-v1-2026-07",
        virtual_folder="lizard/export",
    )
    assert a1.id != a2.id
    assert a1.content_hash == a2.content_hash
    assert a1.storage_relpath == a2.storage_relpath
    assert a1.file_name == "lizard-upload-A.xlsx"
    assert a2.file_name == "lizard-upload-B.xlsx"
    blob = Path(repo.artifacts_root) / a1.storage_relpath
    assert blob.is_file()
    assert blob.read_bytes() == content
    # only one physical file
    files = list((Path(repo.artifacts_root) / "by-hash").rglob("*"))
    assert sum(1 for f in files if f.is_file()) == 1


def test_list_artifacts_newest_first(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    repo.register_artifact(
        account_key="sellfox-main",
        kind="lizard_tracking_import",
        file_name="r1.xlsx",
        content=b"one",
        actor="a",
        virtual_folder="lizard/import",
    )
    repo.register_artifact(
        account_key="sellfox-main",
        kind="lizard_upload_export",
        file_name="e1.xlsx",
        content=b"two",
        actor="a",
        virtual_folder="lizard/export",
    )
    rows = repo.list_artifacts(account_key="sellfox-main", limit=10)
    assert len(rows) == 2
    assert rows[0].file_name == "e1.xlsx"
    only_import = repo.list_artifacts(
        account_key="sellfox-main", kind="lizard_tracking_import"
    )
    assert len(only_import) == 1


def test_migration_head_includes_artifacts(tmp_path: Path) -> None:
    repo = PackageRepository(tmp_path / "shipping.db")
    with repo.engine.connect() as connection:
        version = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one()
        table = connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='shipping_artifacts'"
        ).scalar_one()
    assert version == "0004_artifacts"
    assert table == "shipping_artifacts"
