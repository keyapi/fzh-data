# -*- coding: utf-8 -*-
"""赛狐 Amazon 结算自动取回 + 与运营钉钉提交值比对（试点原型）

只依赖标准库 + 仓库内 SELLFOX_API.client.SellfoxClient（代理或直连均可）。

用法（先设置 SELLFOX_API_KEY 于 D:\\Work\\赛狐\\Cursor\\.env 或环境变量）:
  uv run python sellfox_settlement/reconcile_amazon.py shops
  uv run python sellfox_settlement/reconcile_amazon.py fetch --start 2026-06-01 --end 2026-07-10 --out data/saihu_amazon_202606
  uv run python sellfox_settlement/reconcile_amazon.py candidates --detail data/saihu_amazon_202606/detail.csv
  uv run python sellfox_settlement/reconcile_amazon.py reconcile \
      --settlement data/saihu_amazon_202606 --dingtalk "D:/Work/王忠于/成本核算/Amazon&新平台成本 20260604-20260703 销售收款确认单-20260706111631_合并汇率&账号_2026-07-06_11-52-51.xlsx" \
      --month 202606 --out out/amazon_compare_202606.xlsx
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import pathlib
import sys
import time
import urllib.request
import zipfile
from collections import Counter, defaultdict

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# 渠道账号列：钉钉合并文件里的列名（取第一个存在的）
DINGTALK_ACCOUNT_COLS = ["渠道账号", "销售账户", "渠道账号别名", "亚马逊销售账户"]
MONEY_COLS = ["销售额", "佣金", "广告费", "退款", "应收金额", "收款费用累加外币"]
PERIOD_RE = re = None  # placeholder


# ---------------------------------------------------------------- client
def get_client():
    from SELLFOX_API.client import SellfoxClient, SellfoxConfig

    parent_env = pathlib.Path(r"D:\Work\赛狐\Cursor\.env")
    cfg = SellfoxConfig.from_env(REPO_ROOT / ".env", parent_env)
    return SellfoxClient(cfg)


# ---------------------------------------------------------------- helpers
def extract_rows(data):
    """从结算中心返回的 data 里取列表（不同接口字段名不同，做防御性探测）。"""
    if not isinstance(data, dict):
        return []
    for key in ("detailPageVoList", "rows", "groupList", "resultList", "list", "records"):
        val = data.get(key)
        if isinstance(val, list):
            return val
    # 兜底：递归找第一个列表
    for val in data.values():
        if isinstance(val, list) and val and isinstance(val[0], dict):
            return val
    return []


def flatten(rows):
    """把 dict 列表拍平成 (dict[str,str]，并 collect 所有字段名)。"""
    fields = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    out = []
    for r in rows:
        out.append({k: r.get(k) for k in fields})
    return fields, out


def write_csv(path, fields, rows):
    parent = pathlib.Path(path).parent
    parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def fetch_paged(client, url_path, body, start, end):
    """分页拉取。body 里可先给 startTime/endTime/timeType；pageNo/pageSize 按 schema 用字符串。"""
    body = dict(body or {})
    body.setdefault("startTime", start)
    body.setdefault("endTime", end)
    body.setdefault("pageNo", "1")
    body.setdefault("pageSize", "200")
    all_rows = []
    first = client.signed_post(url_path, dict(body))
    rows = extract_rows(first)
    all_rows.extend(rows)
    total = None
    if isinstance(first, dict) and first.get("totalSize") is not None:
        total = int(first["totalSize"])
    size = int(body.get("pageSize", len(rows) or 1))
    pages = -(-total // size) if total else 1
    for p in range(2, pages + 1):
        time.sleep(2)
        data = client.signed_post(url_path, dict(body, pageNo=str(p)))
        all_rows.extend(extract_rows(data))
    return all_rows


# ---------------------------------------------------------------- commands
def cmd_shops(client):
    shops = client.list_shops()
    print(f"共 {len(shops)} 个店铺")
    print(f"{'id':>8}  {'region':<8} {'marketplaceId':<14} {'adStatus':<4}  name")
    for s in shops:
        print(
            f"{str(s.get('id')):>8}  {str(s.get('region','')):<8} "
            f"{str(s.get('marketplaceId','')):<14} {str(s.get('adStatus','')):<4}  {s.get('name','')}"
        )
    print("\n小写名称：")
    for s in shops:
        print(f"  {s.get('name','')}  ->  {(s.get('name','') or '').strip().upper()}")


def cmd_fetch(client, args):
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    shop_ids = [x.strip() for x in (args.shop or "").split(",") if x.strip()] or None
    if shop_ids:
        shop_ids = [int(x) if x.lstrip("-").isdigit() else x for x in shop_ids]
    month = args.month or args.start[:7].replace("-", "")

    # 1) 汇总（按结算结束日筛选 → 账期月=groupEndStr 所在自然月）
    print("== 拉取结算汇总 groupPage（按结算结束日 =", month, "）==")
    sum_body = {"timeType": "settlementEndTime", "pageNo": "1", "pageSize": "200"}
    if shop_ids:
        sum_body["shopIds"] = shop_ids
    if args.marketplace:
        sum_body["marketplaceIds"] = [m.strip() for m in args.marketplace.split(",") if m.strip()]
    if args.currency:
        sum_body["currency"] = args.currency
    srows = fetch_paged(client, "/api/financial/v2/settlementSummary/groupPage.json",
                        sum_body, args.start, args.end)
    sf, sd = flatten(srows)
    write_csv(out / "summary.csv", sf, sd)
    print(f"  汇总 {len(srows)} 行 → {out/'summary.csv'}")

    # 2) 结算结束日归属月份的 settlementId 集
    def gs(r):
        g = r.get("groupEndStr") or r.get("settlementEndDate") or ""
        return str(g)[:7].replace("-", "")
    settle_ids = {r.get("settlementId") for r in srows if gs(r) == month and r.get("settlementId")}
    print(f"  归属月份 {month} 的结算 settlementId 数: {len(settle_ids)}")

    # 3) 明细（先按 posted 日期窗口拉，再按 settlementId 过滤到当月结算）
    #    currency 参数默认 CNY；传具体币种（如 USD）可返回原币。
    print("== 拉取结算明细 detailPage（posted 日期窗口, currency=" + (args.currency or "CNY默认") + "）==")
    det_body = {"pageNo": "1", "pageSize": "200"}
    if args.currency:
        det_body["currency"] = args.currency
    drows = fetch_paged(client, "/api/financial/v2/settlementSummary/detailPage.json",
                        det_body, args.start, args.end)
    df_, dd = flatten(drows)
    write_csv(out / "detail.csv", df_, dd)
    print(f"  明细 {len(drows)} 行 → {out/'detail.csv'}")
    if settle_ids:
        det_june = [r for r in drows if r.get("settlementId") in settle_ids]
        write_csv(out / "detail_june.csv", df_, det_june)
        print(f"  按 settlementId 过滤当月明细 {len(det_june)} 行 → {out/'detail_june.csv'}")


def cmd_candidates(args):
    import pandas as pd

    df = pd.read_csv(args.detail, encoding="utf-8-sig")
    keys = [k for k in ("transactionType", "amountType", "amountDescription") if k in df.columns]
    g = df.groupby(keys, dropna=False).size().reset_index(name="count")
    if "amount" in df.columns:
        amt = df.groupby(keys, dropna=False)["amount"].sum().reset_index(name="amount_sum")
        g = g.merge(amt, on=keys, how="left")
    print(f"未识别科目候选（去重，{len(g)} 组）:")
    print(g.to_string())
    print("\namount 符号分布（看正负口径）:")
    print(df["amount"].apply(lambda x: "pos" if float(x) > 0 else ("neg" if float(x) < 0 else "zero")).value_counts())


def cmd_reconcile(args):
    import pandas as pd

    # --- 读赛狐明细+汇总 ---
    settle_dir = pathlib.Path(args.settlement)
    if (settle_dir / "detail.csv").exists():
        det = pd.read_csv(settle_dir / "detail.csv", encoding="utf-8-sig")
    else:
        det = pd.DataFrame()
    if (settle_dir / "summary.csv").exists():
        summ = pd.read_csv(settle_dir / "summary.csv", encoding="utf-8-sig")
    else:
        summ = pd.DataFrame()

    # --- 读钉钉 -----------------------------------------------------------------
    dfile = args.dingtalk
    wb = pd.read_excel(dfile, sheet_name=None)
    dw = wb[sorted(wb)[0]]  # 取第一个 sheet
    # 表头：合并文件 header 在第 0 行
    # 找合适账号列
    acct_col = next((c for c in DINGTALK_ACCOUNT_COLS if c in dw.columns), "选择平台")
    cur_col = next((c for c in ("收款币种", "币种") if c in dw.columns), None)
    money_present = [c for c in MONEY_COLS if c in dw.columns]
    groupkeys = [acct_col] + ([cur_col] if cur_col else [])
    dsum = dw.groupby(groupkeys, dropna=False)[money_present].sum().reset_index()
    dsum = dsum.rename(columns={acct_col: "account"})

    # --- 科目映射（赛狐明细→ 钉钉科目） ------------------------------------------
    # 工作假设，需用 candidates 结果人工校准后覆盖
    SUBJ = {
        "销售额": lambda r: r.get("amountType") in ("Principal",) or r.get("amountDescription") in ("Principal",),
        "佣金": lambda r: "commission" in str(r.get("amountDescription", "")).lower() or str(r.get("amountType", "")).lower() in ("commission", "marketplacefacilitatorfee"),
        "广告费": lambda r: "advertising" in str(r.get("amountDescription", "")).lower() or "sponsored" in str(r.get("amountDescription", "")).lower(),
        "退款": lambda r: "refund" in str(r.get("transactionType", "")).lower() or "refund" in str(r.get("amountType", "")).lower(),
        "稅": lambda r: str(r.get("amountType", "")).lower() == "tax" or "withholding" in str(r.get("amountDescription", "")).lower() or "tax" in str(r.get("amountDescription", "")).lower(),
        "平台月租": lambda r: "subscription" in str(r.get("amountDescription", "")).lower() or "月租" in str(r.get("amountDescription", "")),
    }
    def map_subject(r):
        for name, fn in SUBJ.items():
            try:
                if fn(r):
                    return name
            except Exception:
                continue
        return "其他/未识别"

    if len(det):
        det = det.copy()
        det["subject"] = det.apply(map_subject, axis=1)
        det["amount"] = pd.to_numeric(det.get("amount"), errors="coerce").fillna(0.0)
        # 账号：优先 settlement 里的 storeName
        det["account"] = det.get("storeName", det.get("渠道账号", ""))
        per_subj = det.groupby(["account", "subject"])["amount"].sum().unstack(fill_value=0.0)
        per_subj = per_subj.reset_index()
    else:
        per_subj = pd.DataFrame()

    # --- 汇总净收入（赛狐） ---
    if len(summ):
        summ = summ.copy()
        summ["account"] = summ.get("storeName", "")
        summ["net"] = pd.to_numeric(summ.get("accountNetIncome"), errors="coerce").fillna(0.0)
        summ["income"] = pd.to_numeric(summ.get("accountIncome"), errors="coerce").fillna(0.0)
        summ["exp"] = pd.to_numeric(summ.get("accountExpenditure"), errors="coerce").fillna(0.0)
        net_by_account = summ.groupby("account")[["net", "income", "exp"]].sum().reset_index()

    # --- 合并比对 ---
    rows = []
    accounts = set()
    if len(per_subj):
        accounts |= set(per_subj["account"])
    if len(net_by_account):
        accounts |= set(net_by_account["account"])
    if len(dsum):
        accounts |= set(dsum["account"])
    for a in sorted(accounts, key=lambda x: str(x)):
        row = {"account": a}
        sd = per_subj[per_subj["account"] == a] if len(per_subj) else pd.DataFrame()
        dd2 = dsum[dsum["account"] == a] if len(dsum) else pd.DataFrame()
        sb = net_by_account[net_by_account["account"] == a] if len(net_by_account) else pd.DataFrame()
        for subj in ("销售额", "佣金", "广告费", "退款", "平台月租", "其他/未识别"):
            row[f"赛狐.{subj}"] = (sd[subj].iloc[0] if len(sd) and subj in sd.columns else 0.0)
        for col in ("销售额", "佣金", "广告费", "退款", "应收金额"):
            row[f"钉钉.{col}"] = (dd2[col].iloc[0] if len(dd2) and col in dd2.columns else 0.0)
        row["赛狐.净收入"] = float(sb["net"].iloc[0]) if len(sb) else 0.0
        rows.append(row)
    report = pd.DataFrame(rows)
    report["销售额差"] = report["赛狐.销售额"] - report["钉钉.销售额"]
    report["佣金差"] = report["赛狐.佣金"] - report["钉钉.佣金"]
    report["广告差"] = report["赛狐.广告费"] - report["钉钉.广告费"]
    report["净收入差"] = report["赛狐.净收入"] - report["钉钉.应收金额"]

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    report.to_excel(out, index=False)
    print(report.to_string())
    print("\n[写] ", out)

    # 未识别科目占赛狐总金额比
    if len(det):
        total = det["amount"].abs().sum()
        unk = det[det["subject"] == "其他/未识别"]["amount"].abs().sum()
        print(f"未识别科目金额占比 {unk / total:.1%}" if total else "无明细")


def cmd_fetch_custom(client, args):
    """拉取紫鸟/赛狐插件已抓到的 Amazon「列式」报表文件（getPlugPageList）。
    reportType: 3=Transaction(月度,yyyy-MM) 4=Summary 5=Deferred 6=FBAInboundConvenience。
    返回商品行级列式 CSV（product sales/tax/selling fees/fba fees/other/total…）。"""
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = client.signed_post("/api/report/center/task/getPlugPageList.json", {
        "reportTypeList": [int(args.report_type)],
        "statusList": [1],
        "startTime": args.start,
        "endTime": args.end,
        "pageNo": "1",
        "pageSize": "50",
    })
    rows = extract_rows(rows) if isinstance(rows, dict) else rows
    n = 0
    for i, r in enumerate(rows):
        month = str(r.get("reportDayType", ""))
        if args.month and month != args.month:
            continue
        shop = r.get("shopName", "")
        urls = r.get("fileUrls")
        url = urls[0] if isinstance(urls, list) else json.loads(urls)[0]
        raw = urllib.request.urlopen(urllib.request.Request(url), timeout=120).read()
        try:
            zf = zipfile.ZipFile(io.BytesIO(raw))
            name = zf.namelist()[0]
            txt = zf.read(name).decode("utf-8-sig", errors="replace")
        except zipfile.BadZipFile:
            namem = (r.get("reportDayType") or "") + "_" + shop + ".csv"
            txt = raw.decode("utf-8-sig", errors="replace")
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in shop)
        (out / f"{safe}__{month}.csv").write_text(txt, encoding="utf-8")
        n += 1
        if (i + 1) % 10 == 0:
            time.sleep(2)
        print(f"  {n}. {shop} {month}")
    print(f"[fetch-custom] wrote {n} files → {out}")


def main():
    p = argparse.ArgumentParser(description="赛狐 Amazon 结算自动取回+比对原型")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("shops", help="列出店铺，用于建 渠道账号 映射")
    f = sub.add_parser("fetch", help="拉取结算汇总+明细到目录")
    f.add_argument("--start", required=True)
    f.add_argument("--end", required=True)
    f.add_argument("--shop", default="", help="店铺ID, 逗号分隔")
    f.add_argument("--currency", default="")
    f.add_argument("--marketplace", default="")
    f.add_argument("--month", default="", help="账期月 YYYYMM（默认取 start 月份），用于按结算结束日归属")
    f.add_argument("--out", required=True)
    c = sub.add_parser("candidates", help="打印未识别科目候选")
    c.add_argument("--detail", required=True)
    fc = sub.add_parser("fetch-custom", help="拉取紫鸟/赛狐插件抓的列式报表(3=Transaction,4=Summary)")
    fc.add_argument("--start", required=True)
    fc.add_argument("--end", required=True)
    fc.add_argument("--month", default="", help="只留某月 yyyy-MM")
    fc.add_argument("--report-type", default="3", help="3=Transaction 4=Summary 5=Deferred 6=FBAInbound")
    fc.add_argument("--out", required=True)
    r = sub.add_parser("reconcile", help="比对赛狐 vs 钉钉")
    r.add_argument("--settlement", required=True, help="fetch 输出目录")
    r.add_argument("--dingtalk", required=True, help="钉钉定稿 xlsx")
    r.add_argument("--month", default="", help="账期月，如 202606")
    r.add_argument("--out", required=True)
    args = p.parse_args()

    if args.cmd == "candidates":
        cmd_candidates(args)
        return
    if args.cmd == "fetch-custom":
        client = get_client()
        cmd_fetch_custom(client, args)
        return
    if args.cmd in ("shops", "fetch", "reconcile"):
        client = get_client()
    else:
        p.print_help()
        return
    if args.cmd == "shops":
        cmd_shops(client)
    elif args.cmd == "fetch":
        cmd_fetch(client, args)
    elif args.cmd == "reconcile":
        cmd_reconcile(args)


if __name__ == "__main__":
    main()
