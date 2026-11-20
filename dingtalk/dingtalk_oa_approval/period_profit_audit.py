# -*- coding: utf-8 -*-
"""DingTalk export vs Sellfox vs NAS txt for a 账期月 (YYYY-MM)."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import pandas as pd

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "dingtalk" / "dingtalk_oa_approval"))

from paths import OA_DATA, OA_REPORTS, OA_WORK, local_nas_period  # noqa: E402

from SELLFOX_API.client import SellfoxClient, SellfoxConfig  # noqa: E402
from ding_xlsx import enrich, id_text, read_dingtalk_xlsx, unique_key  # noqa: E402
from nas_upload_api21 import stem_key  # noqa: E402
from parse import keep_approval, parse_amz_channel, period_month_bucket, ym  # noqa: E402
from channel_canonical import canonical_account  # noqa: E402
from sellfox_amz_settlements import ding_brand_site, fetch_groups, norm_brand, shop_brand_site  # noqa: E402

EXPORT = OA_WORK / "Amazon&新平台成本 20260801-20261013 销售收款确认单-20261014151249.xlsx"
PROBE = OA_REPORTS / "probe_ding_202608_v2.jsonl"
NAS_ROOT = local_nas_period()
COMMENT_API_DIR = OA_DATA / "files" / "_comment_api"
AFLOW_DIR = OA_DATA / "aflow_attachments"
REPORT_DIR = OA_REPORTS


def keep_row(status, result) -> bool:
    st = "" if status is None or (isinstance(status, float) and pd.isna(status)) else str(status)
    res = "" if result is None or (isinstance(result, float) and pd.isna(result)) else str(result)
    return keep_approval(st, res)


def month_range(period: str) -> tuple[str, str]:
    import calendar

    y, m = int(period[:4]), int(period[5:7])
    start = f"{y:04d}-{m:02d}-01"
    last = calendar.monthrange(y, m)[1]
    end = f"{y:04d}-{m:02d}-{last:02d}"
    return start, end


def correct_name(name: str) -> str:
    n = re.sub(r"\s+", "", name or "")
    n = re.sub(r"AMZCTRDU5", "AMZCTRDUS", n, flags=re.I)
    if re.search(r"US\d{1,2}[.\-]\d", n, re.I) and "-US-" not in n.upper():
        n = re.sub(r"(US)(\d)", r"US-\1", n, count=1, flags=re.I)
    return n


def to_float(v) -> float | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None


def load_probe_amz(period: str) -> pd.DataFrame:
    rows = []
    if not PROBE.is_file():
        return pd.DataFrame(rows)
    for line in PROBE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if not rec.get("keep"):
            continue
        for t in rec.get("tables") or []:
            if str(t.get("选择平台") or "").strip() != "亚马逊":
                continue
            pd_ = str(t.get("账期日期") or "")[:10]
            if ym(pd_) != period:
                continue
            rows.append(
                {
                    "审批编号": rec.get("businessId"),
                    "账期日期": pd_,
                    "销售账户": str(t.get("销售账户") or "").strip(),
                    "账期收款额": t.get("账期收款额"),
                    "销售额": t.get("销售额"),
                    "发起时间": rec.get("createTime"),
                }
            )
    return pd.DataFrame(rows)


def unique_key_from_probe(r) -> str:
    fake = pd.Series(
        {
            "审批编号": r.get("审批编号"),
            "账期日期": r.get("账期日期"),
            "销售账户_展开": r.get("销售账户"),
            "销售额": r.get("销售额"),
            "应收账款": r.get("账期收款额"),
        }
    )
    return unique_key(fake)


def file_settlement_date(name: str) -> pd.Timestamp | pd.NaT:
    amz = parse_amz_channel(name)
    if not amz:
        return pd.NaT
    stem = Path(name).stem
    m = re.search(r"(20\d{2})[-._]?(\d{1,2})[-._]?(\d{1,2})", stem)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return pd.Timestamp(y, mo, d)
    m = re.search(r"(\d{1,2})[.\-](\d{1,2})$", stem)
    if m:
        ym = str(amz.get("period_month") or "")
        if ym:
            y = int(ym[:4])
        else:
            y_m = re.search(r"(20\d{2})", stem)
            y = int(y_m.group(1)) if y_m else 2026
        return pd.Timestamp(y, int(m.group(1)), int(m.group(2)))
    return pd.NaT


def index_local_txt(nas_bucket: Path, period: str) -> dict[str, list[dict]]:
    by_stem: dict[str, list[dict]] = defaultdict(list)
    if nas_bucket.is_dir():
        for person in nas_bucket.iterdir():
            if not person.is_dir():
                continue
            for f in person.iterdir():
                if f.is_file() and f.suffix.lower() == ".txt":
                    sk = stem_key(correct_name(f.name))
                    by_stem[sk].append(
                        {"path": str(f), "name": f.name, "person": person.name, "bytes": f.stat().st_size}
                    )
    for extra in (COMMENT_API_DIR, AFLOW_DIR):
        if not extra.is_dir():
            continue
        for f in extra.rglob("*.txt"):
            amz = parse_amz_channel(f.name)
            if amz and (amz.get("period_month") or "") == period:
                sk = stem_key(correct_name(f.name))
                by_stem[sk].append({"path": str(f), "name": f.name, "person": "_cache", "bytes": f.stat().st_size})
    return by_stem


def match_file(row: pd.Series, by_stem: dict, period: str) -> list[dict]:
    acct = canonical_account(str(row.get("销售账户_展开") or row.get("销售账户") or "").strip())
    pd_ = pd.to_datetime(row.get("账期日期"), errors="coerce")
    if pd.isna(pd_) or not acct:
        return []
    want_ch = acct.upper()
    hits = []
    for items in by_stem.values():
        for item in items:
            amz = parse_amz_channel(item["name"])
            if not amz:
                continue
            ch = canonical_account(amz.get("channel") or "").upper() or (amz.get("channel") or "").upper()
            if want_ch != ch and want_ch not in ch and ch not in want_ch:
                b, s = ding_brand_site(acct, item["name"])
                b2, s2 = ding_brand_site(ch, item["name"])
                if not (b and s and f"{b}-{s}".upper() in ch):
                    continue
            fd = file_settlement_date(item["name"])
            if pd.isna(fd):
                continue
            if abs((fd - pd_).days) <= 7:
                hits.append(item)
    seen: set[str] = set()
    return [h for h in hits if h["path"] not in seen and not seen.add(h["path"])]  # type: ignore


def sellfox_paid(period: str) -> pd.DataFrame:
    start, end = month_range(period)
    prefix = period[:7]  # 2026-09
    client = SellfoxClient(SellfoxConfig.from_env())
    shops = {str(s.get("id")): s for s in client.list_shops()}
    groups = fetch_groups(client, start, end)
    rows = []
    for g in groups:
        end_raw = g.get("siteGroupEndStr") or g.get("groupEndStr") or ""
        end_d = re.sub(r"[/]", "-", str(end_raw))[:10]
        if not end_d.startswith(prefix):
            continue
        fund = str(g.get("fundTransferStatusStr") or "")
        amt = to_float(g.get("transferAmount"))
        paid = fund == "转账成功" and (amt is not None and amt > 0)
        shop_name = str(g.get("storeName") or "")
        if "TOODDLY" in shop_name.upper():
            brand, site = "TOODDLY", shop_brand_site(shop_name, str(g.get("marketplaceName") or ""))[1]
        else:
            brand, site = shop_brand_site(shop_name, str(g.get("marketplaceName") or ""))
        rows.append(
            {
                "shopName": shop_name,
                "brand": brand,
                "site": site,
                "groupEnd": end_d,
                "transferAmount": amt,
                "fundStatus": fund,
                "paid": paid,
            }
        )
    return pd.DataFrame(rows)


def match_sellfox(ding_row, sf: pd.DataFrame) -> dict | None:
    acct = str(ding_row.get("销售账户_展开") or "")
    pd_ = pd.to_datetime(ding_row.get("账期日期"), errors="coerce")
    amt = to_float(ding_row.get("账期收款额"))
    if pd.isna(pd_) or amt is None:
        return None
    b, s = ding_brand_site(acct, "")
    if not b:
        b = norm_brand(acct.replace("AMZ", ""))
    if not s and len(acct) >= 2 and acct.upper()[-2:].isalpha():
        tail = acct.upper()[-2:]
        if tail in {"US", "DE", "FR", "IT", "ES", "UK", "BE", "NL", "SE", "CA", "MX", "PL"}:
            s = tail
    cand = sf[sf["paid"] & (sf["brand"] == b) & (sf["site"] == s)].copy()
    if cand.empty:
        return None
    cand["groupEnd"] = cand["groupEnd"].astype(str).str.replace("/", "-", regex=False).str[:10]
    cand["diff"] = (pd.to_datetime(cand["groupEnd"]) - pd_).abs().dt.days
    cand = cand[cand["diff"] <= 7]
    if cand.empty:
        return None
    cand["amt_diff"] = (cand["transferAmount"] - amt).abs()
    best = cand.sort_values(["amt_diff", "diff"]).iloc[0]
    if best["amt_diff"] > 0.05:
        return {"match": "weak_amount", **best.to_dict()}
    return {"match": "ok", **best.to_dict()}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", required=True, help="YYYY-MM")
    ap.add_argument("--export", default="", help="钉钉宽窗导出 xlsx")
    ap.add_argument("--probe", default="", help="可选 API 探针 jsonl")
    args = ap.parse_args()
    period = args.period
    export_path = Path(args.export) if args.export else EXPORT
    if args.probe:
        global PROBE
        PROBE = Path(args.probe)
    bucket_name = period_month_bucket(period)
    nas_bucket = NAS_ROOT / bucket_name
    out = REPORT_DIR / f"{period.replace('-', '')}_profit_audit.json"

    raw = read_dingtalk_xlsx(export_path)
    en = enrich(raw)
    en["keep"] = en.apply(lambda r: keep_row(r.get("审批状态"), r.get("审批结果")), axis=1)
    all_period = en[en["账期月"] == period].copy()
    amz = all_period[(all_period["选择平台"] == "亚马逊") & all_period["keep"]].copy()

    dup = amz[amz["_key"].duplicated(keep=False)]

    missing_from_export = []
    probe = load_probe_amz(period)
    if not probe.empty:
        exp_keys = set(amz["_key"])
        for _, r in probe.iterrows():
            k = unique_key_from_probe(r)
            if k not in exp_keys:
                missing_from_export.append({**r.to_dict(), "_key": k})

    by_stem = index_local_txt(nas_bucket, period)
    stem_dupes = {
        k: v
        for k, v in by_stem.items()
        if sum(1 for x in v if str(nas_bucket.resolve()) in str(Path(x["path"]).resolve())) > 1
    }

    attach = []
    for _, r in amz.iterrows():
        hits = match_file(r, by_stem, period)
        attach.append(
            {
                "审批编号": id_text(r.get("审批编号")),
                "账期日期": str(r.get("账期日期"))[:10],
                "销售账户": r.get("销售账户_展开"),
                "账期收款额": r.get("账期收款额"),
                "nas_txt_n": len(hits),
                "nas_files": "; ".join(h["name"] for h in hits[:2]),
            }
        )
    attach_df = pd.DataFrame(attach)
    no_txt = attach_df[attach_df["nas_txt_n"] == 0]

    sf = sellfox_paid(period)
    paid_sf = sf[sf["paid"]] if not sf.empty and "paid" in sf.columns else sf.iloc[0:0]
    sf_ok = []
    unmatched = []
    weak = []
    for _, r in amz.iterrows():
        m = match_sellfox(r, sf)
        amt = to_float(r.get("账期收款额"))
        if m and m.get("match") == "ok":
            sf_ok.append(id_text(r["审批编号"]))
        elif m and m.get("match") == "weak_amount":
            weak.append({"审批编号": id_text(r["审批编号"]), "账户": r["销售账户_展开"], **m})
        elif amt is not None and amt > 0:
            unmatched.append(
                {
                    "审批编号": id_text(r["审批编号"]),
                    "账期日期": str(r["账期日期"])[:10],
                    "销售账户": r["销售账户_展开"],
                    "账期收款额": amt,
                }
            )

    matched_sf_keys = set()
    for _, r in amz.iterrows():
        m = match_sellfox(r, sf)
        if m and m.get("match") == "ok":
            matched_sf_keys.add((m["brand"], m["site"], m["groupEnd"], m["transferAmount"]))
    orphan_sf = []
    for _, g in paid_sf.iterrows():
        key = (g["brand"], g["site"], g["groupEnd"], g["transferAmount"])
        if key not in matched_sf_keys:
            orphan_sf.append(g.to_dict())

    nas_txt_only = sum(
        1
        for items in by_stem.values()
        for it in items
        if str(nas_bucket.resolve()) in str(Path(it["path"]).resolve())
    )

    report = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "period": period,
        "export": str(export_path),
        "nas_bucket": str(nas_bucket),
        "nas_bucket_exists": nas_bucket.is_dir(),
        "counts": {
            "export_all_rows": len(raw),
            "export_period_all_platforms_kept": int(all_period["keep"].sum()),
            "export_amz_period_kept": len(amz),
            "duplicate_key_rows": len(dup),
            "api_probe_amz_period": len(probe),
            "api_not_in_export": len(missing_from_export),
            "nas_txt_stems": len(by_stem),
            "nas_txt_files_in_bucket": nas_txt_only,
            "nas_stem_collisions_in_bucket": len(stem_dupes),
            "ding_amz_no_nas_txt_match": len(no_txt),
            "sellfox_groups_in_month": len(sf),
            "sellfox_paid": len(paid_sf),
            "ding_amz_matched_sf_ok": len(sf_ok),
            "ding_positive_unmatched_sf": len(unmatched),
            "ding_weak_amount_match": len(weak),
            "sellfox_paid_unmatched": len(orphan_sf),
        },
        "missing_from_export_vs_probe": missing_from_export[:50],
        "duplicate_keys": dup[["_key", "审批编号", "账期日期", "销售账户_展开", "账期收款额"]].head(20).to_dict(orient="records"),
        "no_nas_txt": no_txt.to_dict(orient="records"),
        "ding_weak_amount": weak[:30],
        "ding_positive_unmatched_sellfox": unmatched[:40],
        "sellfox_paid_unmatched": orphan_sf[:40],
        "probe_note": "probe 缓存截止约 2026-10-13；若 api_not_in_export>0 或 export 发起窗已延长需重扫 API",
    }
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report["counts"], ensure_ascii=False, indent=2))
    print("wrote", out)


if __name__ == "__main__":
    main()
