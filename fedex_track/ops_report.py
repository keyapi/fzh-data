"""fedex_track 运营异常报表：分类逻辑在 parcel_track.classify，Excel 写出共用 ops_excel。"""

from __future__ import annotations

import re

import pandas as pd

from parcel_track.classify import (
    HANDLING_DAYS,
    STUCK_DAYS,
    TRANSIT_SEVERE_DAYS,
    TRANSIT_SLOW_DAYS,
    TT_PICK,
    _bare_tracking,
    _late_level,
    _to_ts,
    bizdays,
    load_tt_identity,
)
from parcel_track.classify import CLASS as SHARED_CLASS
from parcel_track.classify import _cat as _cat_shared
from parcel_track.ops_excel import write_ops_workbook

CLASS = {**SHARED_CLASS, "fedex_slow": ("FedEx延误", "fedex_slow", "orange")}
SHEET_OF_CLASS = {
    "missing_not_handed": "漏发未交接",
    "fresh_no_pickup": "漏发未交接",
    "late_handover": "迟发",
    "fedex_slow": "承运异常",
    "carrier_slow": "承运异常",
    "stuck": "承运异常",
    "cancelled": "取消·其他",
    "not_found": "取消·其他",
}
ACTION = {
    "missing_not_handed": "通知仓库/货代核查是否漏发或未交接；未发出→取消或补发，已交但无扫描→开FedEx trace",
    "fresh_no_pickup": "持续关注是否转漏发；与仓确认交接；超过N天按漏发处理",
    "late_handover": "交接SLA复盘；对已延误买家提前告知/安抚；根因治理（仓、货代排程）",
    "fedex_slow": "记录；超过严重阈值→开FedEx trace/索赔",
    "carrier_slow": "记录；超过严重阈值→开承运商 trace/索赔",
    "stuck": "开FedEx trace调查；超14天→索赔+重发/退款",
    "cancelled": "确认取消原因（我方撤单/货代/FedEx），按需退款或重下",
    "not_found": "核查通途源数据（如拼接号/非FedEx号）；非FedEx单改走对应渠道",
    "reused_no_label": "复用号旧票，从建标开始的对应票为准；无需处理",
    "delivered_ok": "—",
    "in_transit": "—",
}


def _cat(dev, pu, label, ship, now, last_event=None):
    key = _cat_shared(dev, pu, label, ship, now, last_event=last_event)
    return "fedex_slow" if key == "carrier_slow" else key


def build(summary_csv: str, tt_xlsx: str, out_xlsx: str):
    S = pd.read_csv(summary_csv, dtype=str).fillna("")
    tt = load_tt_identity(tt_xlsx)
    now = pd.Timestamp(_dt.datetime.now())
    rows = []
    for _, r in S.iterrows():
        n = r["跟踪号"]
        dev = _to_ts(r["交付时间"])
        pu = _to_ts(r["站点收件时间"])
        label = _to_ts(r["建标时间"])
        last_event = _to_ts(r["最近节点时间"]) if "最近节点时间" in r.index else pd.NaT
        ident = tt.get(_bare_tracking(n), tt.get(n, {}))
        ship = pd.NaT
        remark = r["备注"] if "备注" in r.index else ""
        m = re.search(r"发货日期=([0-9-]+)", str(remark))
        if m:
            ship = pd.to_datetime(m.group(1), errors="coerce")
        if (ship is pd.NaT or pd.isna(ship)) and ident.get("发货日期"):
            ship = pd.to_datetime(ident.get("发货日期"), errors="coerce")
        cat_key = _cat(dev, pu, label, ship, now, last_event=last_event)
        if r.get("已取消", "") == "是" and dev is pd.NaT:
            cat_key = "cancelled"
        if r.get("当前状态", "") == "查无此号":
            cat_key = "not_found"
        zh, en, _base = CLASS[cat_key]
        overdue = None
        bd = bizdays(label, pu)
        if bd is not None:
            overdue = bd - HANDLING_DAYS
        trans = bizdays(pu, dev) if (dev is not pd.NaT and pu is not pd.NaT) else None
        if cat_key == "late_handover":
            level = _late_level(overdue)
        elif cat_key in ("fedex_slow", "carrier_slow"):
            level = "严重延误" if (trans is not None and trans > TRANSIT_SEVERE_DAYS) else zh
        else:
            level = zh
        amazon = "" if overdue is None else ("是" if overdue > 0 else "否")
        caldays = int((pu - label).days) if (pu is not pd.NaT and label is not pd.NaT) else ""
        rows.append({
            "跟踪号": n, "承运商": "fedex", "分类(EN)": en, "分类(中文)": zh, "等级": level,
            "订单号": ident.get("订单号", ""), "包裹号": ident.get("包裹号", ""),
            "渠道账号": ident.get("渠道账号", ""), "渠道": ident.get("渠道", ""),
            "平台SKU": ident.get("平台SKU", ""), "通途SKU": ident.get("通途SKU", ""),
            "产品名称": ident.get("产品名称", "")[:40], "发货仓库": ident.get("发货仓库", ""),
            "执行发货人": ident.get("执行发货人", ""), "是否补发货": ident.get("是否补发货", ""),
            "销售站点": ident.get("销售站点", ""), "买家姓名": ident.get("买家姓名", ""),
            "国家": ident.get("国家/地区", ""), "城市": ident.get("城市", ""), "省/州": ident.get("省/州", ""),
            "发货日期": ship.date() if ship is not pd.NaT else "",
            "建标时间": label, "站点收件时间": pu, "交付时间": dev,
            "日历延迟(天)": caldays, "营业日延迟(天)": overdue, "承运延迟(营业日)": trans,
            "Amazon是否判迟": amazon, "所属Sheet": SHEET_OF_CLASS.get(cat_key, ""),
            "建议动作": ACTION.get(cat_key, ""), "处理状态": "",
            "_key": cat_key,
        })
    df = pd.DataFrame(rows)
    write_ops_workbook(
        df, out_xlsx,
        title="FedEx 运营异常总览（Amazon 口径 · 营业日）",
        slow_label="FedEx延误",
        notes_title="FedEx 异常运营报表口径说明（v2）",
    )
    return df


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--summary", required=True)
    p.add_argument("--tt", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    df = build(a.summary, a.tt, a.out)
    print("total rows", len(df))
    print(df["分类(中文)"].value_counts().to_dict())
    print("written", a.out)
