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
                CREATE TABLE IF NOT EXISTS recommendation_snapshots(id TEXT PRIMARY KEY, sha256 TEXT NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY, actor TEXT NOT NULL, action TEXT NOT NULL, entity TEXT NOT NULL, at TEXT NOT NULL, detail TEXT NOT NULL);
            """)

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

    @staticmethod
    def _recommendation(conn):
        row = conn.execute(
            "SELECT r.data FROM recommendation_snapshots r JOIN settings s ON s.value=r.id "
            "WHERE s.key='recommendation_snapshot'").fetchone()
        return json.loads(row[0]) if row else None

    def set_recommendation_snapshot(self, payload, actor="system"):
        """Append an immutable read-only recommendation snapshot.

        Never touches the D5 baseline pointer and always records the two
        eligibility flags as false, whatever the caller supplies.
        """
        from .recommendation import REPLENISHMENT_ELIGIBLE, SCHEMA, SERVICE_CERTIFIED
        actor = text(actor, "导入人")
        if not isinstance(payload, dict):
            fail("invalid_recommendation", "建议快照必须是对象")
        if payload.get("schema") != SCHEMA:
            fail("invalid_recommendation", "建议快照schema不匹配")
        rows = payload.get("rows")
        if not isinstance(rows, list) or not rows:
            fail("invalid_recommendation", "建议快照必须包含建议行")
        for key in ("source_sha256", "as_of", "input_count", "accepted_count",
                    "rejected_count", "skipped_count", "reconciled"):
            if key not in payload:
                fail("invalid_recommendation", f"建议快照缺少{key}")
        day(payload["as_of"])
        for key in ("input_count", "accepted_count", "rejected_count", "skipped_count"):
            value = payload[key]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                fail("invalid_recommendation", f"{key}必须是非负整数")
        if payload["accepted_count"] != len(rows):
            fail("invalid_recommendation", "accepted_count与建议行数不一致")
        if payload["input_count"] != payload["accepted_count"] + payload["rejected_count"] + payload["skipped_count"]:
            fail("recommendation_not_reconciled", "建议快照数量不守恒")
        if payload["reconciled"] is not True:
            fail("recommendation_not_reconciled", "建议快照未标记守恒")
        if payload.get("service_certified") not in (False, None) or payload.get("replenishment_eligible") not in (False, None):
            fail("invalid_eligibility", "建议快照不得具备服务认证或补货资格")
        ids, keys = set(), set()
        for row in rows:
            if not isinstance(row, dict):
                fail("invalid_recommendation", "建议行必须是对象")
            for key in ("row_id", "sku", "uom", "action", "period_start", "period_end",
                        "source_row", "source_hash"):
                if not isinstance(row.get(key), (str, int)):
                    fail("invalid_recommendation", f"建议行缺少{key}")
            text(row["sku"], "sku")
            text(row["uom"], "uom")
            text(row["action"], "action")
            start, end = day(row["period_start"]), day(row["period_end"])
            if end < start:
                fail("invalid_period", "建议期间结束早于开始")
            identity = (row["row_id"], row["sku"], row.get("customer"), row.get("warehouse"),
                        row.get("physical_form"), row["uom"], row["period_start"], row["period_end"])
            if identity in keys:
                fail("duplicate_identity", "建议快照存在重复身份键")
            keys.add(identity)
            if row["row_id"] in ids:
                fail("duplicate_row_id", "建议快照存在重复行标识")
            ids.add(row["row_id"])
            if row.get("service_certified") not in (False, None) or row.get("replenishment_eligible") not in (False, None):
                fail("invalid_eligibility", "建议行不得具备服务认证或补货资格")
        content = {key: value for key, value in payload.items()
                   if key not in ("snapshot_id", "sha256", "imported_at", "imported_by")}
        content_hash = digest(content)
        if payload.get("snapshot_id") not in (None, content_hash) or payload.get("sha256") not in (None, content_hash):
            fail("recommendation_immutable", "快照哈希与内容不一致", 409)
        record = dict(content, snapshot_id=content_hash, sha256=content_hash,
                      imported_by=actor, imported_at=now(),
                      service_certified=SERVICE_CERTIFIED,
                      replenishment_eligible=REPLENISHMENT_ELIGIBLE, read_only=True)
        with self._write() as conn:
            existing = conn.execute("SELECT sha256,data FROM recommendation_snapshots WHERE id=?",
                                    (content_hash,)).fetchone()
            if existing:
                if existing[0] != content_hash:
                    fail("recommendation_immutable", "相同快照标识内容不可改变", 409)
                return json.loads(existing[1])
            conn.execute("INSERT INTO recommendation_snapshots VALUES(?,?,?)",
                         (content_hash, content_hash, encoded(record)))
            conn.execute("INSERT OR REPLACE INTO settings VALUES('recommendation_snapshot',?)",
                         (content_hash,))
            self._audit(conn, actor, "recommendation_snapshot_loaded", content_hash,
                        {"source_sha256": payload["source_sha256"], "as_of": payload["as_of"],
                         "accepted_count": payload["accepted_count"]})
        return record

    def recommendation(self, snapshot_id):
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT data FROM recommendation_snapshots WHERE id=?",
                               (snapshot_id,)).fetchone()
            if not row:
                fail("not_found", "建议快照不存在", 404)
            return json.loads(row[0])

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
                   ("history", "inventory_qty", "supply_note", "period_end", "physical_form"))
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
        content_hash = digest(payload)
        with self._write() as conn:
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
                    "recommendation": self._recommendation(conn),
                    "publications": [json.loads(r[0]) for r in conn.execute("SELECT data FROM publications ORDER BY rowid DESC")],
                    "audit": [dict(r) for r in conn.execute("SELECT * FROM audit ORDER BY seq")]}

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
                fail("unresolved_proposals", "仍有未裁决提案；接受、拒绝或留明待估后再发布", 409)
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
