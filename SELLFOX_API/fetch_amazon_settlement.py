#!/usr/bin/env python3
"""Amazon 账期报表下载归档（只读赛狐 API + 只写本地）。

数据来源：赛狐 `报告中心/插件获取报告` = `/api/report/center/task/getPlugPageList.json`。
Amazon 账期(Transaction/Summary) **赛狐不自抓**，靠浏览器插件在账号登录态下抓回来存 COS；
本接口是**纯读**——只返回插件已抓结果的文件地址。所以「拉不到」= 插件侧还没抓过。

★ 关键约束：`fileUrls` 是 **1 小时有效的临时签名 URL**（腾讯 COS）。
  不能存链接，必须「调 API 拿新 URL → 立刻下载落盘」。

用法:
  # 看缺口、不下载
  uv run python fetch_amazon_settlement.py --start 2026-06-01 --end 2026-09-21 --dry-run

  # 下载归档（默认落到 <repo_root>/out/amazon_settlement）
  uv run python fetch_amazon_settlement.py --start 2026-06-01 --end 2026-09-21

  # 只下 Summary(PDF)
  uv run python fetch_amazon_settlement.py --start 2026-06-01 --end 2026-09-21 --types 4

归档结构:
  <out>/<报告月>/<店铺名>/<类型>-<原始文件名>
  <out>/_manifest.csv        本次实际下载了什么
  <out>/_gaps.csv            哪些店铺/月份没有任何报表（交给运营去插件补抓）
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
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
API_PACING_S = 2.0

TYPE_NAMES = {
    3: "Transaction",
    4: "Summary",
    5: "DeferredTransaction",
    6: "FBAInboundConvenience",
}
STATUS_OK = 1

MAGIC = [
    (b"PK\x03\x04", ".zip"),
    (b"%PDF", ".pdf"),
]


def raw_post(client: SellfoxClient, path: str, body: dict) -> dict[str, Any]:
    if client.config.mode != "proxy":
        raise SystemExit("本机不在 VPS 白名单，仅支持 proxy 模式")
    result, _ = client._post_once_proxy(path, body)
    time.sleep(API_PACING_S)
    return result


def all_shops(client: SellfoxClient) -> list[dict]:
    out: list[dict] = []
    page = 1
    while page <= 20:
        r = raw_post(client, SHOP_PATH, {"pageSize": 200, "pageNum": page})
        if r.get("code") != 0:
            raise SystemExit(f"店铺列表失败 code={r.get('code')} msg={r.get('msg')}")
        data = r.get("data") or {}
        rows = data.get("rows") or []
        out += rows
        if len(rows) < 200 or len(out) >= int(data.get("totalSize") or 0):
            break
        page += 1
    return out


def plug_tasks(client: SellfoxClient, start: str, end: str) -> list[dict]:
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
        print(f"    API 第 {page} 页 {len(rows)} 条（累计 {len(out)}）")
        if len(rows) < 200:
            break
        page += 1
    return out


def sniff_ext(data: bytes, url: str) -> str:
    for magic, ext in MAGIC:
        if data.startswith(magic):
            return ext
    return Path(urllib.parse.urlparse(url).path).suffix or ".csv"


def download(url: str, timeout: int = 300) -> bytes:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def safe_name(text: str) -> str:
    bad = '<>:"/\\|?*'
    return "".join("_" if c in bad else c for c in str(text)).strip() or "unknown"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default=(date.today() - timedelta(days=95)).isoformat(),
                    help="报告开始时间 yyyy-MM-dd")
    ap.add_argument("--end", default=date.today().isoformat(), help="报告结束时间 yyyy-MM-dd")
    ap.add_argument("--out", help="归档根目录，默认 <repo_root>/out/amazon_settlement")
    ap.add_argument("--types", help="只处理这些 reportType，逗号分隔，如 3,4")
    ap.add_argument("--shop-pattern", help="只看店铺名/ID 含该子串的")
    ap.add_argument("--dry-run", action="store_true", help="只列清单与缺口，不下载")
    ap.add_argument("--overwrite", action="store_true", help="已存在也重下")
    args = ap.parse_args()

    root = find_main_root()
    out_dir = Path(args.out) if args.out else root / "out" / "amazon_settlement"
    wanted = {int(x) for x in args.types.split(",")} if args.types else None

    client = SellfoxClient(SellfoxConfig.from_env(root / ".env"))
    print(f"repo_root={root}\n归档目录={out_dir}\n窗口 {args.start} → {args.end}")
    print(f"模式={'DRY-RUN' if args.dry_run else '下载'}\n")

    print("[1] 店铺列表")
    shops = all_shops(client)
    print(f"    {len(shops)} 店\n")

    print("[2] 插件报告任务")
    tasks = plug_tasks(client, args.start, args.end)
    print(f"    共 {len(tasks)} 条\n")

    if args.shop_pattern:
        shops = [s for s in shops
                 if args.shop_pattern in str(s.get("id"))
                 or args.shop_pattern.lower() in str(s.get("name", "")).lower()]
        keep = {int(s["id"]) for s in shops}
        tasks = [t for t in tasks if t.get("shopId") in keep]
        print(f"    --shop-pattern 过滤后：{len(shops)} 店 / {len(tasks)} 条\n")

    if wanted:
        tasks = [t for t in tasks if t.get("reportType") in wanted]

    # ---- 下载 ----
    manifest: list[dict] = []
    failures: list[dict] = []
    if not args.dry_run:
        print("[3] 下载")
        for i, t in enumerate(tasks, 1):
            if t.get("status") != STATUS_OK:
                continue
            rt = t.get("reportType")
            month = safe_name(t.get("reportDayType") or "unknown")
            shop = safe_name(t.get("shopName") or t.get("shopId"))
            type_name = TYPE_NAMES.get(rt, f"Type{rt}")
            urls = t.get("fileUrls") or []
            for idx, url in enumerate(urls):
                orig = Path(urllib.parse.urlparse(url).path).name
                prefix = f"{type_name}-" if len(urls) == 1 else f"{type_name}{idx + 1}-"
                # 前缀带类型，原始名保留月份等信息；后缀下载后按魔数定
                stem = f"{prefix}{orig}".rsplit(".", 1)[0] if "." in orig else f"{prefix}{orig}"
                dest_dir = out_dir / month / shop
                dest_dir.mkdir(parents=True, exist_ok=True)
                existing = list(dest_dir.glob(f"{stem}.*"))
                if existing and not args.overwrite:
                    print(f"    [{i}/{len(tasks)}] 已存在，跳过 {shop}/{month}/{stem}")
                    manifest.append({"月": month, "店铺": shop, "店铺ID": t.get("shopId"),
                                     "类型": type_name, "文件": existing[0].name,
                                     "字节": existing[0].stat().st_size, "状态": "已存在"})
                    continue
                try:
                    data = download(url)
                except Exception as e:  # noqa: BLE001
                    print(f"    [{i}/{len(tasks)}] ✗ 下载失败 {shop}/{month}: {type(e).__name__} {e}")
                    failures.append({"月": month, "店铺": shop, "类型": type_name,
                                     "错误": f"{type(e).__name__}: {e}"})
                    continue
                dest = dest_dir / f"{stem}{sniff_ext(data, url)}"
                dest.write_bytes(data)
                print(f"    [{i}/{len(tasks)}] ✓ {dest.relative_to(out_dir)}  {len(data):,} bytes")
                manifest.append({"月": month, "店铺": shop, "店铺ID": t.get("shopId"),
                                 "类型": type_name, "文件": dest.name,
                                 "字节": len(data), "状态": "已下载"})

        out_dir.mkdir(parents=True, exist_ok=True)
        if manifest:
            with open(out_dir / "_manifest.csv", "w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=list(manifest[0]))
                w.writeheader()
                w.writerows(manifest)
        if failures:
            with open(out_dir / "_failures.csv", "w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=list(failures[0]))
                w.writeheader()
                w.writerows(failures)

    # ---- 缺口清单（给运营）----
    by_shop: dict[int, set[str]] = defaultdict(set)
    for t in tasks:
        if t.get("status") == STATUS_OK:
            by_shop[t.get("shopId")].add(t.get("reportDayType"))
    months = sorted({t.get("reportDayType") for t in tasks if t.get("reportDayType")})

    gaps: list[dict] = []
    for s in sorted(shops, key=lambda x: str(x.get("id"))):
        have = by_shop.get(int(s.get("id")), set())
        if not have:
            gaps.append({"店铺ID": s.get("id"), "店铺名": s.get("name"),
                         "站点": s.get("marketplaceId"), "缺口": "完全没抓过（全部月份）",
                         "已有月份": ""})
        else:
            miss = [m for m in months if m not in have]
            if miss:
                gaps.append({"店铺ID": s.get("id"), "店铺名": s.get("name"),
                             "站点": s.get("marketplaceId"),
                             "缺口": ",".join(miss), "已有月份": ",".join(sorted(have))})

    print(f"\n[4] 覆盖与缺口")
    have_shops = sum(1 for s in shops if int(s.get("id")) in by_shop)
    never = [g for g in gaps if not g["已有月份"]]
    partial = [g for g in gaps if g["已有月份"]]
    print(f"    有报表 {have_shops}/{len(shops)} 店；覆盖月份: {months}")
    print(f"    ✗ 完全没抓过 {len(never)} 店  ← 需运营去插件侧补抓")
    print(f"    △ 缺部分月份 {len(partial)} 店  ← 可能当月无业务，也可能漏抓，需确认")
    if never:
        groups: dict[str, int] = defaultdict(int)
        for g in never:
            base = str(g["店铺名"])
            for sfx in ("-US", "-CA", "-MX", "-BR", "-ES", "-UK", "-FR", "-DE",
                        "-IT", "-TR", "-NL", "-SE", "-PL", "-BE", "-IE"):
                if base.endswith(sfx):
                    base = base[: -len(sfx)]
                    break
            groups[base] += 1
        print("    没抓过的店群:", ", ".join(f"{k}({v})" for k, v in sorted(groups.items())))

    if not args.dry_run and gaps:
        gap_csv = out_dir / "_gaps.csv"
        with open(gap_csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(gaps[0]))
            w.writeheader()
            w.writerows(gaps)
        print(f"    缺口清单 → {gap_csv}")
    elif args.dry_run and gaps:
        print(f"    （dry-run：缺口 {len(gaps)} 店，未写文件）")

    if not args.dry_run:
        ok = [m for m in manifest if m["状态"] == "已下载"]
        print(f"\n[5] 汇总：下载 {len(ok)} 个文件，"
              f"跳过 {len(manifest) - len(ok)}，失败 {len(failures)}")
        print(f"    归档目录 {out_dir}")
    print("\n⚠ 无报表 = 插件侧尚未抓取。需运营在赛狐/紫鸟的插件侧对该账号执行一次抓取。")


if __name__ == "__main__":
    main()
