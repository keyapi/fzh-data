# -*- coding: utf-8 -*-
"""Leadtime 快照刷新（只读 EN + ZMT 快照）。

血缘
- EN 原生 Shipment 的 custom_zmt_* 字段与 ZMT Shipment Snapshot 同源：
  Jack 的 PC 约 10 点爬虫批量更新 EN，ZMT CSV 是同一批导入快照。
- EN Shipment 当前全部 docstatus=0（Draft），但都是真实运单，必须全读；
  docstatus 0/1/2 全收，不只看 submitted。
- 两者可互相校验：EN 行级 + ZMT 大样本；行级不强行一一匹配。

输出
- leadtime_snapshot_YYYYMMDD.csv（长表：EN + ZMT 归一后的运单/分段）
- leadtime_snapshot_YYYYMMDD.json（按 source×main_haul×last_mile 的 n / 分段 / full_lt p50/p90）
- leadtime_refresh_YYYYMMDD.md（与上一版快照对比）
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests

B = "D:/Work/fzh-order-store"
BA = f"{B}/analysis"
ENV_PATH = "D:/Work/赛狐/Cursor/EN_API/.env"

EN_FIELDS = ["name", "docstatus", "status", "creation", "modified",
             "custom_zmt_transport", "custom_zmt_seg1", "custom_zmt_seg2",
             "custom_zmt_seg3", "custom_zmt_full_lt", "custom_zmt_atd",
             "custom_zmt_ata", "custom_zmt_appt", "custom_zmt_region",
             "custom_zmt_dest", "custom_zmt_pieces", "custom_zmt_cw", "custom_zmt_vol"]


def load_env(path=ENV_PATH):
    env = {}
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def main_haul(t: str) -> str:
    t = str(t)
    if "空运" in t:
        return "空运"
    if "美森" in t or "快船" in t:
        return "海运快船"
    if "海运" in t or "卡派" in t:
        return "海运普船"
    return "未知"


def last_mile(t: str) -> str:
    t = str(t)
    if "卡派" in t or "卡车" in t:
        return "卡车"
    if "快递" in t:
        return "快递"
    if "海运" in t:
        return "卡车"
    return "未知"


def stat(s: pd.Series):
    x = pd.to_numeric(s, errors="coerce").dropna()
    if len(x) == 0:
        return dict(n=0, p50=np.nan, p90=np.nan)
    return dict(n=int(len(x)), p50=float(x.median()), p90=float(x.quantile(0.9)))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Leadtime 快照刷新（只读）")
    ap.add_argument("--zmt", default=f"{BA}/zmt_shipment_snapshot_2026-11-02.csv")
    ap.add_argument("--out-dir", default=f"{BA}/leadtime")
    ap.add_argument("--date", default="2026-11-02")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    # ---------- EN 原生 Shipment（docstatus 0/1/2）
    env = load_env()
    base = "https://erpnext.vilavi.cn"
    h = {"Authorization": f"token {env['ERP_API_KEY']}:{env['ERP_API_SECRET']}"}
    r = requests.get(base + "/api/resource/Shipment", headers=h, timeout=60,
                     params={"fields": json.dumps(EN_FIELDS), "limit_page_length": 0,
                             "filters": json.dumps([["docstatus", "<", 3]])})
    r.raise_for_status()
    en = pd.DataFrame(r.json()["data"])
    en["source"] = "en_shipment"
    en["shipment"] = en["name"]
    en["docstatus"] = pd.to_numeric(en["docstatus"], errors="coerce")

    # ---------- ZMT 快照
    z = pd.read_csv(args.zmt)
    z["source"] = "zmt_snapshot"
    z["shipment"] = z["name"]
    z["docstatus"] = np.nan

    common = {"transport": ["custom_zmt_transport", "transport"],
              "seg1": ["custom_zmt_seg1", "seg1"],
              "seg2": ["custom_zmt_seg2", "seg2"],
              "seg3": ["custom_zmt_seg3", "seg3"],
              "full_lt": ["custom_zmt_full_lt", "full_lt"],
              "atd": ["custom_zmt_atd", "atd"],
              "ata": ["custom_zmt_ata", "ata"],
              "region": ["custom_zmt_region", "region"],
              "dest": ["custom_zmt_dest", "dest"]}
    rows = []
    for _, e in en.iterrows():
        rec = dict(source="en_shipment", shipment=e["shipment"], docstatus=e["docstatus"],
                   status=e.get("status"), transport=e.get("custom_zmt_transport"),
                   carrier=None, way=None, appt=e.get("custom_zmt_appt"),
                   pieces=e.get("custom_zmt_pieces"), cw=e.get("custom_zmt_cw"),
                   vol=e.get("custom_zmt_vol"))
        for k, (ec, zc) in common.items():
            rec[k] = e.get(ec)
        rows.append(rec)
    for _, q in z.iterrows():
        rec = dict(source="zmt_snapshot", shipment=q["shipment"], docstatus=None,
                   status=q.get("status"), transport=q.get("transport"),
                   carrier=q.get("carrier"), way=q.get("way"),
                   appt=q.get("eta"), pieces=q.get("pieces"), cw=q.get("cw"),
                   vol=q.get("vol"))
        for k, (ec, zc) in common.items():
            rec[k] = q.get(zc)
        rows.append(rec)
    df = pd.DataFrame(rows)
    df["main_haul"] = df["transport"].map(main_haul)
    df["last_mile"] = df["transport"].map(last_mile)
    for c in ("seg1", "seg2", "seg3", "full_lt", "pieces", "cw", "vol"):
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # ---------- 汇总（full_lt>0 才用于分段/总时长）
    done = df[df["full_lt"] > 0].copy()
    summary = []
    for (src, mh, lm), g in done.groupby(["source", "main_haul", "last_mile"], dropna=False):
        summary.append(dict(source=src, main_haul=mh, last_mile=lm, n=len(g),
                            seg1=stat(g["seg1"]), seg2=stat(g["seg2"]),
                            seg3=stat(g["seg3"]), full_lt=stat(g["full_lt"])))
    # EN vs ZMT 对照（按 main/last）
    cmp_rows = []
    for (mh, lm), g in done.groupby(["main_haul", "last_mile"]):
        e = g[g["source"] == "en_shipment"]
        q = g[g["source"] == "zmt_snapshot"]
        if len(e) or len(q):
            cmp_rows.append(dict(main_haul=mh, last_mile=lm,
                                 en_n=len(e), en_p50=stat(e["full_lt"])["p50"],
                                 en_p90=stat(e["full_lt"])["p90"],
                                 zmt_n=len(q), zmt_p50=stat(q["full_lt"])["p50"],
                                 zmt_p90=stat(q["full_lt"])["p90"]))
    payload = dict(
        generated_at=datetime.now().astimezone().isoformat(),
        date=args.date,
        lineage=("EN Shipment custom_zmt_* 与 ZMT Snapshot 同源：Jack PC 约 10 点爬虫批量更新 EN，"
                 "ZMT CSV 是同一批导入快照；EN docstatus=0 Draft 但为真实运单，全读 0/1/2。"),
        counts=dict(en_rows=len(en), en_docstatus=en["docstatus"].value_counts().to_dict(),
                    zmt_rows=len(z), zmt_full_lt_positive=int((z["full_lt"] > 0).sum())
                    if "full_lt" in z else 0,
                    zmt_month=z["month"].astype(str).value_counts().sort_index().to_dict()
                    if "month" in z else {}),
        summary=summary, en_vs_zmt=cmp_rows,
    )

    # 与上一版快照对比
    prev_files = sorted(Path(args.out_dir).glob("leadtime_snapshot_*.json"))
    prev = None
    for p in reversed(prev_files):
        if args.date not in p.name:
            prev = p
            break
    if prev:
        pj = json.loads(prev.read_text(encoding="utf-8"))
        payload["compare_previous"] = dict(previous=prev.name,
                                           zmt_rows_prev=pj["counts"]["zmt_rows"],
                                           en_rows_prev=pj["counts"]["en_rows"])

    print(f"EN Shipment: {len(en)} 行，docstatus {en['docstatus'].value_counts().to_dict()}")
    print(f"ZMT Snapshot: {len(z)} 行；full_lt>0 {payload['counts']['zmt_full_lt_positive']}")
    print("分段/总时长（full_lt>0）:")
    for s in summary:
        print(f"  {s['source']:12s} {s['main_haul']}/{s['last_mile']}: n={s['n']} "
              f"full_lt {s['full_lt']['p50']}/{s['full_lt']['p90']} "
              f"seg1 {s['seg1']['p50']}/{s['seg1']['p90']} "
              f"seg2 {s['seg2']['p50']}/{s['seg2']['p90']} "
              f"seg3 {s['seg3']['p50']}/{s['seg3']['p90']}")

    if args.dry_run:
        return 0

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / f"leadtime_snapshot_{args.date.replace('-', '')}.csv"
    json_path = out / f"leadtime_snapshot_{args.date.replace('-', '')}.json"
    md_path = out / f"leadtime_refresh_{args.date.replace('-', '')}.md"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    lines = [
        f"# Leadtime 快照刷新（{args.date}）",
        "",
        f"- 生成时间：{payload['generated_at']}",
        f"- EN 原生 Shipment：**{len(en)}** 行（docstatus {payload['counts']['en_docstatus']}），全读 0/1/2。",
        f"- ZMT Snapshot：**{len(z)}** 行；full_lt>0 **{payload['counts']['zmt_full_lt_positive']}**。",
        f"- 血缘：{payload['lineage']}",
        "",
        "## 分段与总时长（full_lt>0）",
        "",
        "| source | main_haul | last_mile | n | seg1 p50/p90 | seg2 p50/p90 | seg3 p50/p90 | full_lt p50/p90 |",
        "|---|---|---|---:|---|---|---|---|",
    ]
    for s in summary:
        lines.append(f"| {s['source']} | {s['main_haul']} | {s['last_mile']} | {s['n']} | "
                     f"{s['seg1']['p50']:.0f}/{s['seg1']['p90']:.0f} | "
                     f"{s['seg2']['p50']:.0f}/{s['seg2']['p90']:.0f} | "
                     f"{s['seg3']['p50']:.0f}/{s['seg3']['p90']:.0f} | "
                     f"{s['full_lt']['p50']:.0f}/{s['full_lt']['p90']:.0f} |")
    lines += ["", "## EN vs ZMT 校验（full_lt）", "",
              "| main/last | EN n | EN p50/p90 | ZMT n | ZMT p50/p90 |",
              "|---|---:|---|---:|---|"]
    for c in cmp_rows:
        lines.append(f"| {c['main_haul']}/{c['last_mile']} | {c['en_n']} | "
                     f"{c['en_p50']:.0f}/{c['en_p90']:.0f} | {c['zmt_n']} | "
                     f"{c['zmt_p50']:.0f}/{c['zmt_p90']:.0f} |")
    if prev:
        lines += ["", f"- 上一版快照：`{prev.name}`；对比已写入 JSON `compare_previous`。"]
    lines += ["", "## 限制", "- EN 当前 docstatus=0（Draft），但为真实运单；不按 submitted 过滤。",
              "- ZMT 仅 2026-06..10 五个月，非全年稳定分布；分段为经验值。"]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n已写：{csv_path}\n      {json_path}\n      {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
