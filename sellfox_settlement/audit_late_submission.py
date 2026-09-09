# -*- coding: utf-8 -*-
"""账期提交审计（单文件多账期桶）。

读钉钉后台「销售收款确认单」导出（可跨多月、多 sheet），按「账期日期自然月」归属账期月，
按「发起时间 4号~下月3号」归提交桶，判 正常/迟交/遗档/早交，输出逐月汇总 + 异常单明细。

规则（本项目口径）：
  账期归属 = 账期日期所在自然月 Z（1号~月末）。
  提交窗口 = [Z月4日, (Z+1)月3日]；提交时间 = 发起时间。
  桶(发起) = 发起落在 4号~下月3号 的窗口；桶月 = 窗口起始自然月。
  判类：Z==桶月→正常；Z<桶月→迟交(混入下月；年份更早→遗档)；Z>桶月→早交(下月账期提前混入本桶)。
  迟交天数 = 发起日 − (Z+1)/3。

用法：
  uv run python sellfox_settlement/audit_late_submission.py \
     "D:/Work/王忠于/成本核算/Amazon&新平台成本 20260101-20260908 销售收款确认单-20260909140003.xlsx" \
     --out out/late_submission_audit --platform 亚马逊
"""
from __future__ import annotations

import argparse
import collections
import pathlib
import re

import pandas as pd

# 钉钉原始导出列（取第一个存在的）
ACCT_COLS = ["渠道账号", "销售账户", "渠道账号别名", "亚马逊销售账户", "新平台销售账户"]
MONEY_COLS = ["应收金额", "销售额", "账期收款额"]


def read_dingtalk_xlsx(path):
    xp = pd.ExcelFile(path)
    frames = []
    for sn in xp.sheet_names:
        hdr = xp.parse(sn, header=None, nrows=8)
        hr_i = None
        for i in range(min(8, len(hdr))):
            row = [str(x).strip() if pd.notna(x) else "" for x in hdr.iloc[i]]
            if "账期日期" in row:
                hr_i = i
                break
        if hr_i is None:
            continue
        df = xp.parse(sn, header=hr_i)
        if "账期日期" not in df.columns:
            continue
        df = df[df["账期日期"].notna()]
        if df.empty:
            continue
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _ym(v):
    d = pd.to_datetime(v, errors="coerce")
    if pd.isna(d):
        return ""
    return f"{d.year:04d}-{d.month:02d}"


def _ymm(v):  # YYYYMM
    return _ym(v).replace("-", "")


def _bucket_month(d):
    """发起日期落在哪个 4号~下月3号 桶 → 返回桶起始月 label YYYY-MM。"""
    if d is None or pd.isna(d):
        return ""
    if d.day >= 4:
        return f"{d.year:04d}-{d.month:02d}"
    y, m = d.year, d.month - 1
    if m == 0:
        y, m = y - 1, 12
    return f"{y:04d}-{m:02d}"


def _window_end(ym):  # (Z+1)/3 截止
    y, m = int(ym[:4]), int(ym[5:7]) + 1
    if m == 13:
        y, m = y + 1, 1
    return pd.Timestamp(y, m, 3)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("xlsx", help="钉钉导出 xlsx（可多 sheet、跨多月）")
    p.add_argument("--out", required=True, help="输出文件前缀/目录")
    p.add_argument("--platform", default="", help="只留某平台，如 亚马逊")
    p.add_argument("--min-year", default="2026", help="below this year 账期 → 遗档；默认 2026")
    args = p.parse_args()

    df = read_dingtalk_xlsx(args.xlsx)
    print("总行(去重前)：", len(df))
    if df.empty:
        print("无数据"); return

    if args.platform and "选择平台" in df.columns:
        df = df[df["选择平台"].astype(str).str.strip() == args.platform]
        print(f"平台过滤 {args.platform} → {len(df)}")

    # 列名标准化
    acct = next((c for c in ACCT_COLS if c in df.columns), None)
    money = next((c for c in MONEY_COLS if c in df.columns), None)
    df["_账期"] = pd.to_datetime(df["账期日期"], errors="coerce")
    df["_发起"] = pd.to_datetime(df["发起时间"], errors="coerce")
    df["_完成"] = pd.to_datetime(df["完成时间"], errors="coerce")
    df["_Z"] = df["_账期"].apply(_ym)            # 账期月 YYYY-MM
    df["_B"] = df["_发起"].apply(_bucket_month)  # 提交桶月
    df["_平台"] = df["选择平台"].astype(str).str.strip() if "选择平台" in df.columns else ""

    # 去重
    keys = [k for k in ["审批编号", "账期日期", acct, money] if k and k in df.columns]
    before = len(df)
    df = df.drop_duplicates(subset=keys, keep="first") if keys else df
    print(f"去重后 {len(df)}（去掉 {before - len(df)}）")

    # 判类
    def classify(r):
        Z, B = r["_Z"], r["_B"]
        if not Z or not B:
            return "未知", None
        if Z < B:
            if int(Z[:4]) < int(args.min_year):
                return "遗档", None
            end = _window_end(Z)
            return "迟交", (r["_发起"] - end).days
        if Z > B:
            return "早交", None
        return "正常", None

    cls = df.apply(classify, axis=1)
    df["_class"] = [c for c, _ in cls]
    df["_days"] = [d for _, d in cls]

    res = collections.defaultdict(lambda: collections.Counter())
    for _, r in df.iterrows():
        res[r["_Z"]][r["_class"]] += 1

    print("\n=== 逐账期月汇总 ===")
    print(f"{'账期月':9s} {'总':>4s} {'正常':>4s} {'迟交':>4s} {'迟交天(min~max)':>18s} {'遗档':>4s} {'早交':>4s}")
    rows = []
    late_by = collections.defaultdict(list)
    for _, r in df.iterrows():
        if r["_class"] == "迟交":
            late_by[r["_Z"]].append(r["_days"])
    for z in sorted(res):
        c = res[z]
        la = late_by.get(z, [])
        dmin = min(la) if la else "-"
        dmax = max(la) if la else "-"
        print(f"{z:9s} {c['正常']+c['迟交']+c['遗档']+c['早交']:4d} {c['正常']:4d} {c['迟交']:4d} "
              f"{dmin}~{dmax:>4}  {c['遗档']:4d} {c['早交']:4d}")
        rows.append([z, c.get("正常",0), c.get("迟交",0), dmin, dmax, c.get("遗档",0), c.get("早交",0)])

    # cross-month 迟交（落入下月桶的）
    print("\n=== 按桶汇总：迟交混入下月桶的账期月分布 ===")
    for b in sorted(set(df["_B"])):
        sub = df[(df["_B"] == b) & (df["_class"].isin(["迟交","遗档"]))]
        if sub.empty:
            continue
        dist = collections.Counter(sub["_Z"])
        print(f"  提交桶 {b}: " + ", ".join(f"{zz}×{n}" for zz, n in sorted(dist.items())))

    # 输出 xlsx + md
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    md = pathlib.Path(args.out + ".md")
    with open(md, "w", encoding="utf-8") as fh:
        fh.write("# 账期提交审计\n\n## 逐账期月\n\n")
        fh.write("| 账期月 | 总 | 正常 | 迟交 | 迟交天 | 遗档 | 早交 |\n|---|---|---|---|---|---|---|\n")
        for r in rows:
            fh.write(f"| {r[0]} | {r[1]+r[2]+r[5]+r[6]} | {r[1]} | {r[2]} | {r[3]}~{r[4]} | {r[5]} | {r[6]} |\n")
    # detail xlsx
    with pd.ExcelWriter(out / "late_submission_detail.xlsx") as xw:
        pd.DataFrame(rows, columns=["账期月","正常","迟交","迟交天min","迟交天max","遗档","早交"]).to_excel(xw, sheet_name="逐月汇总", index=False)
        cols = [c for c in (["审批编号","标题","账期日期","发起时间","完成时间","选择平台",acct,money,"_Z","_B","_class","_days"]) if c and c in df.columns]
        df[cols].rename(columns={"_Z":"账期月","_B":"提交桶","_class":"分类","_days":"迟交天数",acct or "":"账号",money or "":"金额"}).to_excel(xw, sheet_name="异常单明细", index=False)
    print(f"\n[写] {md}\n[写] {out/'late_submission_detail.xlsx'}")


if __name__ == "__main__":
    main()
