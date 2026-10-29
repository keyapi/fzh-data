from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from config import AccountConfig, AppConfig, Capabilities, Credentials
from main import create_app, create_runtime_app


def _config() -> AppConfig:
    return AppConfig(
        accounts={
            "centrade": AccountConfig(
                upstream="https://api.example.test",
                credentials=Credentials(client_id="id", client_secret="secret"),
                capabilities=Capabilities(inventory_snapshot=True),
            )
        }
    )


def test_runtime_app_loads_paths_from_environment(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
accounts:
  centrade:
    upstream: https://api.example.test
    credentials:
      client_id: id
      client_secret: secret
""".strip(),
        encoding="utf-8",
    )
    db_path = tmp_path / "runtime.db"
    monkeypatch.setenv("WAYFAIR_CONFIG", str(config_path))
    monkeypatch.setenv("WAYFAIR_DATABASE", str(db_path))

    app = create_runtime_app()
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert app.state.config.accounts["centrade"].capabilities.model_dump() == {
        "inventory_snapshot": False,
        "inventory_live": False,
        "inventory_transactions": False,
        "inbound_live": False,
    }
    assert db_path.exists()


def test_health_does_not_require_auth(tmp_path):
    with TestClient(create_app(_config(), db_path=tmp_path / "wayfair.db")) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_inventory_route_requires_bearer_key(tmp_path):
    with TestClient(create_app(_config(), db_path=tmp_path / "wayfair.db")) as client:
        response = client.post(
            "/v1/accounts/centrade/inventory/query",
            json={"skus": ["SKU-1"], "mode": "snapshot"},
        )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "unauthorized"


def test_live_capability_gate_returns_stable_error(tmp_path):
    app = create_app(_config(), db_path=tmp_path / "wayfair.db")
    with TestClient(app) as client:
        async def create_key():
            return await app.state.db.create_api_key(
                name="test",
                accounts=["centrade"],
                operations=["inventory:live:read"],
            )

        created = client.portal.call(create_key)
        response = client.post(
            "/v1/accounts/centrade/inventory/query",
            json={"skus": ["SKU-1"], "mode": "live"},
            headers={"Authorization": f"Bearer {created.raw_key}"},
        )

    assert response.status_code == 501
    assert response.json()["detail"]["code"] == "capability_unavailable"


def _create_key(client, app, **overrides):
    async def create():
        return await app.state.db.create_api_key(
            name=overrides.get("name", "test"),
            accounts=overrides.get("accounts", ["centrade"]),
            operations=overrides.get("operations", ["inventory:snapshot:read"]),
        )

    return client.portal.call(create)


def test_inbound_route_is_capability_gated(tmp_path):
    app = create_app(_config(), db_path=tmp_path / "wayfair.db")
    with TestClient(app) as client:
        created = _create_key(client, app, operations=["inbound:read"])
        response = client.post(
            "/v1/accounts/centrade/inbound/query",
            json={"skus": ["SKU-1"]},
            headers={"Authorization": f"Bearer {created.raw_key}"},
        )

    assert response.status_code == 501
    assert response.json()["detail"]["code"] == "capability_unavailable"


def test_snapshot_run_route_requires_permission(tmp_path):
    app = create_app(_config(), db_path=tmp_path / "wayfair.db")
    with TestClient(app) as client:
        created = _create_key(client, app)
        response = client.post(
            "/admin/api/accounts/centrade/snapshot-runs",
            headers={"Authorization": f"Bearer {created.raw_key}"},
        )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "forbidden_operation"


def test_snapshot_run_route_stays_blocked(tmp_path):
    app = create_app(_config(), db_path=tmp_path / "wayfair.db")
    with TestClient(app) as client:
        created = _create_key(client, app, operations=["snapshot:run"])
        response = client.post(
            "/admin/api/accounts/centrade/snapshot-runs",
            headers={"Authorization": f"Bearer {created.raw_key}"},
        )

    assert response.status_code == 501
    assert response.json()["detail"]["code"] == "capability_unavailable"


def test_ready_reports_snapshot_state(tmp_path):
    with TestClient(create_app(_config(), db_path=tmp_path / "wayfair.db")) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["database"] == "ok"
    assert body["accounts"]["centrade"] == {"has_snapshot": False}


def test_authenticated_request_is_audited_and_counted(tmp_path):
    db_path = tmp_path / "wayfair.db"
    app = create_app(_config(), db_path=db_path)
    with TestClient(app) as client:
        created = _create_key(client, app, operations=["inventory:live:read"])
        response = client.post(
            "/v1/accounts/centrade/inventory/query",
            json={"skus": ["SKU-1"], "mode": "live"},
            headers={
                "Authorization": f"Bearer {created.raw_key}",
                "X-Request-ID": "req-123",
            },
        )

    assert response.status_code == 501
    assert response.headers["X-Request-ID"] == "req-123"

    with sqlite3.connect(db_path) as connection:
        event = connection.execute(
            """
            SELECT key_id, account, operation, status_code, error_category
            FROM audit_events WHERE request_id = ?
            """,
            ("req-123",),
        ).fetchone()
        key_row = connection.execute(
            "SELECT request_count, last_used_at FROM api_keys WHERE id = ?",
            (created.id,),
        ).fetchone()

    assert event == (
        created.id,
        "centrade",
        "inventory:live:read",
        501,
        "capability_unavailable",
    )
    assert key_row[0] == 1
    assert key_row[1] is not None


def test_export_snapshot_returns_all_positions(tmp_path):
    app = create_app(_config(), db_path=tmp_path / "wayfair.db")
    with TestClient(app) as client:
        created = _create_key(client, app, operations=["inventory:snapshot:read"])

        async def publish():
            from datetime import datetime, timezone

            return await app.state.db.publish_inventory_snapshot(
                account="centrade",
                started_at=datetime.now(timezone.utc),
                items=[
                    {"sku": "SKU-1", "warehouse": "CG", "available": 3},
                    {"sku": "SKU-2", "warehouse": "CG", "available": 0},
                ],
                upstream_count=2,
            )

        run_id = client.portal.call(publish)
        response = client.get(
            "/v1/accounts/centrade/inventory/snapshot",
            headers={"Authorization": f"Bearer {created.raw_key}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 2
    assert body["meta"]["snapshot_run_id"] == run_id
    assert body["meta"]["source"] == "snapshot"


def test_export_snapshot_without_run_is_missing(tmp_path):
    app = create_app(_config(), db_path=tmp_path / "wayfair.db")
    with TestClient(app) as client:
        created = _create_key(client, app, operations=["inventory:snapshot:read"])
        response = client.get(
            "/v1/accounts/centrade/inventory/snapshot",
            headers={"Authorization": f"Bearer {created.raw_key}"},
        )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "snapshot_missing"


def test_transactions_are_capability_gated(tmp_path):
    app = create_app(_config(), db_path=tmp_path / "wayfair.db")
    with TestClient(app) as client:
        created = _create_key(client, app, operations=["inventory:transactions:read"])
        response = client.post(
            "/v1/accounts/centrade/inventory/transactions/query",
            json={"sku": "SKU-1"},
            headers={"Authorization": f"Bearer {created.raw_key}"},
        )

    assert response.status_code == 501
    assert response.json()["detail"]["code"] == "capability_unavailable"


def test_transactions_require_permission(tmp_path):
    app = create_app(_config(), db_path=tmp_path / "wayfair.db")
    with TestClient(app) as client:
        created = _create_key(client, app, operations=["inventory:snapshot:read"])
        response = client.post(
            "/v1/accounts/centrade/inventory/transactions/query",
            json={"sku": "SKU-1"},
            headers={"Authorization": f"Bearer {created.raw_key}"},
        )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "forbidden_operation"


def test_offboarding_deactivates_all_keys_for_owner(tmp_path):
    app = create_app(_config(), db_path=tmp_path / "wayfair.db")
    with TestClient(app) as client:
        async def create_keys():
            await app.state.db.create_api_key(
                name="leaver-1",
                owner="leaver",
                accounts=["centrade"],
                operations=["inventory:snapshot:read"],
            )
            await app.state.db.create_api_key(
                name="leaver-2",
                owner="leaver",
                accounts=["centrade"],
                operations=["inventory:snapshot:read"],
            )
            return await app.state.db.create_api_key(
                name="offboarding",
                accounts=["centrade"],
                operations=["offboarding:deactivate"],
            )

        service = client.portal.call(create_keys)
        response = client.post(
            "/v1/offboarding/owners/leaver/deactivate",
            headers={"Authorization": f"Bearer {service.raw_key}"},
        )

        listed = client.portal.call(
            lambda: app.state.db.list_api_keys()
        )
        leaver_active = [row["is_active"] for row in listed if row["owner"] == "leaver"]

    assert response.status_code == 200
    assert response.json() == {"owner": "leaver", "deactivated": 2}
    assert leaver_active == [False, False]


def test_offboarding_requires_operation(tmp_path):
    app = create_app(_config(), db_path=tmp_path / "wayfair.db")
    with TestClient(app) as client:
        created = _create_key(client, app)
        response = client.post(
            "/v1/offboarding/owners/leaver/deactivate",
            headers={"Authorization": f"Bearer {created.raw_key}"},
        )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "forbidden_operation"


def test_audit_does_not_store_authorization_header(tmp_path):
    db_path = tmp_path / "wayfair.db"
    app = create_app(_config(), db_path=db_path)
    with TestClient(app) as client:
        created = _create_key(client, app, operations=["inventory:live:read"])
        client.post(
            "/v1/accounts/centrade/inventory/query",
            json={"skus": ["SKU-1"], "mode": "live"},
            headers={"Authorization": f"Bearer {created.raw_key}"},
        )

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute("SELECT * FROM audit_events").fetchone()

    assert created.raw_key not in " ".join(str(value) for value in tuple(row))
