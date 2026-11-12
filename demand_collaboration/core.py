"""Conservative, transaction-safe collaboration ledger (stdlib only)."""
from __future__ import annotations

from contextlib import closing, contextmanager
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3


class DomainError(Exception):
    def __init__(self, status_code, code, message=None):
        self.status_code, self.code = status_code, code
        self.message = message or code
        super().__init__(self.message)


def fail(code, message, status=422):
    raise DomainError(status, code, message)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(encoded(value).encode("utf-8")).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def text(value, field):
    if not isinstance(value, str) or not value.strip() or len(value) > 10000:
        fail("invalid_text", f"{field}必须提供非空文本")
    return value.strip()


def number(value, field, minimum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        fail("invalid_number", f"{field}必须是有限数值")
    if minimum is not None and value < minimum:
        fail("invalid_number", f"{field}不能小于{minimum}")
    return value


def day(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        fail("invalid_date", "日期必须是YYYY-MM-DD")


def period_end(row):
    return day(row["period_end"]) if "period_end" in row else day(row["week"]) + timedelta(days=6)


def fields(payload, required, optional=()):
    if not isinstance(payload, dict) or set(payload) - set(required) - set(optional) or set(required) - set(payload):
        fail("invalid_fields", "字段缺失或包含未支持字段")


def json_object(value, field, limit=20000):
    if not isinstance(value, dict):
        fail("invalid_context", f"{field}必须是对象")
    try:
        size = len(encoded(value))
    except (TypeError, ValueError):
        fail("invalid_context", f"{field}必须是可序列化对象")
    if size > limit:
        fail("invalid_context", f"{field}过大")
    return value


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS baselines(version TEXT PRIMARY KEY, hash TEXT NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS proposals(id TEXT PRIMARY KEY, hash TEXT NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS publications(id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY, actor TEXT NOT NULL, action TEXT NOT NULL, entity TEXT NOT NULL, at TEXT NOT NULL, detail TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit(entity);
            """)
            conn.execute("INSERT OR IGNORE INTO settings VALUES('schema_version','1')")
            conn.commit()

    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=20)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _write(self):
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _audit(conn, actor, action, entity, detail):
        conn.execute("INSERT INTO audit(actor,action,entity,at,detail) VALUES(?,?,?,?,?)",
                     (actor, action, entity, now(), encoded(detail)))

    @staticmethod
    def _baseline(conn):
        row = conn.execute("SELECT b.data FROM baselines b JOIN settings s ON s.value=b.version WHERE s.key='baseline'").fetchone()
        return json.loads(row[0]) if row else None

    @staticmethod
    def _proposals(conn):
        return [json.loads(r[0]) for r in conn.execute("SELECT data FROM proposals ORDER BY rowid")]

    def set_baseline(self, payload):
        fields(payload, ("version", "as_of", "demo", "rows"))
        version = text(payload["version"], "version")
        day(payload["as_of"])
        if not isinstance(payload["demo"], bool) or not isinstance(payload["rows"], list) or not payload["rows"]:
            fail("invalid_baseline", "基准必须注明演示状态并包含商品")
        seen = set()
        intervals = {}
        for row in payload["rows"]:
            fields(row, ("id", "product_id", "sku", "name", "branch", "unit", "week", "baseline_qty"),
                   ("history", "inventory_qty", "supply_note", "period_end", "physical_form",
                    "tongtong_sku", "en_item_code", "context"))
            for key in ("id", "product_id", "sku", "name", "unit"):
                text(row[key], key)
            if row["id"] in seen:
                fail("duplicate_row", "商品期间标识重复")
            seen.add(row["id"])
            if row["branch"] not in ("USNJ", "USTX", "PL"):
                fail("unknown_branch", "未支持的分公司")
            start = day(row["week"])
            end = period_end(row)
            if "period_end" not in row and start.weekday() != 0:
                fail("invalid_week", "周期间必须从星期一开始")
            if end < start:
                fail("invalid_period", "期间结束不能早于开始")
            if "physical_form" in row:
                text(row["physical_form"], "physical_form")
            target = (row["product_id"], row["branch"], row["unit"], row.get("physical_form", ""))
            for previous_start, previous_end in intervals.get(target, []):
                if start <= previous_end and previous_start <= end:
                    fail("overlapping_horizons", "同一商品仓池形态的预测窗口重叠，须选择单一窗口")
            intervals.setdefault(target, []).append((start, end))
            number(row["baseline_qty"], "基准需求", 0)
            if "history" in row:
                if not isinstance(row["history"], list):
                    fail("invalid_history", "历史销量应为列表")
                for value in row["history"]:
                    if value is not None:
                        number(value, "历史销量", 0)
            if row.get("inventory_qty") is not None:
                number(row["inventory_qty"], "库存", 0)
            if "supply_note" in row and not isinstance(row["supply_note"], str):
                fail("invalid_supply_note", "供给备注必须是文本")
            for key in ("tongtong_sku", "en_item_code"):
                if row.get(key) is not None:
                    text(row[key], key)
            if "context" in row:
                json_object(row["context"], "context")
        content_hash = digest(payload)
        with self._write() as conn:
            current = self._baseline(conn)
            if current and day(payload["as_of"]) < day(current["as_of"]):
                fail("baseline_as_of_regression", "新基准数据时点不能早于当前基准", 409)
            existing = conn.execute("SELECT hash FROM baselines WHERE version=?", (version,)).fetchone()
            if existing and existing[0] != content_hash:
                fail("baseline_immutable", "相同基准版本内容不可改变", 409)
            conn.execute("INSERT OR IGNORE INTO baselines VALUES(?,?,?)", (version, content_hash, encoded(payload)))
            conn.execute("INSERT OR REPLACE INTO settings VALUES('baseline',?)", (version,))
            self._audit(conn, "system", "baseline_loaded", version, {"sha256": content_hash})
        return self.state()["baseline"]

    def state(self):
        with closing(self._connect()) as conn:
            return {"baseline": self._baseline(conn), "proposals": self._proposals(conn),
                    "publications": [json.loads(r[0]) for r in conn.execute(
                        "SELECT data FROM publications ORDER BY rowid DESC LIMIT 20")],
                    "audit": [dict(r) for r in conn.execute(
                        "SELECT * FROM (SELECT * FROM audit ORDER BY seq DESC LIMIT 500) ORDER BY seq")]}

    def record_audit(self, actor, action, entity, detail):
        with self._write() as conn:
            self._audit(conn, text(actor, "actor"), action, entity, detail)

    def submit(self, payload, actor):
        fields(payload, ("id", "row_id", "event_id", "kind", "value", "start", "end", "reason", "evidence", "baseline_version"))
        actor = text(actor, "提交人")
        for key in ("id", "row_id", "event_id", "reason", "evidence", "baseline_version"):
            text(payload[key], key)
        kind = payload["kind"]
        if kind not in ("delta", "total", "percent", "event_only"):
            fail("unknown_kind", "未支持的调整语义")
        if kind == "event_only":
            if payload["value"] is not None:
                fail("event_value", "只报事件时数量必须留空")
        else:
            number(payload["value"], "调整值", 0 if kind == "total" else -100 if kind == "percent" else None)
        start, end = day(payload["start"]), day(payload["end"])
        content_hash = digest({"actor": actor, "payload": payload})
        with self._write() as conn:
            existing = conn.execute("SELECT hash,data FROM proposals WHERE id=?", (payload["id"],)).fetchone()
            if existing:
                if existing[0] != content_hash:
                    fail("idempotency_conflict", "相同提交ID的内容或提交人不同", 409)
                return json.loads(existing[1])
            baseline = self._baseline(conn)
            if not baseline or baseline["version"] != payload["baseline_version"]:
                fail("stale_baseline", "基准已变化，请重新确认", 409)
            row = next((r for r in baseline["rows"] if r["id"] == payload["row_id"]), None)
            if not row:
                fail("unknown_row", "商品期间不在当前范围")
            if kind == "event_only":
                if start < day(row["week"]) or end > period_end(row) or end < start:
                    fail("event_period_outside_baseline", "事件日期须位于源预测期间内且结束不早于开始")
            elif start != day(row["week"]) or end != period_end(row):
                fail("partial_period_unsupported", "首版仅接受与源预测完全对齐的期间，不自动拆分周/月")
            result = dict(payload, author=actor, status="submitted", revision=1, created_at=now())
            conn.execute("INSERT INTO proposals VALUES(?,?,?)", (payload["id"], content_hash, encoded(result)))
            self._audit(conn, actor, "submitted", payload["id"], payload)
            return result

    @staticmethod
    def _adjust(row, proposal):
        base, value, kind = row["baseline_qty"], proposal["value"], proposal["kind"]
        if kind == "event_only":
            fail("unquantified_event", "事件影响尚未定量，不可批准成数值需求")
        result = value if kind == "total" else base + value if kind == "delta" else base * (1 + value / 100)
        return number(result, "调整后需求", 0)

    def decide(self, id, status, revision, actor, role, reason):
        if role != "reviewer":
            fail("reviewer_required", "仅需求审核人可裁决", 403)
        actor, reason = text(actor, "审核人"), text(reason, "审核理由")
        if status not in ("approved", "rejected", "cancelled"):
            fail("invalid_decision", "未支持的审核动作")
        with self._write() as conn:
            record = conn.execute("SELECT data FROM proposals WHERE id=?", (id,)).fetchone()
            if not record:
                fail("not_found", "提案不存在", 404)
            p = json.loads(record[0])
            if isinstance(revision, bool) or not isinstance(revision, int) or p["revision"] != revision:
                fail("revision_conflict", "记录已被修改，请刷新", 409)
            if p["status"] not in ("submitted", "approved") or (p["status"] == "approved" and status != "cancelled"):
                fail("invalid_transition", "当前状态不允许此操作", 409)
            if status == "approved":
                if actor == p["author"]:
                    fail("self_approval", "不能审核自己的提案", 403)
                baseline = self._baseline(conn)
                if not baseline or p["baseline_version"] != baseline["version"]:
                    fail("stale_baseline", "提案基准已失效，请重新提交", 409)
                row = next(r for r in baseline["rows"] if r["id"] == p["row_id"])
                self._adjust(row, p)
                for other in self._proposals(conn):
                    if other["id"] != id and other["status"] == "approved" and other["baseline_version"] == p["baseline_version"] and other["row_id"] == p["row_id"]:
                        fail("overlapping_proposal", "同一商品期间已有批准提案，须先撤销或裁决重叠", 409)
            p.update(status=status, revision=revision + 1, reviewer=actor, decision_reason=reason, updated_at=now())
            conn.execute("UPDATE proposals SET data=? WHERE id=?", (encoded(p), id))
            self._audit(conn, actor, status, id, {"reason": reason, "revision": p["revision"]})
            return p

    def publish(self, baseline_version, as_of, actor, role):
        if role != "reviewer":
            fail("reviewer_required", "仅需求审核人可发布", 403)
        actor = text(actor, "发布人")
        as_of_day = day(as_of)
        with self._write() as conn:
            baseline = self._baseline(conn)
            if not baseline or baseline_version != baseline["version"]:
                fail("stale_baseline", "只能发布当前基准", 409)
            if as_of_day < day(baseline["as_of"]):
                fail("invalid_as_of", "发布时间不能早于基准数据时点")
            proposals = [p for p in self._proposals(conn) if p["baseline_version"] == baseline_version]
            if any(p["status"] == "submitted" for p in proposals):
                fail("unresolved_proposals", "仍有未裁决提案；请接受、拒绝或撤回后再发布（仅报事件需定量或驳回）", 409)
            approved = {p["row_id"]: p for p in proposals if p["status"] == "approved"}
            rows = []
            for original in baseline["rows"]:
                row = dict(original)
                row["expired"] = as_of_day > period_end(row)
                row["period_state"] = "expired" if row["expired"] else "in_progress" if as_of_day > day(row["week"]) else "future"
                row["quantity_scope"] = "entire_source_period"
                row["needs_remaining_period_forecast"] = row["period_state"] == "in_progress"
                row["replenishment_eligible"] = False
                p = approved.get(row["id"]) if not row["expired"] else None
                row.update(adjusted_qty=self._adjust(row, p) if p else row["baseline_qty"],
                           proposal_ids=[p["id"]] if p else [],
                           status="expired" if row["expired"] else "adjusted" if p else "baseline_unreviewed")
                rows.append(row)
            result = {"schema": "operator-demand/v1", "baseline_version": baseline_version,
                      "baseline_sha256": digest(baseline), "as_of": as_of, "demo": baseline["demo"],
                      "rows": rows, "proposal_decisions": proposals, "published_by": actor,
                      "service_certified": False, "assumptions": ["point_scenario_not_calibrated", "not_purchase_instructions", "exact_source_periods_only"]}
            content_hash = digest(result)
            result.update(id=content_hash, sha256=content_hash)
            existing = conn.execute("SELECT data FROM publications WHERE id=?", (content_hash,)).fetchone()
            if existing:
                return json.loads(existing[0])
            result["published_at"] = now()
            conn.execute("INSERT INTO publications VALUES(?,?)", (content_hash, encoded(result)))
            self._audit(conn, actor, "published", content_hash, {"baseline_version": baseline_version})
            return result

    def publication(self, id):
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT data FROM publications WHERE id=?", (id,)).fetchone()
            if not row:
                fail("not_found", "发布快照不存在", 404)
            return json.loads(row[0])
