"""Apply Alembic migrations for the package-centric SQLite schema."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

PACKAGE_ROOT = Path(__file__).resolve().parent
ALEMBIC_INI = PACKAGE_ROOT / "alembic.ini"
MIGRATIONS_DIR = PACKAGE_ROOT / "migrations"
HEAD_REVISION = "0001_package_schema"


def upgrade_schema(db_path: str | Path) -> None:
    """Upgrade package tables to head, or stamp legacy create_all databases."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{path.resolve().as_posix()}")

    with sqlite3.connect(path) as connection:
        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

    if "shipping_packages" in table_names and "alembic_version" not in table_names:
        command.stamp(cfg, HEAD_REVISION)
        return

    command.upgrade(cfg, "head")
