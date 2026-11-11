# -*- coding: utf-8 -*-
"""查询 ERPNext 生产系统中「客户物料号 (customer_items.ref_code) 以 -1 结尾」的物料。

只读查询, 不写任何数据。

数据模型:
  - 父文档: Item (物料)
  - 子表字段: customer_items  →  子表 Doctype: Item Customer Detail
  - 客户物料号字段: ref_code

策略:
  1. 优先用子表过滤: GET /api/resource/Item
        filters=[["Item Customer Detail","ref_code","like","%-1"]]
        fields=[...,"customer_items"]
     若列表接口正常返回子表行 → 直接在 Python 中二次过滤 endswith("-1")。
  2. 若列表接口不返回子表行 (Frappe get_list 的常见行为) →
     先用同样的过滤拿到匹配物料的 name 列表, 再逐个 GET 拉 customer_items 子表, 并发过滤。

输出: out/客户物料号_结尾-1_物料_{ts}.xlsx  (含汇总 sheet)
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests
from requests.adapters import HTTPAdapter

_DIR = Path(__file__).resolve().parent
os.chdir(_DIR)

_SUFFIX = "-1"  # 客户物料号结尾


# ── .env 加载 ──
def _load_dotenv(candidates):
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


_load_dotenv([_DIR / ".env", _DIR.parent / ".env"])


class _NoExpect(HTTPAdapter):
    def send(self, req, **kw):
        req.headers.pop("Expect", None)
        return super().send(req, **kw)


def main() -> int:
    base = os.getenv("ERP_URL") or "https://erpnext.vilavi.cn"
    key = os.getenv("PROD_ERP_API_KEY") or os.getenv("ERP_API_KEY", "")
    secret = os.getenv("PROD_ERP_API_SECRET") or os.getenv("ERP_API_SECRET", "")

    if not key or not secret:
        print("错误: 未找到 API 凭证 (PROD_ERP_API_KEY / PROD_ERP_API_SECRET)")
        return 1
    # 注: 本项目生产系统凭证实际为 15 位 (用户已确认), 不再按 32 位强制校验。

    sess = requests.Session()
    sess.headers["Authorization"] = f"token {key}:{secret}"
    sess.mount("https://", _NoExpect())

    # ── 连通性检查 ──
    try:
        r = sess.get(f"{base}/api/method/ping", timeout=30)
        if r.status_code == 401:
            print(f"错误: 鉴权失败 (401)。凭证无效或已被截断。请检查 {_DIR / '.env'}")
            return 1
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"错误: 无法连接 {base}: {e}")
        return 1

    print(f"已连接生产系统: {base}")

    def _get(url, params):
        for attempt in range(4):
            try:
                resp = sess.get(url, params=params, timeout=(60, 300))
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as e:
                if attempt < 3:
                    time.sleep(3 * (attempt + 1))
                else:
                    raise
        return {}

    # ── 策略 1: 带子表过滤的列表查询 ──
    print("策略1: 子表过滤查询 (ref_code like %-1) ...")
    list_params = {
        "fields": json.dumps(["name", "item_code", "item_name",
                               "item_group", "customer_items"]),
        "filters": json.dumps([["Item Customer Detail", "ref_code", "like", f"%{_SUFFIX}"]]),
        "limit_page_length": "0",
    }
    data = _get(f"{base}/api/resource/Item", list_params).get("data", [])
    print(f"  过滤返回物料数: {len(data)}")

    # 判断列表是否返回了子表行
    child_populated = any((d.get("customer_items") or []) for d in data[:50]) or \
                      any((d.get("customer_items") or []) for d in data[-50:])

    results = []  # list of dict

    if child_populated:
        print("  列表接口已返回子表行, 直接二次过滤。")
        for d in data:
            cis = d.get("customer_items") or []
            matched = [ci for ci in cis
                       if (ci.get("ref_code") or "").endswith(_SUFFIX)]
            if matched:
                results.append(_build_row(d, matched))
    else:
        print("  列表接口未返回子表行, 转入策略2: 逐个拉取 customer_items。")
        # 去重: ERPNext 子表 JOIN 可能让同一物料返回多次
        names = list(dict.fromkeys(d["name"] for d in data if d.get("name")))
        print(f"  需逐个查询的物料数 (去重后): {len(names)}")

        def _fetch_one(name):
            try:
                full = _get(f"{base}/api/resource/Item/{name}",
                            {"fields": json.dumps(["name", "item_code",
                                                   "item_name", "item_group",
                                                   "customer_items"])})
                d = full.get("data", {})
                cis = d.get("customer_items") or []
                matched = [ci for ci in cis
                           if (ci.get("ref_code") or "").endswith(_SUFFIX)]
                return _build_row(d, matched) if matched else None
            except Exception:
                return None

        t0 = time.time()
        done = 0
        with ThreadPoolExecutor(max_workers=8) as pool:
            futs = {pool.submit(_fetch_one, n): n for n in names}
            for fut in as_completed(futs):
                done += 1
                row = fut.result()
                if row:
                    results.append(row)
                if done % 2000 == 0:
                    el = time.time() - t0
                    print(f"    {done}/{len(names)} ({done/len(names)*100:.0f}%) "
                          f"耗时 {el:.0f}s, 已匹配 {len(results)}")
        print(f"  逐个查询完成, 匹配 {len(results)} 个物料。")

    # 安全去重: 按物料编码去重 (同一物料可能因多匹配子表行出现多次)
    seen = set()
    deduped = []
    for r0 in results:
        code = r0["物料编码"]
        if code in seen:
            continue
        seen.add(code)
        deduped.append(r0)
    results = deduped

    # ── 输出 ──
    print(f"\n=== 匹配结果: 共 {len(results)} 个物料 (客户物料号以 {_SUFFIX} 结尾) ===")
    for r0 in results[:20]:
        print(f"  {r0['物料编码']} | {r0['物料名称'][:24]} | 客户物料号: {r0['匹配客户物料号']}")
    if len(results) > 20:
        print(f"  ... 其余 {len(results)-20} 个见 Excel")

    out_dir = _DIR / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"客户物料号_结尾{_SUFFIX}_物料_{ts}.xlsx"

    # 展开: 一行一个 (物料, 客户物料号)
    flat = []
    for r0 in results:
        for code in r0["匹配客户物料号"].split(" | "):
            flat.append({
                "物料编码": r0["物料编码"],
                "物料名称": r0["物料名称"],
                "物料组": r0["物料组"],
                "客户物料号": code,
                "客户组": r0.get("客户组", ""),
            })
    df = pd.DataFrame(flat, columns=["物料编码", "物料名称", "物料组",
                                      "客户物料号", "客户组"])
    summary = pd.DataFrame([{
        "查询条件": f"customer_items.ref_code 以 {_SUFFIX} 结尾",
        "环境": "prod (erpnext.vilavi.cn)",
        "匹配物料数": len(results),
        "匹配明细行数": len(flat),
        "查询时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }])
    with pd.ExcelWriter(out_path, engine="openpyxl") as w:
        summary.to_excel(w, sheet_name="汇总", index=False)
        df.to_excel(w, sheet_name="明细", index=False)

    print(f"\n报告已生成: {out_path}")
    return 0


def _build_row(d: dict, matched: list[dict]) -> dict:
    codes = [ci.get("ref_code", "") for ci in matched]
    groups = sorted({ci.get("customer_group") or ci.get("customer") or ""
                     for ci in matched})
    return {
        "物料编码": d.get("item_code", ""),
        "物料名称": d.get("item_name", ""),
        "物料组": d.get("item_group", ""),
        "匹配客户物料号": " | ".join(codes),
        "客户组": " | ".join(g for g in groups if g),
    }


if __name__ == "__main__":
    raise SystemExit(main())
