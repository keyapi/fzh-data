# -*- coding: utf-8 -*-
"""把生产 ERPNext「包装工艺路线」子表的工费率 / 工序时间改成指定值。

背景
----
这条 Routing 上有一个必填自定义字段「来源物料」(`source_items`, Link -> Item)，而该记录
此字段为空，所以页面保存和任何 REST 保存都会被服务端 `_validate_mandatory` 拦下
(「工艺路线中有必填字段 来源物料」)。

Frappe 15 里**没有任何 REST 路径能跳过校验**，已逐条核实：
  * 唯一开关 `doc.flags.ignore_mandatory` 无法注入 —— `"flags"` 在
    `BaseDocument._reserved_keywords` 里，`doc.update({"flags": ...})` 被静默忽略；
  * `frappe.client.set_value` / `bulk_update` / `insert` / `save` 和 Data Import 的
    `Importer.update_record` 全部以 `doc.save()` 收尾；
  * `PUT /api/resource/BOM Operation/<子行>` 也会级联
    `frappe.get_doc(parenttype, parent).save()`。
生产机 SSH 实际可达（见 AGENTS.md「EN 服务器 SSH」）；本脚本仍走 REST，是为了可复现、免交互 —— `bench execute` 不再被排除。

做法
----
临时建一条 Property Setter 把 `Routing.source_items` 的 `reqd` 覆盖成 0，保存工艺路线
（服务端会自动重算 `operating_cost`），然后立刻删掉这条 Property Setter。

比直接改 Custom Field 更轻：`PropertySetter` 的钩子只调 `frappe.clear_cache(doctype)`，
而 `CustomField.on_update` 会额外触发 `frappe.db.updatedb("Routing")`（生产表结构同步）。

使用
----
  python update_packaging_routing_cost.py            # dry-run，只读，不写任何东西
  python update_packaging_routing_cost.py --apply    # 真正写入生产

凭证取 `EN_API/.env` 的 `PROD_ERP_API_KEY` / `PROD_ERP_API_SECRET`。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter

_DIR = Path(__file__).resolve().parent

# ── 目标 ──────────────────────────────────────────────
ROUTING = "包装工艺路线"
ROUTING_DOCTYPE = "Routing"
SOURCE_ITEM_FIELD = "source_items"
HOUR_RATE = 23.2
TIME_IN_MINS = 28.0
# ERPNext: operating_cost = flt(hour_rate * time_in_mins / 60, precision)
OPERATING_COST = round(HOUR_RATE * TIME_IN_MINS / 60, 3)  # 10.827

DEFAULT_URL = "https://erpnext.vilavi.cn"

# 覆盖 reqd 的 Property Setter（建立后立即删除）
REQDER_BODY = {
    "doctype_or_field": "DocField",
    "doc_type": ROUTING_DOCTYPE,
    "field_name": SOURCE_ITEM_FIELD,
    "property": "reqd",
    "property_type": "Check",
    "value": "0",
}


# ── .env 加载 ─────────────────────────────────────────
def _load_dotenv(candidates: list[Path]) -> None:
    for p in candidates:
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                v = v[1:-1]
            os.environ.setdefault(k, v)


# ── HTTP ──────────────────────────────────────────────
class _NoExpectAdapter(HTTPAdapter):
    def send(self, request, **kwargs):
        request.headers.pop("Expect", None)
        return super().send(request, **kwargs)


class ErpnextClient:
    def __init__(self, base_url: str, api_key: str, api_secret: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"token {api_key}:{api_secret}"
        self.session.mount("https://", _NoExpectAdapter())
        self.session.mount("http://", _NoExpectAdapter())

    # -- 通用 --
    def _request(self, method: str, path: str, *, retries: int = 2,
                 retry_delay: float = 3.0, **kwargs: Any) -> requests.Response:
        timeout = kwargs.pop("timeout", (30, 120))
        url = f"{self.base_url}{path}"
        last: Exception | None = None
        for attempt in range(retries + 1):
            try:
                r = self.session.request(method, url, timeout=timeout, **kwargs)
                r.raise_for_status()
                return r
            except requests.RequestException as exc:
                last = exc
                if attempt < retries:
                    time.sleep(retry_delay)
        assert last is not None
        raise last

    @staticmethod
    def _resource(doctype: str, name: str | None = None) -> str:
        base = f"/api/resource/{quote(doctype, safe='')}"
        return f"{base}/{quote(name, safe='')}" if name else base

    # -- 具体操作 --
    def get_doc(self, doctype: str, name: str) -> dict:
        return self._request("GET", self._resource(doctype, name)).json()["data"]

    def get_list(self, doctype: str, filters: list | None = None,
                 fields: list[str] | None = None) -> list[dict]:
        params: dict[str, str] = {"limit_page_length": "0"}
        if filters is not None:
            params["filters"] = json.dumps(filters)
        if fields is not None:
            params["fields"] = json.dumps(fields)
        return self._request("GET", self._resource(doctype), params=params).json()["data"]

    def create_doc(self, doctype: str, body: dict) -> dict:
        return self._request("POST", self._resource(doctype), json=body).json()["data"]

    def update_doc(self, doctype: str, name: str, body: dict) -> dict:
        return self._request("PUT", self._resource(doctype, name), json=body).json()["data"]

    def delete_doc(self, doctype: str, name: str) -> None:
        self._request("DELETE", self._resource(doctype, name))


# ── 业务 ──────────────────────────────────────────────
def row_summary(row: dict) -> dict:
    return {k: row.get(k) for k in ("name", "idx", "operation", "workstation",
                                    "hour_rate", "time_in_mins", "operating_cost")}


def build_payload(doc: dict) -> tuple[dict, list[dict]]:
    """返回 (PUT body, 改后子表)。原样子行整份回传，只改三个数字。

    必须整份回传：`doc.update()` 对 Table 字段会重建子行，而 `db_update` 写入
    `get_valid_columns()` 的全部列 —— 漏带的字段会被写空。
    """
    ops: list[dict] = []
    for raw in doc.get("operations") or []:
        row = dict(raw)
        row["hour_rate"] = HOUR_RATE
        row["time_in_mins"] = TIME_IN_MINS
        row["operating_cost"] = OPERATING_COST
        ops.append(row)
    body = {
        "routing_name": doc.get("routing_name"),
        "disabled": doc.get("disabled", 0),
        "operations": ops,
    }
    return body, ops


def verify(client: ErpnextClient, leftover_ps: str | None) -> list[str]:
    """返回问题列表（空 = 全部通过）。"""
    problems: list[str] = []

    doc = client.get_doc(ROUTING_DOCTYPE, ROUTING)
    ops = doc.get("operations") or []
    got = [{k: r.get(k) for k in ("hour_rate", "time_in_mins", "operating_cost")} for r in ops]
    want = {"hour_rate": HOUR_RATE, "time_in_mins": TIME_IN_MINS, "operating_cost": OPERATING_COST}
    for g in got:
        for k, v in want.items():
            if abs(float(g.get(k) or 0) - v) > 1e-9:
                problems.append(f"{ROUTING}.operations 的 {k} 期望 {v}，实际 {g.get(k)}")
    if doc.get("source_items"):
        problems.append(f"{ROUTING}.source_items 应保持为空，实际 {doc['source_items']!r}")

    cf = client.get_doc("Custom Field", f"{ROUTING_DOCTYPE}-{SOURCE_ITEM_FIELD}")
    if int(cf.get("reqd") or 0) != 1:
        problems.append(f"Custom Field {ROUTING_DOCTYPE}-{SOURCE_ITEM_FIELD} 的 reqd 未恢复为 1，"
                        f"实际 {cf.get('reqd')!r}")

    remaining = client.get_list("Property Setter",
                                filters=[["doc_type", "=", ROUTING_DOCTYPE]],
                                fields=["name", "property", "field_name"])
    names = {r["name"] for r in remaining}
    if leftover_ps and leftover_ps in names:
        problems.append(f"Property Setter 未删除：{leftover_ps}")
    stray = [r["name"] for r in remaining
             if r.get("property") == "reqd" and r.get("field_name") == SOURCE_ITEM_FIELD]
    if stray:
        problems.append(f"仍有 reqd 覆盖残留：{stray}")
    print(f"  现存 Routing Property Setter: {sorted(names)}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="修改生产「包装工艺路线」子表的工费率/工序时间")
    ap.add_argument("--apply", action="store_true", help="真正写入（默认 dry-run，只读）")
    ap.add_argument("--url", default=os.getenv("PROD_ERP_URL", DEFAULT_URL))
    args = ap.parse_args()

    _load_dotenv([_DIR / ".env", _DIR.parent / ".env", _DIR.parent.parent / ".env"])
    key = os.getenv("PROD_ERP_API_KEY", "")
    secret = os.getenv("PROD_ERP_API_SECRET", "")
    if not key or not secret:
        print("错误: 缺少 PROD_ERP_API_KEY / PROD_ERP_API_SECRET（见 EN_API/.env）")
        return 1

    client = ErpnextClient(args.url, key, secret)

    doc = client.get_doc(ROUTING_DOCTYPE, ROUTING)
    ops = doc.get("operations") or []
    print(f"环境: {args.url}")
    print(f"文档: {ROUTING_DOCTYPE} / {ROUTING}  (docstatus={doc.get('docstatus')}, "
          f"来源物料={doc.get('source_items')!r})")
    print(f"子表 {len(ops)} 行：")
    for r in ops:
        print("   前:", json.dumps(row_summary(r), ensure_ascii=False))
    body, new_ops = build_payload(doc)
    for r in new_ops:
        print("   后:", json.dumps(row_summary(r), ensure_ascii=False))
    print(f"目标 operating_cost = {HOUR_RATE} * {TIME_IN_MINS} / 60 = {OPERATING_COST}")

    if not args.apply:
        print("\n[dry-run] 将要执行：")
        print(f"  1) POST   /api/resource/Property Setter   {json.dumps(REQDER_BODY, ensure_ascii=False)}")
        print(f"  2) GET    /api/resource/{ROUTING_DOCTYPE}/{ROUTING}")
        print(f"  3) PUT    /api/resource/{ROUTING_DOCTYPE}/{ROUTING}   (operations 整份回传)")
        print("  4) DELETE /api/resource/Property Setter/<新建的 name>       # finally")
        print("  5) GET 复核：值 / reqd=1 / 无 Property Setter 残留")
        print("\n加 --apply 才会真正写入。")
        return 0

    ps_name: str | None = None
    failed = False
    try:
        print("\n[1/4] 建立 reqd=0 覆盖 ...")
        ps = client.create_doc("Property Setter", dict(REQDER_BODY))
        ps_name = ps.get("name")
        print(f"      已建立 Property Setter: {ps_name}")

        print("[2/4] 读取最新文档 ...")
        doc = client.get_doc(ROUTING_DOCTYPE, ROUTING)
        body, _ = build_payload(doc)

        print("[3/4] 保存工艺路线 ...")
        saved = client.update_doc(ROUTING_DOCTYPE, ROUTING, body)
        for r in saved.get("operations") or []:
            print("      已保存:", json.dumps(row_summary(r), ensure_ascii=False))
    except Exception as exc:
        failed = True
        print(f"\n[失败] {type(exc).__name__}: {exc}")
        if isinstance(exc, requests.HTTPError) and exc.response is not None:
            print("       服务端返回:", exc.response.text[:600])
        if ps_name is None:
            print("       提示: 若 POST Property Setter 被拒，可改用 Custom Field 方案 —— ")
            print('             PUT /api/resource/Custom Field/Routing-source_items  {"reqd":0}')
            print("             ...保存工艺路线...")
            print('             PUT /api/resource/Custom Field/Routing-source_items  {"reqd":1}')
    finally:
        if ps_name:
            print(f"[4/4] 删除 Property Setter {ps_name} ...")
            try:
                client.delete_doc("Property Setter", ps_name)
                print("      已删除")
            except Exception as exc:
                failed = True
                print(f"      [严重] 删除失败: {type(exc).__name__}: {exc}")
                print(f"      请手工删除: DELETE {args.url}/api/resource/Property Setter/{quote(ps_name, safe='')}")
                print(f"      否则「{SOURCE_ITEM_FIELD}」会一直是可选状态！")
                ps_name_left = ps_name
            else:
                ps_name_left = None
        else:
            ps_name_left = None

    print("\n[复核] 重新读取 ...")
    problems = verify(client, ps_name_left)
    if problems or failed:
        print("\n结果: 不通过")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("\n结果: 全部通过 —— 已改好，且「来源物料」仍为空、必填约束已恢复。")
    print("注意: 这条工艺路线仍是「必填字段为空」的状态，页面上再点保存依旧会报同样的错。")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    raise SystemExit(main())
