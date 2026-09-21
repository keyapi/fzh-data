"""Amazon 账期报表可拉取性核查（只读）。

背景：财务报税需要各账号的 Amazon 账期报表。赛狐侧有两条路：
  A. 报告中心/亚马逊原报告  (/api/report/center/{add,pageList}.json)  —— 服务端生成
  B. 报告中心/插件获取报告  (/api/report/center/task/getPlugPageList.json) —— 读「插件」已抓取的结果
Amazon 账期(Transaction/Summary) 只走 B：赛狐不自抓，靠浏览器插件在账号登录态下抓回来。
所以本脚本核查的是「**插件是否已为每个店铺抓过报表**」。

用法:
  uv run python probe_amazon_reports.py --start 2026-06-01 --end 2026-09-21
  uv run python probe_amazon_reports.py --start 2026-06-01 --end 2026-09-21 --shop-pattern 596
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from client import SellfoxClient, SellfoxConfig  # noqa: E402
from repo_root import find_main_root  # noqa: E402

PLUG_PATH = "/api/report/center/task/getPlugPageList.json"
SHOP_PATH = "/api/shop/pageList.json"
PACING_S = 2.0

# 插件报告类型（来自本地文档镜像 报告中心/插件获取报告/插件获取报告.md）
PLUG_TYPES = {
    3: "Transaction (csv/zip)",
    4: "Summary (pdf)",
    5: "Deferred transaction (csv/zip)",
    6: "FBAInboundConvenience (csv)",
}
STATUS = {0: "获取中", 1: "获取成功", 2: "获取失败"}


def raw_post(client: SellfoxClient, path: str, body: dict) -> dict[str, Any]:
    if client.config.mode != "proxy":
        raise SystemExit("本机不在 VPS 白名单，仅支持 proxy 模式")
    result, _ = client._post_once_proxy(path, body)
    time.sleep(PACING_S)
    return result


def all_shops(client: SellfoxClient) -> list[dict]:
    out: list[dict] = []
    page = 1
    while True:
        r = raw_post(client, SHOP_PATH, {"pageSize": 200, "pageNum": page})
        if r.get("code") != 0:
            raise SystemExit(f"店铺列表失败 code={r.get('code')} msg={r.get('msg')}")
        data = r.get("data") or {}
        out += data.get("rows") or []
        if len(out) >= int(data.get("totalSize") or 0) or not data.get("rows"):
            break
        page += 1
    return out


def all_plug_tasks(client: SellfoxClient, start: str, end: str) -> list[dict]:
    out: list[dict] = []
    page = 1
    while page <= 50:
        r = raw_post(client, PLUG_PATH, {
            "startTime": start, "endTime": end,
            "pageNo": str(page), "pageSize": "200",
        })
        if r.get("code") != 0:
            raise SystemExit(f"插件报告查询失败 code={r.get('code')} msg={r.get('msg')}")
        data = r.get("data") or {}
        rows = data.get("rows") or []
        out += rows
        print(f"  第 {page} 页 {len(rows)} 条（累计 {len(out)} / totalSize {data.get('totalSize')}）")
        if len(rows) < 200:
            break
        page += 1
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", help="报告开始时间 yyyy-MM-dd，默认 95 天前")
    ap.add_argument("--end", help="报告结束时间 yyyy-MM-dd，默认今天")
    ap.add_argument("--shop-pattern", help="只看店铺名/ID 含该子串的")
    ap.add_argument("--dump", help="原始 JSON 落盘路径")
    args = ap.parse_args()

    start = args.start or (date.today() - timedelta(days=95)).isoformat()
    end = args.end or date.today().isoformat()

    root = find_main_root()
    client = SellfoxClient(SellfoxConfig.from_env(root / ".env"))
    print(f"repo_root={root}  mode={client.config.mode}  窗口 {start} → {end}\n")

    print("[1] 拉 Amazon 店铺列表")
    shops = all_shops(client)
    print(f"  共 {len(shops)} 店\n")

    print("[2] 拉「插件获取报告」任务")
    tasks = all_plug_tasks(client, start, end)
    print(f"  共 {len(tasks)} 条\n")

    if args.dump:
        Path(args.dump).parent.mkdir(parents=True, exist_ok=True)
        Path(args.dump).write_text(
            json.dumps({"shops": shops, "plugTasks": tasks}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        print(f"  原始数据落盘 {args.dump}\n")

    # ---- 覆盖度分析 ----
    by_shop: dict[int, list[dict]] = defaultdict(list)
    for t in tasks:
        by_shop[t.get("shopId")].append(t)

    # 报告类型分布
    print("[3] 报告类型分布")
    type_count: dict[int, int] = defaultdict(int)
    for t in tasks:
        type_count[t.get("reportType")] += 1
    for rt in sorted(type_count):
        print(f"  reportType {rt}  {PLUG_TYPES.get(rt, '?'):<28} {type_count[rt]:>5} 条")
    print()

    # 月份 × 店铺 覆盖矩阵
    months = sorted({t.get("reportDayType") for t in tasks if t.get("reportDayType")})
    print(f"[4] 覆盖月份: {months}\n")

    shops_sorted = sorted(shops, key=lambda s: str(s.get("id")))
    if args.shop_pattern:
        shops_sorted = [s for s in shops_sorted
                        if args.shop_pattern in str(s.get("id"))
                        or args.shop_pattern.lower() in str(s.get("name", "")).lower()]

    covered, missing = [], []
    print(f"[5] 逐店覆盖（{len(shops_sorted)} 店 × {len(months)} 月）")
    hdr = "  {:<10} {:<26}".format("店铺ID", "店铺名") + "".join(f"{m[-2:]:>4}" for m in months)
    print(hdr + "   类型")
    for s in shops_sorted:
        sid = s.get("id")
        rows = by_shop.get(int(sid), [])
        cell = ""
        for m in months:
            rs = [t for t in rows if t.get("reportDayType") == m]
            if not rs:
                cell += "   -"
            elif any(t.get("status") == 1 for t in rs):
                cell += "   ✓"
            else:
                cell += "   ✗"
        types = sorted({t.get("reportType") for t in rows})
        mark = types and "  ".join(f"{PLUG_TYPES.get(x, x).split()[0]}" for x in types) or "**无任何报表**"
        print(f"  {str(sid):<10} {str(s.get('name'))[:26]:<26}{cell}   {mark}")
        (covered if rows else missing).append(s)

    print(f"\n[6] 结论")
    print(f"  有插件报表的店铺: {len(covered)}/{len(shops_sorted)}")
    print(f"  **无任何插件报表**: {len(missing)} 店")
    if missing:
        for s in missing[:40]:
            print(f"      {s.get('id')}  {s.get('name')}  {s.get('region')}/{s.get('marketplaceId')}")
        if len(missing) > 40:
            print(f"      ... 另有 {len(missing)-40} 店")
    print()
    print("  ⚠ 无报表 = 尚未用插件抓取 → 需运营在紫鸟(插件)侧对该账号执行一次抓取")
    print("  ⚠ 文件地址(fileUrls)是临时签名 URL，有效期 1 小时，不能存下来长期用")


if __name__ == "__main__":
    main()
