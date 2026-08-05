"""SQLite storage layer for sellfox_shipping.

Orders, labels, tracking log, and rule log tables.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sellfox_shipping.models import (
    Address,
    Label,
    LabelFormat,
    Order,
    OrderItem,
    PackageStatus,
    TrackingInfo,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    """SQLite-backed persistence for shipping data."""

    def __init__(self, db_path: str = "data/shipping.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    # ── schema ──────────────────────────────────────────────────

    def _create_tables(self):
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                amazon_order_id TEXT UNIQUE NOT NULL,
                seller_order_id TEXT,
                package_sn TEXT,
                shop_id TEXT,
                shop_name TEXT,
                platform TEXT DEFAULT 'Amazon',
                marketplace TEXT,
                order_status TEXT,
                package_status TEXT DEFAULT 'to_audit',
                purchase_date TEXT,
                earliest_ship_date TEXT,
                latest_ship_date TEXT,
                order_total REAL DEFAULT 0,
                currency TEXT DEFAULT 'USD',
                raw_json TEXT,
                fetched_at TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS addresses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER REFERENCES orders(id) ON DELETE CASCADE,
                name TEXT,
                company TEXT,
                address1 TEXT,
                address2 TEXT,
                city TEXT,
                state TEXT,
                postal_code TEXT,
                country TEXT,
                country_code TEXT,
                phone TEXT,
                email TEXT
            );

            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER REFERENCES orders(id) ON DELETE CASCADE,
                order_item_id TEXT,
                seller_sku TEXT,
                commodity_sku TEXT,
                commodity_name TEXT,
                asin TEXT,
                quantity INTEGER DEFAULT 0,
                main_image TEXT,
                variation TEXT
            );

            CREATE TABLE IF NOT EXISTS labels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER REFERENCES orders(id),
                package_sn TEXT,
                carrier TEXT NOT NULL,
                service_level TEXT,
                tracking_number TEXT UNIQUE,
                forward_number TEXT,
                label_format TEXT DEFAULT 'PDF',
                label_path TEXT,
                cost REAL DEFAULT 0,
                currency TEXT DEFAULT 'USD',
                status TEXT DEFAULT 'generated',
                carrier_response_json TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS tracking_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label_id INTEGER REFERENCES labels(id),
                package_sn TEXT,
                action TEXT,
                sellfox_response_code INTEGER,
                sellfox_response_json TEXT,
                success INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS rule_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER REFERENCES orders(id),
                rule_name TEXT,
                carrier_selected TEXT,
                service_selected TEXT,
                match_reason TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            """
        )
        self.conn.commit()

    # ── orders ──────────────────────────────────────────────────

    def upsert_order(self, order: Order) -> int:
        """Insert or update an order by amazon_order_id. Returns order db id."""
        existing = self.conn.execute(
            "SELECT id FROM orders WHERE amazon_order_id = ?",
            (order.amazon_order_id,),
        ).fetchone()

        order_dict = {
            "amazon_order_id": order.amazon_order_id,
            "seller_order_id": order.seller_order_id,
            "package_sn": order.package_sn,
            "shop_id": order.shop_id,
            "shop_name": order.shop_name,
            "platform": order.platform,
            "marketplace": order.marketplace,
            "order_status": order.order_status,
            "package_status": order.package_status.value,
            "purchase_date": order.purchase_date.isoformat() if order.purchase_date else None,
            "earliest_ship_date": order.earliest_ship_date.isoformat() if order.earliest_ship_date else None,
            "latest_ship_date": order.latest_ship_date.isoformat() if order.latest_ship_date else None,
            "order_total": order.order_total,
            "currency": order.currency,
            "raw_json": order.raw_json,
            "fetched_at": order.fetched_at.isoformat() if order.fetched_at else _now(),
            "updated_at": _now(),
        }

        if existing:
            order_id = existing["id"]
            set_clause = ", ".join(f"{k}=:{k}" for k in order_dict)
            self.conn.execute(
                f"UPDATE orders SET {set_clause} WHERE id=:id",
                {**order_dict, "id": order_id},
            )
        else:
            cols = ", ".join(order_dict.keys())
            placeholders = ", ".join(f":{k}" for k in order_dict)
            cursor = self.conn.execute(
                f"INSERT INTO orders ({cols}) VALUES ({placeholders})",
                order_dict,
            )
            order_id = cursor.lastrowid

        # Address
        addr = order.shipping_address
        self.conn.execute(
            "DELETE FROM addresses WHERE order_id = ?", (order_id,)
        )
        self.conn.execute(
            """INSERT INTO addresses
               (order_id, name, company, address1, address2, city, state,
                postal_code, country, country_code, phone, email)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (order_id, addr.name, addr.company, addr.address1, addr.address2,
             addr.city, addr.state, addr.postal_code, addr.country,
             addr.country_code, addr.phone, addr.email),
        )

        # Items
        self.conn.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
        for item in order.items:
            self.conn.execute(
                """INSERT INTO order_items
                   (order_id, order_item_id, seller_sku, commodity_sku,
                    commodity_name, asin, quantity, main_image, variation)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (order_id, item.order_item_id, item.seller_sku,
                 item.commodity_sku, item.commodity_name, item.asin,
                 item.quantity, item.main_image, item.variation),
            )

        self.conn.commit()
        return order_id

    def get_order(self, amazon_order_id: str) -> Optional[Order]:
        row = self.conn.execute(
            "SELECT * FROM orders WHERE amazon_order_id = ?",
            (amazon_order_id,),
        ).fetchone()
        if not row:
            return None
        return self._row_to_order(row)

    def list_orders(
        self,
        status: Optional[str] = None,
        carrier: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Order]:
        query = "SELECT * FROM orders WHERE 1=1"
        params: list = []
        if status:
            query += " AND package_status = ?"
            params.append(status)
        if carrier:
            query += """ AND id IN (
                SELECT DISTINCT order_id FROM labels WHERE carrier = ?
            )"""
            params.append(carrier)
        query += " ORDER BY purchase_date DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self.conn.execute(query, params).fetchall()
        return [self._row_to_order(r) for r in rows]

    def count_orders(self, status: Optional[str] = None) -> int:
        query = "SELECT COUNT(*) FROM orders"
        params: list = []
        if status:
            query += " WHERE package_status = ?"
            params.append(status)
        return self.conn.execute(query, params).fetchone()[0]

    def _row_to_order(self, row: sqlite3.Row) -> Order:
        addr_row = self.conn.execute(
            "SELECT * FROM addresses WHERE order_id = ?", (row["id"],)
        ).fetchone()
        addr = Address()
        if addr_row:
            addr = Address(
                name=addr_row["name"] or "",
                company=addr_row["company"] or "",
                address1=addr_row["address1"] or "",
                address2=addr_row["address2"] or "",
                city=addr_row["city"] or "",
                state=addr_row["state"] or "",
                postal_code=addr_row["postal_code"] or "",
                country=addr_row["country"] or "",
                country_code=addr_row["country_code"] or "",
                phone=addr_row["phone"] or "",
                email=addr_row["email"] or "",
            )

        item_rows = self.conn.execute(
            "SELECT * FROM order_items WHERE order_id = ?", (row["id"],)
        ).fetchall()
        items = [
            OrderItem(
                order_item_id=ir["order_item_id"] or "",
                seller_sku=ir["seller_sku"] or "",
                commodity_sku=ir["commodity_sku"] or "",
                commodity_name=ir["commodity_name"] or "",
                asin=ir["asin"] or "",
                quantity=ir["quantity"] or 0,
                main_image=ir["main_image"] or "",
                variation=ir["variation"] or "",
            )
            for ir in item_rows
        ]

        return Order(
            id=row["id"],
            amazon_order_id=row["amazon_order_id"],
            seller_order_id=row["seller_order_id"] or "",
            package_sn=row["package_sn"] or "",
            shop_id=row["shop_id"] or "",
            shop_name=row["shop_name"] or "",
            platform=row["platform"] or "Amazon",
            marketplace=row["marketplace"] or "",
            order_status=row["order_status"] or "",
            package_status=PackageStatus(row["package_status"] or "to_audit"),
            purchase_date=datetime.fromisoformat(row["purchase_date"]) if row["purchase_date"] else None,
            earliest_ship_date=datetime.fromisoformat(row["earliest_ship_date"]) if row["earliest_ship_date"] else None,
            latest_ship_date=datetime.fromisoformat(row["latest_ship_date"]) if row["latest_ship_date"] else None,
            order_total=row["order_total"] or 0.0,
            currency=row["currency"] or "USD",
            shipping_address=addr,
            items=items,
            raw_json=row["raw_json"] or "",
            fetched_at=datetime.fromisoformat(row["fetched_at"]) if row["fetched_at"] else None,
        )

    # ── labels ──────────────────────────────────────────────────

    def save_label(self, label: Label) -> int:
        cols = [
            "order_id", "package_sn", "carrier", "service_level",
            "tracking_number", "forward_number", "label_format",
            "label_path", "cost", "currency", "status",
            "carrier_response_json",
        ]
        values = [
            label.order_id, label.package_sn, label.carrier,
            label.service_level, label.tracking_number, label.forward_number,
            label.label_format.value, label.label_path, label.cost,
            label.currency, label.status, label.carrier_response_json,
        ]
        cursor = self.conn.execute(
            f"INSERT INTO labels ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
            values,
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_labels_for_order(self, order_id: int) -> list[Label]:
        rows = self.conn.execute(
            "SELECT * FROM labels WHERE order_id = ? ORDER BY created_at DESC",
            (order_id,),
        ).fetchall()
        return [self._row_to_label(r) for r in rows]

    def update_label_status(self, label_id: int, status: str):
        self.conn.execute(
            "UPDATE labels SET status = ? WHERE id = ?", (status, label_id)
        )
        self.conn.commit()

    def _row_to_label(self, row: sqlite3.Row) -> Label:
        return Label(
            id=row["id"],
            order_id=row["order_id"],
            package_sn=row["package_sn"] or "",
            carrier=row["carrier"],
            service_level=row["service_level"] or "",
            tracking_number=row["tracking_number"] or "",
            forward_number=row["forward_number"] or "",
            label_format=LabelFormat(row["label_format"] or "PDF"),
            label_path=row["label_path"] or "",
            cost=row["cost"] or 0.0,
            currency=row["currency"] or "USD",
            status=row["status"] or "generated",
            carrier_response_json=row["carrier_response_json"] or "",
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
        )

    # ── tracking log ────────────────────────────────────────────

    def log_tracking_writeback(
        self,
        label_id: int,
        package_sn: str,
        action: str,
        response_code: int,
        response_json: str,
        success: bool,
    ):
        self.conn.execute(
            """INSERT INTO tracking_log
               (label_id, package_sn, action, sellfox_response_code,
                sellfox_response_json, success)
               VALUES (?,?,?,?,?,?)""",
            (label_id, package_sn, action, response_code, response_json, int(success)),
        )
        self.conn.commit()

    # ── rule log ────────────────────────────────────────────────

    def log_rule_match(
        self, order_id: int, rule_name: str, carrier: str,
        service: str, reason: str,
    ):
        self.conn.execute(
            """INSERT INTO rule_log (order_id, rule_name, carrier_selected,
               service_selected, match_reason) VALUES (?,?,?,?,?)""",
            (order_id, rule_name, carrier, service, reason),
        )
        self.conn.commit()
