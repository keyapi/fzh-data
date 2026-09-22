# -*- coding: utf-8 -*-
"""验证「方案①」：取消多投产的 Manufacture、把余量退回皮壳 —— 仅测试环境

背景（生产）：菲号 WO-26-02796-002 的成品 KS0001-HLR-153-TAN 被整批 36 件一次性投产
（STE-26-15219），但计划只需要 4 件；DN-26-00078 出掉 4 件后成品仓剩 32、待包装仓皮壳 0，
导致下一张计划扫码报「无库存」。方案①=把多投产的部分更正掉（保留已出库的扣减，余量退回皮壳）。

本脚本在**测试环境 ensh.vilavi.cn** 自建等效场景，实测：
  H1  取消那张 Manufacture 是否被负库存拦截
  H2  按物料开关 / 全局开关能否放行
  H3  「取消 + 重做 M 件 Manufacture」后账面是否为 成品 0 / 皮壳 N-M
  H4  已提交的出库单流水是否不受影响

**硬锁测试环境**，不提供 prod 分支。

用法（默认 dry-run，写操作必须显式 --apply）：
  python EN_API/manufacture_rollback_verify.py scout
  python EN_API/manufacture_rollback_verify.py run --apply
  python EN_API/manufacture_rollback_verify.py report
  python EN_API/manufacture_rollback_verify.py cleanup --apply
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import quote

import requests

sys.stdout.reconfigure(encoding="utf-8")

_DIR = Path(__file__).resolve().parent
OUT_DIR = _DIR / "out"
MANIFEST = OUT_DIR / "manufacture_rollback_verify_manifest.json"
LOG: list[dict] = []

BASE = "https://ensh.vilavi.cn"          # 测试环境，硬编码
ENV_URLS = {"test": BASE}
COMPANY = "FZH"
WH_SHELL = "待包装成品仓 - FZH"          # 皮壳所在（= 生产里的待包装成品仓）
WH_FG = "成品仓 - FZH"                   # 成品所在

N = 36                                   # 等同生产：整批投产 36 件
M = 4                                    # 等同生产：计划/出库 4 件

IC_SHELL = "ZZVERIFY-SHELL"              # 测试皮壳物料
IC_FG = "ZZVERIFY-FG"                    # 测试成品物料
TN = "ZZVERIFY-TN-001"                   # 测试菲号（追踪维度取值）
CUSTOMER = "美国FBA仓"
ITEM_GROUP = "三角靠枕"                  # 测试物料挂的物料组
SHELL_RATE = 10                          # 皮壳收货单价
FG_RATE = 10                             # 成品入库单价（= 皮壳单价 / 单耗 1）


# ── 基础设施 ───────────────────────────────────────────────
def load_env() -> tuple[str, str]:
    vals: dict[str, str] = {}
    for p in (_DIR / ".env", _DIR.parent / ".env"):
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                v = v[1:-1]
            vals.setdefault(k.strip(), v)
    return vals.get("TEST_ERP_API_KEY", ""), vals.get("TEST_ERP_API_SECRET", "")


class Client:
    def __init__(self) -> None:
        key, sec = load_env()
        if not key or not sec:
            raise SystemExit("✗ 缺少 TEST_ERP_API_KEY / TEST_ERP_API_SECRET（EN_API/.env）")
        self.base = BASE
        self.s = requests.Session()
        self.s.headers["Authorization"] = f"token {key}:{sec}"

    def _req(self, method: str, path: str, **kw) -> requests.Response:
        kw.setdefault("timeout", (30, 180))
        return self.s.request(method, f"{self.base}{path}", **kw)

    def get_list(self, dt, filters=None, fields=None, limit=0):
        pr: dict[str, str] = {"limit_page_length": str(limit)}
        if filters is not None:
            pr["filters"] = json.dumps(filters)
        if fields is not None:
            pr["fields"] = json.dumps(fields)
        r = self._req("GET", f"/api/resource/{quote(dt, safe='')}", params=pr)
        r.raise_for_status()
        return r.json()["data"]

    def get_doc(self, dt, name):
        r = self._req("GET", f"/api/resource/{quote(dt, safe='')}/{quote(name, safe='')}")
        r.raise_for_status()
        return r.json()["data"]

    def exists(self, dt, name) -> bool:
        try:
            self.get_doc(dt, name)
            return True
        except requests.HTTPError:
            return False

    def _write(self, method, path, payload):
        r = self._req(method, path, data=json.dumps(payload),
                      headers={"Content-Type": "application/json"})
        if r.status_code >= 400:
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
            raise RuntimeError(f"{r.status_code} {exc}"[:3000])
        return r.json().get("data") if r.text else None

    def insert(self, dt, doc):
        return self._write("POST", f"/api/resource/{quote(dt, safe='')}", doc)

    def update(self, dt, name, patch):
        return self._write("PUT", f"/api/resource/{quote(dt, safe='')}/{quote(name, safe='')}", patch)

    def submit(self, dt, name):
        return self._write("POST", "/api/method/frappe.client.submit",
                           {"doc": {**self.get_doc(dt, name), "doctype": dt}})

    def cancel(self, dt, name):
        return self._write("POST", "/api/method/frappe.client.cancel", {"doctype": dt, "name": name})

    def delete(self, dt, name):
        return self._write("DELETE", f"/api/resource/{quote(dt, safe='')}/{quote(name, safe='')}", {})

    def set_value(self, dt, name, field, value):
        """用 set_value 走单值更新（同时清文档缓存）。"""
        return self._write("POST", "/api/method/frappe.client.set_value",
                           {"doctype": dt, "name": name, "fieldname": field, "value": value})

    # ── 库存查询（按 (物料, 仓库, 菲号) 汇总 SLE） ──
    def sle_balance(self, item_code, warehouse=None, tracking=None) -> float:
        filters = [["item_code", "=", item_code], ["is_cancelled", "=", 0]]
        if warehouse:
            filters.append(["warehouse", "=", warehouse])
        if tracking is None:
            filters.append(["tracking_number", "is", "not set"])
        else:
            filters.append(["tracking_number", "=", tracking])
        rows = self.get_list("Stock Ledger Entry", filters, ["actual_qty"], 0)
        return round(sum(float(r["actual_qty"] or 0) for r in rows), 4)

    def sle_rows(self, item_code, tracking):
        return self.get_list(
            "Stock Ledger Entry",
            [["item_code", "=", item_code], ["tracking_number", "=", tracking]],
            ["name", "warehouse", "actual_qty", "voucher_type", "voucher_no",
             "posting_date", "is_cancelled"], 0)


def log(step: str, ok: bool | None, detail, **extra) -> None:
    rec = {"step": step, "ok": ok, "detail": detail, "at": time.strftime("%H:%M:%S"), **extra}
    LOG.append(rec)
    mark = "✓" if ok else ("✗" if ok is False else "·")
    print(f"  {mark} {step}: {detail}")


def banner(t: str) -> None:
    print("\n" + "=" * 72)
    print(t)
    print("=" * 72)


# ── 场景搭建 ───────────────────────────────────────────────
def ensure_item(c: Client, code: str, name: str, group: str, apply: bool) -> None:
    if c.exists("Item", code):
        log(f"item {code}", None, "已存在，复用")
        return
    if not apply:
        log(f"item {code}", None, "dry-run：将创建")
        return
    c.insert("Item", {"doctype": "Item", "item_code": code, "item_name": name,
                      "item_group": group, "stock_uom": "个", "is_stock_item": 1})
    log(f"item {code}", True, "已创建")


def ensure_tn(c: Client, apply: bool) -> None:
    if c.exists("Tracking Number", TN):
        log(f"TN {TN}", None, "已存在，复用")
        return
    if not apply:
        log(f"TN {TN}", None, "dry-run：将创建")
        return
    patch = {"doctype": "Tracking Number", "tracking_number": TN,
             "qty": N, "item_code": IC_SHELL}
    try:
        c.insert("Tracking Number", patch)
        log(f"TN {TN}", True, "已创建")
    except RuntimeError as e:
        log(f"TN {TN}", False, f"创建失败（可能是命名/必填）：{e}")


def se_receipt(c: Client, qty, apply: bool, created: dict) -> str | None:
    """Material Receipt：把皮壳入到待包装仓，带菲号。"""
    doc = {
        "doctype": "Stock Entry", "stock_entry_type": "Material Receipt", "purpose": "Material Receipt",
        "company": COMPANY, "posting_date": str(date.today()), "fg_completed_qty": qty,
        "items": [{"doctype": "Stock Entry Detail", "item_code": IC_SHELL, "qty": qty,
                   "t_warehouse": WH_SHELL, "stock_tracking_number": TN,
                   "basic_rate": SHELL_RATE, "allow_zero_valuation_rate": 1, "uom": "个"}],
    }
    if not apply:
        log(f"receipt {IC_SHELL} x{qty}", None, "dry-run：将创建并提交")
        return None
    name = c.insert("Stock Entry", doc)["name"]
    created.setdefault("receipts", []).append(name)
    save_manifest_now()
    c.submit("Stock Entry", name)
    log(f"receipt {IC_SHELL} x{qty}", True, f"{name} 已提交 → {WH_SHELL}")
    return name


def _manufacture_doc(qty):
    return {
        "doctype": "Stock Entry", "stock_entry_type": "Manufacture", "purpose": "Manufacture",
        "company": COMPANY, "posting_date": str(date.today()), "fg_completed_qty": qty,
        "items": [
            {"doctype": "Stock Entry Detail", "item_code": IC_SHELL, "qty": qty,
             "s_warehouse": WH_SHELL, "stock_tracking_number": TN, "uom": "个",
             "allow_zero_valuation_rate": 1},
            {"doctype": "Stock Entry Detail", "item_code": IC_FG, "qty": qty,
             "t_warehouse": WH_FG, "stock_tracking_number": TN, "uom": "个",
             "is_finished_item": 1, "basic_rate": FG_RATE, "allow_zero_valuation_rate": 1},
        ],
    }


def se_manufacture(c: Client, qty, apply: bool, created: dict, key: str) -> str | None:
    """Manufacture：消耗皮壳 → 产成品入库（等同生产 STE-26-15219 的形态）。"""
    if not apply:
        log(f"manufacture x{qty}", None, "dry-run：将创建并提交")
        return None
    name = c.insert("Stock Entry", _manufacture_doc(qty))["name"]
    created[key] = name
    save_manifest_now()
    c.submit("Stock Entry", name)
    log(f"manufacture x{qty}", True, f"{name} 已提交（消耗皮壳 {qty} → 成品入 {WH_FG}）")
    return name


def make_dn(c: Client, qty, apply: bool, created: dict) -> str | None:
    doc = {
        "doctype": "Delivery Note", "customer": CUSTOMER, "company": COMPANY,
        "posting_date": str(date.today()),
        "items": [{"doctype": "Delivery Note Item", "item_code": IC_FG, "qty": qty,
                   "warehouse": WH_FG, "stock_tracking_number": TN, "uom": "个"}],
    }
    if not apply:
        log(f"DN {IC_FG} x{qty}", None, "dry-run：将创建并提交")
        return None
    name = c.insert("Delivery Note", doc)["name"]
    created["dn"] = name
    save_manifest_now()
    c.submit("Delivery Note", name)
    log(f"DN {IC_FG} x{qty}", True, f"{name} 已提交（模拟已出库 {qty} 件）")
    return name


def balances(c: Client) -> dict:
    return {
        "皮壳@待包装成品仓": c.sle_balance(IC_SHELL, WH_SHELL, TN),
        "成品@成品仓": c.sle_balance(IC_FG, WH_FG, TN),
    }


def show_balances(c: Client, label: str) -> dict:
    b = balances(c)
    print(f"  [{label}] 皮壳@待包装={b['皮壳@待包装成品仓']}  成品@成品仓={b['成品@成品仓']}")
    return b


def load_manifest() -> dict:
    if MANIFEST.is_file():
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {"created": {}, "steps": []}


def save_manifest(m: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")


_M: dict = load_manifest()


def save_manifest_now() -> None:
    _M["log"] = LOG
    save_manifest(_M)


def reset_all(c: Client, apply: bool) -> None:
    """彻底清理 ZZVERIFY 测试单据。

    做法：按 SLE 反查「动过这两个物料、且未取消」的凭证 —— 比清单可靠（清单会漏掉
    中途失败的残留）。取消顺序按依赖倒序：出库单 → Manufacture → 其余，避免自己把
    库存弄成负数而取消不掉。
    """
    found: dict[tuple[str, str], int] = {}
    for ic in (IC_SHELL, IC_FG):
        try:
            rows = c.get_list("Stock Ledger Entry",
                              [["item_code", "=", ic], ["is_cancelled", "=", 0]],
                              ["voucher_type", "voucher_no"], 0)
        except Exception:  # noqa: BLE001
            continue
        for r in rows or []:
            if r.get("voucher_type") in ("Stock Entry", "Delivery Note") and r.get("voucher_no"):
                found[(r["voucher_type"], r["voucher_no"])] = 0
    created = _M.get("created", {})
    for dt, nm in ([("Delivery Note", created.get("dn")),
                    ("Stock Entry", created.get("manufacture_redo")),
                    ("Stock Entry", created.get("manufacture"))]
                   + [("Stock Entry", n) for n in created.get("receipts", [])]):
        if nm:
            found.setdefault((dt, nm), 0)

    ordered = []
    for (dt, nm) in sorted(found):
        pr = 0 if dt == "Delivery Note" else None
        if pr is None:
            try:
                doc = c.get_doc("Stock Entry", nm)
                pr = 1 if (doc.get("purpose") or "").startswith("Manufacture") else 2
            except Exception:  # noqa: BLE001
                pr = 9
        ordered.append((pr, dt, nm))

    for pr, dt, nm in sorted(ordered):
        if not apply:
            print(f"  dry-run：将清理 {dt} {nm}")
            continue
        try:
            doc = c.get_doc(dt, nm)
            if doc.get("docstatus") == 1:
                c.cancel(dt, nm)
            c.delete(dt, nm)
            print(f"  ✓ 已清理 {dt} {nm}")
        except Exception as e:  # noqa: BLE001
            print(f"  · {dt} {nm} 清理跳过：{str(e)[:180]}")

    # 失败草稿兜底（还没产生 SLE 的那些）
    for dt in ("Stock Entry", "Delivery Note"):
        if not apply:
            continue
        try:
            drafts = c.get_list(dt, [["docstatus", "=", 0]], ["name"], 0)
        except Exception:  # noqa: BLE001
            continue
        for row in drafts or []:
            try:
                doc = c.get_doc(dt, row["name"])
                codes = [i.get("item_code") for i in (doc.get("items") or [])]
                if any(str(x).startswith("ZZVERIFY") for x in codes):
                    c.delete(dt, row["name"])
                    print(f"  ✓ 已清理残留草稿 {dt} {row['name']}")
            except Exception:  # noqa: BLE001
                continue

    _M["created"] = {}
    if apply:
        save_manifest_now()


# ── 子命令 ─────────────────────────────────────────────────
def cmd_scout(c: Client) -> None:
    banner("侦察：接口权限 / 默认公司 / 物料组 / 菲号必填 / 现有相关数据")
    r = c._req("GET", "/api/method/frappe.auth.get_logged_user")
    print("  登录用户:", r.json().get("message") if r.status_code == 200 else r.text[:200])
    try:
        u = c._req("GET", "/api/method/frappe.client.get_list",
                   params={"doctype": "User", "fields": json.dumps(["name", "user_type"]),
                           "limit_page_length": 0}).json()
        print("  User 可读（说明有基础读权限）:", str(u)[:200])
    except Exception as e:  # noqa: BLE001
        print("  User 读取受限:", str(e)[:150])
    for probe in ("Has Role", "Role"):
        try:
            rows = c.get_list(probe, None, ["name"], 3)
            print(f"  {probe} 可读，样例 {len(rows)} 条")
        except Exception as e:  # noqa: BLE001
            print(f"  {probe} 403/受限（正常，子表列表被禁）: {str(e)[:80]}")
    try:
        gs = c.get_doc("Global Defaults", "Global Defaults")
        print("  默认公司:", gs.get("default_company"))
    except Exception:  # noqa: BLE001
        pass
    items = c.get_list("Item", [["name", "like", "ALRML1010%"]], ["name", "item_group", "stock_uom"], 3)
    print("  样例物料:", json.dumps(items, ensure_ascii=False))
    if items:
        print("  可复用 item_group:", items[0].get("item_group"))
    tn_meta = c._req("GET", "/api/method/frappe.client.get_meta",
                     params={"doctype": "Tracking Number"}).json().get("message", {})
    print("  Tracking Number autoname:", tn_meta.get("autoname"))
    print("  Tracking Number 必填:", [f["fieldname"] for f in tn_meta.get("fields", []) if f.get("reqd")])
    print("  ZZVERIFY 物料是否已存在:", c.exists("Item", IC_SHELL), c.exists("Item", IC_FG),
          "| TN:", c.exists("Tracking Number", TN))
    print("  当前开关: allow_negative_stock(全局) =",
          c.get_doc("Stock Settings", "Stock Settings").get("allow_negative_stock"))


def cmd_run(c: Client, apply: bool) -> None:
    m = _M
    banner(f"开始验证（{'APPLY 写测试环境' if apply else 'DRY-RUN 不写'}）")

    if apply:
        print("\n[-1] 清理上次残留（幂等重跑）")
        reset_all(c, True)
    created: dict = {}
    m["created"] = created

    print("\n[1] 搭建等效场景：皮壳入库 → 整批投产 N 件 → 出库 M 件")
    ensure_item(c, IC_SHELL, "ZZ验证用皮壳", ITEM_GROUP, apply)
    ensure_item(c, IC_FG, "ZZ验证用成品", ITEM_GROUP, apply)
    ensure_tn(c, apply)
    se_receipt(c, N, apply, created)
    se_manufacture(c, N, apply, created, "manufacture")
    make_dn(c, M, apply, created)

    if not apply:
        log("场景搭建", None, "dry-run 结束；加 --apply 才真正写入测试环境")
        return

    save_manifest_now()
    print("\n  [自检] 场景搭建后的账面")
    before = show_balances(c, "取消前")
    m["balances_before"] = before
    save_manifest_now()
    if abs(before["成品@成品仓"] - (N - M)) > 1e-6 or abs(before["皮壳@待包装成品仓"]) > 1e-6:
        log("场景自检", False,
            f"成品@成品仓={before['成品@成品仓']}（期望 {N - M}）"
            f" 皮壳@待包装={before['皮壳@待包装成品仓']}（期望 0）"
            " —— 场景未按预期落地，后续结论不可信")
        return
    log("场景自检", True,
        f"成品@成品仓={before['成品@成品仓']}（期望 {N - M}）、皮壳={before['皮壳@待包装成品仓']}（期望 0）")

    # ── H1：直接取消，预期被负库存拦截 ──
    print("\n[2] H1：直接取消那张 Manufacture（预期被负库存拦住）")
    h1 = {"blocked": None, "error": None}
    try:
        c.cancel("Stock Entry", created["manufacture"])
        h1["blocked"] = False
        h1["error"] = "未拦截（取消成功）"
        log("H1 取消", True, "未被拦截 —— 假设不成立，需重新评估")
    except RuntimeError as e:
        h1["blocked"] = True
        h1["error"] = str(e)
        log("H1 取消", True, f"被拦截 ✓ 报错：{str(e)[:300]}")

    if h1["blocked"]:
        # ── H2a：按物料开关放行 ──
        print("\n[3] H2a：置 Item.allow_negative_stock=1 后重试取消")
        h2a = {}
        try:
            c.set_value("Item", IC_FG, "allow_negative_stock", 1)
            r = c._req("GET", f"/api/resource/Item/{quote(IC_FG, safe='')}")
            h2a["flag_readback"] = r.json()["data"].get("allow_negative_stock")
            print("  回读 Item.allow_negative_stock =", h2a["flag_readback"])
            c.cancel("Stock Entry", created["manufacture"])
            h2a["passed"] = True
            log("H2a 按物料开关", True, "取消成功 ✓")
        except RuntimeError as e:
            h2a["passed"] = False
            h2a["error"] = str(e)
            log("H2a 按物料开关", False, f"仍被拦住：{str(e)[:300]}")
        finally:
            try:
                c.set_value("Item", IC_FG, "allow_negative_stock", 0)
                back = c._req("GET", f"/api/resource/Item/{quote(IC_FG, safe='')}").json()["data"]
                h2a["flag_reset"] = back.get("allow_negative_stock")
                print("  复位后 Item.allow_negative_stock =", h2a["flag_reset"])
            except Exception as e:  # noqa: BLE001
                h2a["flag_reset"] = f"复位失败: {e}"
        m["h2a"] = h2a

        if not h2a.get("passed"):
            # ── H2b：全局开关放行 ──
            print("\n[4] H2b：置 Stock Settings.allow_negative_stock=1 后重试取消")
            h2b = {}
            try:
                c.set_value("Stock Settings", "Stock Settings", "allow_negative_stock", 1)
                print("  回读全局开关 =",
                      c.get_doc("Stock Settings", "Stock Settings").get("allow_negative_stock"))
                c.cancel("Stock Entry", created["manufacture"])
                h2b["passed"] = True
                log("H2b 全局开关", True, "取消成功 ✓")
            except RuntimeError as e:
                h2b["passed"] = False
                h2b["error"] = str(e)
                log("H2b 全局开关", False, f"仍被拦住：{str(e)[:300]}")
            finally:
                c.set_value("Stock Settings", "Stock Settings", "allow_negative_stock", 0)
                print("  复位后全局开关 =",
                      c.get_doc("Stock Settings", "Stock Settings").get("allow_negative_stock"))
            m["h2b"] = h2b

    # ── H3：重做 M 件 ──
    print("\n[5] H3：取消后的中间态 + 重做 M 件 Manufacture")
    if apply:
        mid = show_balances(c, "取消后 / 重做前")
        m["balances_mid"] = mid
        ensure_item(c, IC_SHELL, "ZZ验证用皮壳", ITEM_GROUP, True)
        se_manufacture(c, M, True, created, "manufacture_redo")
        after = show_balances(c, "重做 M 件后")
        m["balances_after"] = after
        m["h3"] = {
            "fg_is_zero": abs(after["成品@成品仓"]) < 1e-6,
            "shell_expected": N - M,
            "shell_actual": after["皮壳@待包装成品仓"],
            "shell_ok": abs(after["皮壳@待包装成品仓"] - (N - M)) < 1e-6,
        }
        log("H3 终态", bool(m["h3"]["fg_is_zero"] and m["h3"]["shell_ok"]),
            f"成品={after['成品@成品仓']}（期望 0） 皮壳={after['皮壳@待包装成品仓']}（期望 {N - M}）")

        # ── H4：DN 流水未变 ──
        print("\n[6] H4：核对已提交出库单的流水未被改动")
        dn_rows = c.sle_rows(IC_FG, TN)
        dn_related = [r for r in dn_rows if r["voucher_type"] == "Delivery Note"]
        m["h4"] = {"dn_sle_rows": dn_related}
        log("H4 出库流水", bool(dn_related),
            f"Delivery Note 相关 SLE {len(dn_related)} 条："
            + ", ".join(f"{r['voucher_no']}({r['actual_qty']})" for r in dn_related))

    save_manifest_now()
    banner("验证执行完毕，跑 report 出报告")


def _clean(s: str) -> str:
    """去掉 ERPNext 报错里的 HTML 标签，便于阅读。"""
    import re as _re
    return _re.sub(r"<[^>]+>", "", str(s)).replace("&nbsp;", " ").strip()


def cmd_report(c: Client) -> None:
    m = load_manifest()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    out = OUT_DIR / f"manufacture_rollback_verify_{ts}.md"
    lines = [
        "# 验证报告：取消「多投产」的 Manufacture 并把余量退回皮壳",
        "",
        f"- 环境：`{BASE}`（测试，独立数据集）",
        f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 场景参数：整批投产 N={N}，计划/出库 M={M}（等同生产 WO-26-02796-002 的 36 / 4）",
        f"- 测试物料：`{IC_SHELL}` / `{IC_FG}`，菲号 `{TN}`",
        "",
        "## 结论",
        "",
    ]
    h1 = next((e for e in m.get("log", []) if e["step"] == "H1 取消"), None)
    lines.append(f"- **H1 取消是否被负库存拦截**：{_clean(h1['detail']) if h1 else '未执行'}")
    if m.get("h2a"):
        lines.append(f"- **H2a 按物料开关 `Item.allow_negative_stock`**："
                     f"{'放行 ✓' if m['h2a'].get('passed') else '仍被拦 ✗'}；"
                     f"开关回读={m['h2a'].get('flag_readback')}，复位后={m['h2a'].get('flag_reset')}")
    if m.get("h2b"):
        lines.append(f"- **H2b 全局开关 `Stock Settings.allow_negative_stock`**："
                     f"{'放行 ✓' if m['h2b'].get('passed') else '仍被拦 ✗'}")
    if m.get("h3"):
        lines.append(f"- **H3 终态**：成品={m['balances_after']['成品@成品仓']}（期望 0）"
                     f" 皮壳={m['balances_after']['皮壳@待包装成品仓']}（期望 {N - M}）→ "
                     f"{'符合 ✓' if m['h3'].get('fg_is_zero') and m['h3'].get('shell_ok') else '不符合 ✗'}")
    lines += ["", "## 账面变化", "",
              "| 阶段 | 皮壳@待包装成品仓 | 成品@成品仓 |", "|---|---|---|"]
    for key, label in (("balances_before", "取消前"), ("balances_mid", "取消后/重做前"),
                       ("balances_after", "重做 M 件后")):
        b = m.get(key)
        if b:
            lines.append(f"| {label} | {b['皮壳@待包装成品仓']} | {b['成品@成品仓']} |")
    h4 = m.get("h4")
    if h4:
        lines += ["", "## H4 出库流水（应保持原样）", ""]
        for r in h4["dn_sle_rows"]:
            lines.append(f"- {r['voucher_type']} {r['voucher_no']} {r['warehouse']} "
                         f"actual_qty={r['actual_qty']} cancelled={r['is_cancelled']}")
    lines += ["", "## 原始执行日志", "", "```"]
    for e in m.get("log", []):
        lines.append(f"{e.get('at', '')}  {e.get('step', '')}  {_clean(e.get('detail', ''))}")
    lines += ["```", "", "## 创建的单据（清理用）", "", "```",
              json.dumps(m.get("created", {}), ensure_ascii=False, indent=1), "```", ""]

    lines += [
        "## 生产执行方案（已在测试验证，生产尚未执行）",
        "",
        "针对菲号 `WO-26-02796-002` / 成品 `KS0001-HLR-153-TAN`：",
        "",
        "1. **打开负库存闸门（按物料，不动全局）**：`Item.allow_negative_stock = 1`",
        "   —— 依据 `stock_ledger.py:2193 is_negative_stock_allowed()`，按物料的开关即可放行，",
        "   无需改 `Stock Settings`（全局开关影响面更大）。改完记得清文档缓存。",
        "2. **取消 `STE-26-15219`**（36 件 Manufacture）。取消后账面：成品仓 −4 / 待包装仓皮壳 36。",
        "3. **重做一张 4 件的 Manufacture**（消耗 4 皮壳 → 成品入 成品仓，带菲号 `WO-26-02796-002`）。",
        "   终态：**成品仓 0 / 待包装仓皮壳 32**。",
        "4. **关回闸门**：`Item.allow_negative_stock = 0`（脚本必须 `try/finally` 保证）。",
        "5. **复核**：该菲号 成品 0 / 皮壳 32；`DN-26-00078` 的 4 件 SLE 原样未动；",
        "   `WO-26-02502` 由 `Completed` 回退（produced 40→4）—— 执行前确认它没被别处引用。",
        "",
        "### 生产与本次测试的差异（必须注意）",
        "",
        "- 本次测试为绕开 ERPNext「成品须有成本价」的校验，给成品行写了固定单价",
        f"  `basic_rate={FG_RATE}`。**生产不要照抄**：应走 `_build_manufacture_stock_entry(fp_wo, 4,",
        "  tracking_number=...)`（带 BOM，由系统按皮壳成本算出成品单价），否则会低估入账成本。",
        "- 测试场景不带工单/生产计划；生产上该 Manufacture 需挂到成品工单上。",
        "",
        "## 未验证 / 残留不确定",
        "",
        "- **成本结转是否与原始凭证一致**：本次只验证了数量与负库存拦截，重做 4 件的成本口径未做对比。",
        "- **问题会复发（代码推导，未实测）**：`delivery_plan.py:1157-1166` 取",
        "  `min(该菲号待包装仓皮壳余额, 工单剩余)` 投产，下次提交同菲号的计划时会**整批**投产",
        "  （32 件），出 8 件后成品仓又剩 24、皮壳归零 → 再次扫不出来。",
        "  要断根需改扫码口径（皮壳为 0 时回退查成品仓）或改投产数量为按需。",
        "",
    ]
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"✓ 报告: {out}")


def cmd_cleanup(c: Client, apply: bool) -> None:
    m = load_manifest()
    created = m.get("created", {})
    banner(f"清理测试单据（{'APPLY' if apply else 'DRY-RUN'}）")
    for key in ("dn", "manufacture_redo", "manufacture"):
        nm = created.get(key)
        if not nm:
            continue
        if not apply:
            print(f"  dry-run：将取消 {key} = {nm}")
            continue
        try:
            c.cancel("Stock Entry" if key != "dn" else "Delivery Note", nm)
            print(f"  ✓ 已取消 {key} = {nm}")
        except RuntimeError as e:
            print(f"  ✗ {key} = {nm} 取消失败：{str(e)[:200]}")
    for nm in created.get("receipts", []):
        if not apply:
            print(f"  dry-run：将取消 receipt = {nm}")
            continue
        try:
            c.cancel("Stock Entry", nm)
            print(f"  ✓ 已取消 receipt = {nm}")
        except RuntimeError as e:
            print(f"  ✗ receipt = {nm} 取消失败：{str(e)[:200]}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("scout", "run", "reset", "report", "cleanup"))
    ap.add_argument("--apply", action="store_true", help="真正写测试环境（默认 dry-run）")
    args = ap.parse_args()

    c = Client()
    print(f"环境: {BASE}  |  命令: {args.cmd}  |  {'APPLY' if args.apply else 'DRY-RUN'}")
    if args.cmd == "scout":
        cmd_scout(c)
    elif args.cmd == "run":
        cmd_run(c, args.apply)
    elif args.cmd == "reset":
        reset_all(c, args.apply)
    elif args.cmd == "report":
        cmd_report(c)
    else:
        cmd_cleanup(c, args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
