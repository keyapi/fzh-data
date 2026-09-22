# -*- coding: utf-8 -*-
"""出货计划（Delivery Plan）保存/扫码性能 —— 只读探针（测试站 / 生产通用）

背景：`delivery_plan.py` 的性能改造（10 处补丁）已完成并验证于测试机，等待同步到生产。
本脚本用于：
  * `preflight` —— 只读体检：判断目标站点跑的是**旧码还是新码**、行数构成、
    无菲号行是否会触发 Error Log 写入（该逻辑按用户要求保留，故探针必须避开/兜底）。
  * `probe`     —— 计时 + 逐行 dump：`doc.run_method("create_items_from_planned_qties")`
    （**不 save、不 submit**）→ 记录耗时与输出，供「改造前 vs 改造后」逐行对拍。

只读保证（生产绝不允许改数据）：
  1. 只调用该方法，绝不 save / submit；
  2. ⚠️ 实测结论（测试站 rollback_check 自检）：`frappe.log_error` **会立即提交**，
     `frappe.db.rollback()` **丢不掉**它。所以「无菲号行余额为 0 写 Error Log」这条路径
     （delivery_plan.py:660，用户要求保留）**一旦触发就是真写入**。
     → `probe --site prod` 会先对每个计划做 preflight，预测会写 Error Log 就**直接拒绝执行**
       （除非显式传 --allow-error-log-writes）。
  3. 调用后核对 `Delivery Plan.modified` 未变（生产 Error Log 总行数随时在涨，**不能**当判据），
     并按时段精确识别「本次 probe 新增的 Error Log 行」供 `--cleanup-logs` 删除；
  4. 临时 Server Script 用 `zz_` 前缀，执行完立即删除，并复查残留为 0。

用法：
  python EN_API/dp_perf_probe.py rollback_check --site test
  python EN_API/dp_perf_probe.py preflight     --site prod --plan 2609006 2608011
  python EN_API/dp_perf_probe.py probe         --site prod --plan 2609006 --label before
  python EN_API/dp_perf_probe.py residue       --site prod
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from urllib.parse import quote

import requests

sys.stdout.reconfigure(encoding="utf-8")

_DIR = Path(__file__).resolve().parent
OUT_DIR = _DIR / "out"

SITES = {
    "prod": "https://erpnext.vilavi.cn",
    "test": "https://ensh.vilavi.cn",
}
SITE_LABEL = {"prod": "生产", "test": "测试站"}

SERVER_SCRIPT = "zz_dp_perf_probe"
METHOD = "zz_dp_perf_probe"
# 「无菲号行余额为 0」写的那条 Error Log 的 method（frappe 把 title 存进 method 字段）
DEBUG_LOG_METHOD = "出货计划: 严格模式无TN行 actual_qty=0（排查用）"

# 临时 Server Script 正文（同 dn_2600079_fix.py 的模式：script_type=API + api_method 注册）
# 注意：Server Script 沙箱里**不能用 import**，只能用 frappe.* 与内置函数。
SERVER_BODY = '''
plan_name = frappe.form_dict.get("plan")
mode = frappe.form_dict.get("mode") or "probe"


def error_log_count():
    """Error Log 总行数（两种写法，取可用的那个）。"""
    try:
        return frappe.db.count("Error Log")
    except Exception:
        return frappe.db.sql("select count(*) from `tabError Log`")[0][0]


def now_stamp():
    """返回可相减的时间戳；沙箱里没有 import time，优先用 frappe 的 datetime。"""
    try:
        return frappe.utils.now_datetime()
    except Exception:
        return None


def detect_code_version(plan_name):
    """判断站点上跑的是旧码还是新码（沙箱禁止 `_` 属性访问，只能靠行为差异）。

    性能补丁把 `allocate_actual_qty` 的签名从 `(self)` 改成 `(self, stock_map=None)`。
    做法：取一份**清空 item_qties 的临时副本**（死循环为空 → 立刻返回，不查任何库存），
    传 `stock_map={}` 调用它 —— 新码接受该关键字参数；旧码会抛 TypeError。
    副本从不保存，对数据无影响。返回 {"version": "new"/"old"/"unknown", "detail": ...}
    """
    try:
        scratch = frappe.get_doc("Delivery Plan", plan_name)
        scratch.set("item_qties", [])
        scratch.allocate_actual_qty(stock_map={})
        return {"version": "new", "detail": None}
    except TypeError as e:
        return {"version": "old", "detail": str(e)[:200]}
    except Exception as e:
        return {"version": "unknown", "detail": str(e)[:200]}


# rollback 自检：不需要任何计划文档
# recent_plans 只用 SELECT，不需要任何计划文档
if mode == "recent_plans":
    # 最近被改动过的计划 = 刚刚有人在保存的（保存会更新 modified）
    rows = frappe.db.sql(
        "SELECT p.name AS plan, p.docstatus AS docstatus, p.modified AS modified,"
        "       p.owner AS owner,"
        "       (SELECT COUNT(*) FROM `tabDelivery Plan Item Qty` q"
        "         WHERE q.parent = p.name) AS total,"
        "       (SELECT COUNT(*) FROM `tabDelivery Plan Item Qty` q"
        "         WHERE q.parent = p.name"
        "           AND IFNULL(TRIM(q.tracking_number), '') <> '') AS tn"
        "  FROM `tabDelivery Plan` p"
        " WHERE p.docstatus < 2"
        " ORDER BY p.modified DESC"
        " LIMIT 12",
        as_dict=True,
    )
    frappe.response["data"] = {"plans": rows}
elif mode == "find_plans":
    # 挑「规模大且没有无菲号行」的计划来跑 probe：无菲号行为 0 → 不可能触达 Error Log 写入
    rows = frappe.db.sql(
        "SELECT q.parent AS plan, p.docstatus AS docstatus, p.modified AS modified,"
        "       COUNT(*) AS total,"
        "       SUM(CASE WHEN IFNULL(TRIM(q.tracking_number), '') = '' THEN 1 ELSE 0 END) AS untagged"
        "  FROM `tabDelivery Plan Item Qty` q"
        "  JOIN `tabDelivery Plan` p ON p.name = q.parent"
        " WHERE p.docstatus < 2"
        " GROUP BY q.parent, p.docstatus, p.modified"
        " ORDER BY total DESC"
        " LIMIT 40",
        as_dict=True,
    )
    frappe.response["data"] = {"plans": rows}
elif mode == "rollback_check":
    # 故意写一条 Error Log，再看 rollback 能否把它丢掉。
    # 生产探针可能触达「无菲号行余额为 0 写 Error Log」的路径，必须先证明兜底有效。
    c0 = error_log_count()
    write_err = None
    try:
        frappe.log_error(message="zz_dp_probe rollback selftest",
                         title="zz_dp_probe rollback selftest")
    except Exception as e:
        write_err = str(e)[:300]
    c1 = error_log_count()
    frappe.db.rollback()
    c2 = error_log_count()
    frappe.response["data"] = {
        "before": c0,
        "after_write": c1,
        "after_rollback": c2,
        "write_error": write_err,
        "write_landed": c1 > c0,
        "rollback_effective": c2 == c0,
    }
else:
    doc = frappe.get_doc("Delivery Plan", plan_name)

    # 注意：沙箱在 AST 层拦截一切 `_` 开头的属性访问（`getattr` 也被包装成取不到），
    # 所以没法直接探测新码新增的 _dp_pp_child_index / _dp_so_detail_warehouse；
    # 版本判定改走行为差异 —— 见 detect_code_version()。
    qty_rows = doc.item_qties or []
    tn_rows = [r for r in qty_rows if (r.tracking_number or "").strip()]
    untagged_rows = [
        r for r in qty_rows
        if not (r.tracking_number or "").strip() and (r.item_code or "").strip()
    ]

    code_version = detect_code_version(plan_name)

    info = {
        "plan": plan_name,
        "site_mode": mode,
        "code_version": code_version["version"],
        "code_version_detail": code_version["detail"],
        "docstatus": doc.docstatus,
        "is_strict_so_source": doc.is_strict_so_source,
        "item_qties_rows": len(qty_rows),
        "items_rows": len(doc.items or []),
        "tn_rows": len(tn_rows),
        "untagged_rows": len(untagged_rows),
        "modified_before": str(doc.modified),
        "error_log_before": error_log_count(),
    }

    if mode == "preflight":
        # 无菲号行是否会触发「余额为 0 写 Error Log」——逐行复算空菲号余额（只读）
        bal_by_item = {}
        for r in untagged_rows:
            ic = (r.item_code or "").strip()
            if ic not in bal_by_item:
                bal_by_item[ic] = frappe.utils.flt(doc.get_strict_empty_tracking_sle_balance(ic))
        zero_items = {ic: b for ic, b in bal_by_item.items() if b == 0}
        info["untagged_distinct_items"] = len(bal_by_item)
        info["untagged_zero_balance_items"] = zero_items
        info["untagged_zero_balance_rows"] = len(
            [r for r in untagged_rows if (r.item_code or "").strip() in zero_items]
        )
        frappe.response["data"] = info
    elif mode == "hotpath":
        # 只读热点计时：不跑 create_items_from_planned_qties，因此零写入。
        # get_strict_so_warehouse_and_stock 只做 frappe.get_doc(..., for_update=False) + 查询。
        #
        # 量两条路，对照「改造前 vs 改造后」在**同一张计划**上的每行成本：
        #   legacy    —— 无预加载逐条调用 = 旧码在 _allocate_actual_qty_strict 里每行重复付的代价
        #   preloaded —— 复用主循环的 TN/WO/PP 预加载 + batch_sle_cache = 新码实际付的代价
        #                （主循环那段预加载本来就是既有逻辑，不是本次 10 处补丁加的）
        tns = []
        for r in qty_rows:
            t = (r.tracking_number or "").strip()
            if t and t not in tns:
                tns.append(t)

        # 注意：旧码是【按行】重复调用的（同一菲号出现 N 行就付 N 次代价），
        # 所以计时必须按「行」遍历、保留重复，否则会低估旧码成本。
        tn_seq = []
        for r in qty_rows:
            t = (r.tracking_number or "").strip()
            if t:
                tn_seq.append(t)

        # ── 预加载（照抄主循环 create_items_from_planned_qties 的做法）──
        p0 = now_stamp()
        tn_rows = frappe.get_all(
            "Tracking Number", filters={"name": ["in", tns]},
            fields=["name", "work_order", "item_code", "so_materials"],
        ) if tns else []
        tn_doc_map = {r.name: r for r in tn_rows}

        wo_names = []
        for r in tn_rows:
            w = r.work_order
            if w and w not in wo_names:
                wo_names.append(w)
        wo_rows = frappe.get_all(
            "Work Order", filters={"name": ["in", wo_names]},
            fields=["name", "production_plan", "production_plan_item",
                    "production_plan_sub_assembly_item", "production_item"],
        ) if wo_names else []
        wo_doc_map = {r.name: r for r in wo_rows}

        pp_docs_map = {}
        for r in wo_rows:
            pn = r.production_plan
            if pn and pn not in pp_docs_map:
                try:
                    pp_docs_map[pn] = frappe.get_doc("Production Plan", pn, for_update=False)
                except Exception:
                    pass
        p1 = now_stamp()

        # ── 第一条路：无预加载（旧码每【行】的代价）──
        legacy = []
        l_ok = 0
        l_none = 0
        l_err = 0
        l_first_err = None
        for t in tn_seq:
            a = now_stamp()
            found = None
            try:
                si = doc.get_strict_so_warehouse_and_stock(t)
                found = si is not None
                if si:
                    l_ok = l_ok + 1
                else:
                    l_none = l_none + 1
            except Exception as e:
                l_err = l_err + 1
                if l_first_err is None:
                    l_first_err = str(e)[:200]
            b = now_stamp()
            ms = (b - a).total_seconds() * 1000.0 if (a is not None and b is not None) else None
            legacy.append([t, ms, found])

        # ── 第二条路：带预加载（新码每【行】的代价）──
        pre = []
        sle_cache = {}
        n_ok = 0
        n_none = 0
        n_err = 0
        n_first_err = None
        for t in tn_seq:
            tn_doc = tn_doc_map.get(t)
            wo_doc = wo_doc_map.get(tn_doc.work_order) if (tn_doc and tn_doc.work_order) else None
            pp_doc = pp_docs_map.get(wo_doc.production_plan) if (wo_doc and wo_doc.production_plan) else None
            a = now_stamp()
            found = None
            try:
                si = doc.get_strict_so_warehouse_and_stock(
                    t, preloaded_tn_doc=tn_doc, preloaded_wo_doc=wo_doc,
                    preloaded_pp_doc=pp_doc, batch_sle_cache=sle_cache)
                found = si is not None
                if si:
                    n_ok = n_ok + 1
                else:
                    n_none = n_none + 1
            except Exception as e:
                n_err = n_err + 1
                if n_first_err is None:
                    n_first_err = str(e)[:200]
            b = now_stamp()
            ms = (b - a).total_seconds() * 1000.0 if (a is not None and b is not None) else None
            pre.append([t, ms, found])

        def agg(per):
            out = {"calls": len(per)}
            tot = None
            lo = None
            hi = None
            cnt = 0
            for row in per:
                v = row[1]
                if v is None:
                    continue
                cnt = cnt + 1
                if tot is None:
                    tot = v
                else:
                    tot = tot + v
                lo = v if (lo is None or v < lo) else lo
                hi = v if (hi is None or v > hi) else hi
            if cnt:
                out["avg_ms"] = tot / cnt
                out["min_ms"] = lo
                out["max_ms"] = hi
                out["sum_s"] = tot / 1000.0
            return out

        frappe.response["data"] = {
            "plan": plan_name,
            "code_version": code_version["version"],
            "tn_count": len(tns),
            "tn_rows": len(tn_seq),
            "preload": {
                "tn_rows": len(tn_rows), "wo_rows": len(wo_rows), "pp_docs": len(pp_docs_map),
                "setup_s": ((p1 - p0).total_seconds() if (p0 is not None and p1 is not None) else None),
            },
            "legacy": {"ok": l_ok, "none": l_none, "errors": l_err, "first_error": l_first_err,
                       "agg": agg(legacy), "per_tn": legacy},
            "preloaded": {"ok": n_ok, "none": n_none, "errors": n_err, "first_error": n_first_err,
                          "agg": agg(pre), "per_tn": pre},
        }
    else:
        # 服务端当前时间：给「清理本次 probe 新增 Error Log」当时刻下界（避免误删真人同时段写下的合法行）
        info["server_now"] = frappe.utils.now()
        t0 = now_stamp()
        doc.run_method("create_items_from_planned_qties")
        t1 = now_stamp()

        try:
            tables = [df.fieldname for df in doc.meta.get_table_fields()]
        except Exception:
            tables = ["items", "item_qties"]
        scalars = {k: v for k, v in doc.as_dict().items() if k not in tables}

        info["item_qties_rows_after"] = len(doc.item_qties or [])
        info["items_rows_after"] = len(doc.items or [])
        if t0 is not None and t1 is not None:
            info["elapsed_s"] = (t1 - t0).total_seconds()

        dump = {
            "items": [r.as_dict() for r in (doc.items or [])],
            "item_qties": [r.as_dict() for r in (doc.item_qties or [])],
        }

        # 兜底丢弃本次请求内的任何写入（Error Log），再核对确实没动过数据
        frappe.db.rollback()
        info["modified_after"] = str(
            frappe.db.get_value("Delivery Plan", plan_name, "modified")
        )
        info["error_log_after"] = error_log_count()

        frappe.response["data"] = {"info": info, "scalars": scalars, "dump": dump}
'''


def load_env() -> dict[str, str]:
    vals: dict[str, str] = {}
    for p in (_DIR / ".env", _DIR.parent / ".env"):
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, val = line.partition("=")
            val = val.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
                val = val[1:-1]
            vals.setdefault(k.strip(), val)
    return vals


class Client:
    def __init__(self, site: str) -> None:
        env = load_env()
        prefix = "PROD" if site == "prod" else "TEST"
        key = env.get(f"{prefix}_ERP_API_KEY", "")
        sec = env.get(f"{prefix}_ERP_API_SECRET", "")
        if not key or not sec:
            raise SystemExit(f"✗ 缺少 {prefix}_ERP_API_KEY / {prefix}_ERP_API_SECRET（EN_API/.env）")
        self.base = SITES[site]
        self.site = site
        self.s = requests.Session()
        self.s.headers["Authorization"] = f"token {key}:{sec}"

    def _req(self, method, path, **kw):
        kw.setdefault("timeout", (30, 600))
        return self.s.request(method, f"{self.base}{path}", **kw)

    def _check(self, r):
        """把 frappe 的错误信息摊平成人能读的（否则只剩一句 417 EXPECTATION FAILED）。"""
        if r.status_code < 400:
            return r
        try:
            err = r.json()
            msgs = err.get("_server_messages")
            readable = ""
            if msgs:
                try:
                    readable = " | ".join(
                        str(json.loads(m).get("message", m)) for m in json.loads(msgs))
                except Exception:  # noqa: BLE001
                    readable = str(msgs)
            exc = readable or err.get("exception") or err.get("exc") or json.dumps(err)
        except Exception:  # noqa: BLE001
            exc = r.text
        raise RuntimeError(f"{r.status_code} {exc}"[:2000])

    def _write(self, method, path, payload=None, params=None):
        kw: dict = {"headers": {"Content-Type": "application/json"}}
        if payload is not None:
            kw["data"] = json.dumps(payload)
        if params:
            kw["params"] = params
        return self._check(self._req(method, path, **kw)).json()

    def get_doc(self, dt, name):
        r = self._req("GET", f"/api/resource/{quote(dt, safe='')}/{quote(name, safe='')}")
        return self._check(r).json()["data"]

    def get_list(self, dt, filters=None, fields=None, limit=0, order_by=None):
        pr: dict[str, str] = {"limit_page_length": str(limit)}
        if filters is not None:
            pr["filters"] = json.dumps(filters)
        if fields is not None:
            pr["fields"] = json.dumps(fields)
        if order_by:
            pr["order_by"] = order_by
        r = self._req("GET", f"/api/resource/{quote(dt, safe='')}", params=pr)
        return self._check(r).json()["data"]

    def insert(self, dt, doc):
        return self._write("POST", f"/api/resource/{quote(dt, safe='')}", doc)["data"]

    def delete(self, dt, name):
        return self._write("DELETE", f"/api/resource/{quote(dt, safe='')}/{quote(name, safe='')}")

    def call(self, method, params):
        return self._write("POST", f"/api/method/{method}", params=params)["data"]


def ensure_script(c: Client) -> None:
    try:
        c.delete("Server Script", SERVER_SCRIPT)
    except Exception:  # noqa: BLE001
        pass
    c.insert("Server Script", {
        "doctype": "Server Script", "name": SERVER_SCRIPT,
        "script_type": "API", "api_method": METHOD,
        "script": SERVER_BODY, "disabled": 0, "allow_guest": 0,
    })


def drop_script(c: Client) -> None:
    try:
        c.delete("Server Script", SERVER_SCRIPT)
    except Exception:  # noqa: BLE001
        pass


def show_residue(c: Client) -> int:
    rows = c.get_list("Server Script", [["name", "like", "zz_%"]], ["name"], 0)
    print(f"\n[{SITE_LABEL[c.site]}] Server Script 里 `zz_%` 残留：{len(rows)} 个")
    for r in rows:
        print(f"   - {r['name']}")
    return len(rows)


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def md5_of(obj) -> str:
    return hashlib.md5(canonical(obj).encode("utf-8")).hexdigest()


def cmd_preflight(c: Client, plans: list[str]) -> None:
    for plan in plans:
        res = c.call(METHOD, {"mode": "preflight", "plan": plan})
        print(f"\n=== preflight 计划 {plan} ===")
        for k, v in res.items():
            print(f"   {k:<30} {v}")


def cmd_recent_plans(c: Client) -> None:
    res = c.call(METHOD, {"mode": "recent_plans"})
    print("\n=== 最近被改动过的计划（= 刚刚有人在保存的）===")
    print(f"{'计划':<12}{'总行':>6}{'菲号行':>8}{'无菲号':>8}   最后修改 / 操作人")
    for p in res["plans"]:
        total = int(p["total"]); tn = int(p["tn"])
        print(f"{p['plan']:<12}{total:>6}{tn:>8}{total-tn:>8}   {p['modified']} / {p['owner']}")


def cmd_find_plans(c: Client) -> None:
    res = c.call(METHOD, {"mode": "find_plans"})
    plans = res["plans"]
    print(f"\n=== 行数最大的 {len(plans)} 张计划（只读 SQL）===")
    print(f"{'计划':<12}{'行数':>6}{'无菲号':>8}  docstatus  可安全跑 probe")
    for p in plans:
        mark = "✓" if not p["untagged"] else "✗ 会写 Error Log"
        print(f"{p['plan']:<12}{p['total']:>6}{p['untagged']:>8}  {p['docstatus']:<10} {mark}")
    safe = [p for p in plans if not p["untagged"]]
    print("\n无菲号行 = 0（可安全 probe）的最大几张："
          + ", ".join(f"{p['plan']}({p['total']}行)" for p in safe[:6]))


def cmd_rollback_check(c: Client) -> None:
    res = c.call(METHOD, {"mode": "rollback_check", "plan": "skip"})
    print("\n=== rollback 自检（故意写 Error Log 再看能否丢掉）===")
    for k, v in res.items():
        print(f"   {k:<20} {v}")
    if not res["rollback_effective"]:
        print("\n✗ rollback 未能丢弃写入 —— 生产探针不能跑（或必须先保证不触达 Error Log 路径）")
    else:
        print("\n✓ rollback 有效：探针即使触达 Error Log 写入路径，也不会留下数据")


def recent_error_log_names(c: Client, limit: int = 60) -> set[str]:
    """最近若干条 Error Log 的名字（按 creation 倒序，用于跑前/跑后取差集，避开时区问题）。"""
    return {r["name"] for r in
            c.get_list("Error Log", [], ["name"], limit, order_by="creation desc")}


def probe(c: Client, plan: str) -> dict:
    return c.call(METHOD, {"mode": "probe", "plan": plan})


def cleanup_created_logs(c: Client, plan: str, names_before: set[str],
                         since: str | None) -> list[str]:
    """删掉本次 probe 新写出的 Error Log 行。四个条件全满足才删：
      ①名字在「跑后 - 跑前」差集里（差集按 creation 倒序取前 60 —— 跑期间新增的必然在内）
      ②method 是那条无菲号调试日志
      ③error 里点名了这张计划
      ④creation >= 本次 probe 的服务端起始时刻（否则可能删掉真人保存同名计划时写下的合法行）
    教训：漏掉 ④ 就会误删真人写的行（本会话发生过一次）。"""
    created = sorted(recent_error_log_names(c) - names_before)
    deleted: list[str] = []
    for name in created:
        d = c.get_doc("Error Log", name)
        creation = str(d.get("creation") or "")
        if (d.get("method") or "") != DEBUG_LOG_METHOD:
            print(f"     跳过 {name}（method 不匹配：{d.get('method')!r}）")
            continue
        if plan not in (d.get("error") or ""):
            print(f"     跳过 {name}（error 里没有计划号 {plan}）")
            continue
        if since and creation < since:
            print(f"     跳过 {name}（creation {creation} 早于本次 probe 起始 {since}，疑似真人写入）")
            continue
        c.delete("Error Log", name)
        deleted.append(name)
    return deleted


def cmd_hotpath(c: Client, plans: list[str], label: str) -> None:
    """只读热点计时：不跑 create_items_from_planned_qties，因此不产生任何写入。"""
    OUT_DIR.mkdir(exist_ok=True)
    rows_out = []
    for plan in plans:
        t0 = time.perf_counter()
        res = c.call(METHOD, {"mode": "hotpath", "plan": plan})
        wall = time.perf_counter() - t0
        out = OUT_DIR / f"dp_{c.site}_{plan}_{label}_hotpath.json"
        out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

        lg, pl, setup = res["legacy"], res["preloaded"], res["preload"]
        print(f"\n[{SITE_LABEL[c.site]}] 计划 {plan} 热点计时（{label}）  代码版本={res['code_version']}")
        print(f"   菲号行 {res['tn_rows']}（去重 {res['tn_count']} 个）"
              f" ｜ 预加载：TN {setup['tn_rows']} / WO {setup['wo_rows']}"
              f" / PP {setup['pp_docs']} 篇，一次性 {setup['setup_s']:.2f}s")
        print(f"   旧码那条路（无预加载，按行） : 平均 {lg['agg'].get('avg_ms'):.2f} ms/次"
              f" × {lg['agg'].get('calls')} 行 = {lg['agg'].get('sum_s'):.2f}s"
              f"（命中 {lg['ok']} / 无 {lg['none']} / 错 {lg['errors']}）")
        print(f"   新码那条路（带预加载，按行） : 平均 {pl['agg'].get('avg_ms'):.2f} ms/次"
              f" × {pl['agg'].get('calls')} 行 = {pl['agg'].get('sum_s'):.2f}s"
              f"（命中 {pl['ok']} / 无 {pl['none']} / 错 {pl['errors']}）")
        if lg["first_error"]:
            print(f"   旧路首个报错: {lg['first_error']}")
        if pl["first_error"]:
            print(f"   新路首个报错: {pl['first_error']}")
        print(f"   客户端往返 {wall:.2f}s ｜ 落盘 {out}")
        rows_out.append({"plan": plan, "label": label, "code_version": res["code_version"],
                         "tn_count": res["tn_count"], "preload": setup,
                         "legacy": lg["agg"], "preloaded": pl["agg"],
                         "legacy_hits": {"ok": lg["ok"], "none": lg["none"], "errors": lg["errors"]},
                         "preloaded_hits": {"ok": pl["ok"], "none": pl["none"], "errors": pl["errors"]},
                         "file": str(out)})

    man = OUT_DIR / f"dp_{c.site}_{label}_hotpath_summary.json"
    man.write_text(json.dumps(rows_out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n汇总：{man}")


def cmd_probe(c: Client, plans: list[str], label: str, allow_error_log: bool,
              cleanup_logs: bool) -> None:
    OUT_DIR.mkdir(exist_ok=True)

    # 生产安全闸：Error Log 写入无法回滚（实测），所以预测会触发就先拒绝
    for plan in plans:
        pre = c.call(METHOD, {"mode": "preflight", "plan": plan})
        risky = pre.get("untagged_zero_balance_rows", 0)
        print(f"   预检 {plan}：无菲号行 {pre['untagged_rows']}，"
              f"其中余额为 0（会写 Error Log）{risky} 行，代码版本 {pre['code_version']}")
        if risky and c.site == "prod" and not allow_error_log:
            raise SystemExit(
                f"✗ 计划 {plan} 有 {risky} 行无菲号且余额为 0 —— 跑 probe 会往生产的 Error Log 写 {risky} 行，"
                f"而 log_error 无法回滚。\n  换计划，或确认可接受后加 --allow-error-log-writes。"
            )

    summary = []
    for plan in plans:
        names_before = recent_error_log_names(c) if cleanup_logs else None
        t0 = time.perf_counter()
        res = c.call(METHOD, {"mode": "probe", "plan": plan})
        wall = time.perf_counter() - t0

        out = OUT_DIR / f"dp_{c.site}_{plan}_{label}.json"
        out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

        info = res["info"]
        dump = res["dump"]
        dump_md5 = md5_of(dump)
        scalars_md5 = md5_of(res["scalars"])

        modified_ok = info["modified_before"] == info["modified_after"]

        print(f"\n[{SITE_LABEL[c.site]}] 计划 {plan}（{label}）")
        print(f"   代码版本                   : {info['code_version']}"
              f"（{info.get('code_version_detail') or '无异常'}）")
        print(f"   行数                       : item_qties {info['item_qties_rows']}"
              f" → {info['item_qties_rows_after']}，items {info['items_rows']}"
              f" → {info['items_rows_after']}")
        print(f"   菲号行 / 无菲号行          : {info['tn_rows']} / {info['untagged_rows']}")
        print(f"   服务端耗时                 : {info.get('elapsed_s', '（沙箱不可用）')}"
              f"     客户端往返 {wall:.2f}s")
        print(f"   dump md5                   : {dump_md5}")
        print(f"   scalars md5                : {scalars_md5}")
        print(f"   数据未被改动               : modified {'OK' if modified_ok else '✗变了'}")
        print(f"   本次 probe 期间 Error Log  : +{info['error_log_after'] - info['error_log_before']} 行"
              f"（生产上该计数随时在涨，不能当判据；是否为本次所写另见清理结果）")

        deleted: list[str] = []
        if cleanup_logs:
            deleted = cleanup_created_logs(c, plan, names_before, info.get("server_now"))
            print(f"   已清理新增 Error Log       : {len(deleted)} 行 {deleted}")

        print(f"   落盘                       : {out}")
        summary.append({
            "plan": plan, "label": label,
            "code_version": info["code_version"],
            "elapsed_s": info.get("elapsed_s"), "wall_s": wall,
            "dump_md5": dump_md5, "scalars_md5": scalars_md5,
            "modified_unchanged": modified_ok,
            "error_log_delta": info["error_log_after"] - info["error_log_before"],
            "error_log_deleted": deleted,
            "file": str(out),
        })

    man = OUT_DIR / f"dp_{c.site}_{label}_summary.json"
    man.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n汇总：{man}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["preflight", "probe", "hotpath", "rollback_check",
                                    "find_plans", "recent_plans", "residue"])
    ap.add_argument("--site", choices=["prod", "test"], required=True)
    ap.add_argument("--plan", nargs="*", default=[])
    ap.add_argument("--label", default="run")
    ap.add_argument("--keep", action="store_true", help="保留临时 Server Script（默认删除）")
    ap.add_argument("--allow-error-log-writes", action="store_true",
                    help="生产上明知会写 Error Log 仍继续（不可回滚，慎用）")
    ap.add_argument("--cleanup-logs", action="store_true",
                    help="跑完把本次 probe 新增的 Error Log 行删掉（按名字差集 + method + 计划号精确匹配）")
    args = ap.parse_args()

    c = Client(args.site)

    if args.cmd == "residue":
        n = show_residue(c)
        return 0 if n == 0 else 1

    if args.cmd not in ("rollback_check", "find_plans", "recent_plans") and not args.plan:
        raise SystemExit("✗ 需要 --plan")

    ensure_script(c)
    print(f"[{SITE_LABEL[args.site]}] 已创建临时 Server Script {SERVER_SCRIPT}"
          f"（api_method={METHOD}）")
    try:
        if args.cmd == "preflight":
            cmd_preflight(c, args.plan)
        elif args.cmd == "hotpath":
            cmd_hotpath(c, args.plan, args.label)
        elif args.cmd == "rollback_check":
            cmd_rollback_check(c)
        elif args.cmd == "find_plans":
            cmd_find_plans(c)
        elif args.cmd == "recent_plans":
            cmd_recent_plans(c)
        else:
            cmd_probe(c, args.plan, args.label, args.allow_error_log_writes, args.cleanup_logs)
    finally:
        if args.keep:
            print(f"\n（--keep）临时脚本保留：{SERVER_SCRIPT}")
        else:
            drop_script(c)
            print(f"\n已删除临时 Server Script {SERVER_SCRIPT}")
            show_residue(c)
    return 0


if __name__ == "__main__":
    sys.exit(main())
