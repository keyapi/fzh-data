# -*- coding: utf-8 -*-
"""赛狐结算中心 Amazon 结算组 vs 钉钉附件次数。"""
from __future__ import annotations

import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import pandas as pd

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from paths import OA_REPORTS
from SELLFOX_API.client import SellfoxClient, SellfoxConfig  # noqa: E402
from audit_vs_drm import load_manifest  # noqa: E402
from parse import keep_approval, keep_attachment, parse_amz_channel  # noqa: E402
from person_folders import nas_person_folder  # noqa: E402

OUT = OA_REPORTS


def ding_amz_counts() -> pd.DataFrame:
    recs = load_manifest()
    rows = []
    for rec in recs:
        if not keep_approval(rec.get("status") or "", rec.get("result") or ""):
            continue
        if "亚马逊" not in (rec.get("platforms") or []):
            continue
        person = nas_person_folder(rec.get("originator") or "")
        for att in rec.get("attachments") or []:
            if not keep_attachment(att):
                continue
            name = att.get("fileName") or ""
            amz = parse_amz_channel(name)
            months = rec.get("period_months") or []
            if str(name).lower().endswith(".zip"):
                continue
            pm = months[0] if len(months) == 1 else (amz or {}).get("period_month")
            if pm not in {"2026-07", "2026-08"}:
                continue
            rows.append(
                {
                    "人": person,
                    "渠道": (amz or {}).get("channel") or name,
                    "账期月": pm,
                    "附件": name,
                    "审批编号": rec.get("businessId"),
                }
            )
    return pd.DataFrame(rows)


MKT_TO_SITE = {
    "美国": "US",
    "英国": "UK",
    "德国": "DE",
    "法国": "FR",
    "意大利": "IT",
    "西班牙": "ES",
    "加拿大": "CA",
    "墨西哥": "MX",
    "比利时": "BE",
    "荷兰": "NL",
    "瑞典": "SE",
    "波兰": "PL",
    "澳大利亚": "AU",
    "日本": "JP",
    "印度": "IN",
    "爱尔兰": "IE",
    "奥地利": "AT",
}

BRAND_ALIASES = [
    (("JOHNEAR", "JOHNA"), "JOHNEAR"),
    (("BAINA", "BNCKTRD", "BNCK"), "BAINA"),
    (("WOWMAX", "CENTRADE", "CTRD"), "CTRD"),
    (("VERCART", "VER"), "VER"),
    (("RUYANG", "BJRYECLTD", "BJRY"), "RUYANG"),
    (("STRUSERY",), "STRUSERY"),
    (("LELEFIDO", "DANEEY"), "DANEEY"),
    (("TOODDLY",), "TOODDLY"),
    (("ROSOON", "RUCENER", "RUSEN"), "ROSOON"),
    (("NOVELLEDO", "YUNTU", "YTHD"), "YTHD"),
    (("JALNODD", "XJIN"), "JALNODD"),
    (("XALVIOR", "FZHSX"), "XALVIOR"),
    (("SNOW",), "SNOW"),
]


def norm_brand(text: str) -> str:
    u = re.sub(r"[^A-Z0-9]", "", (text or "").upper())
    for aliases, key in BRAND_ALIASES:
        for a in aliases:
            if a in u:
                # VER 太短，避免匹配 VERCART 以外的 VER 误伤：要求紧邻或全词
                if a == "VER" and "VERCART" not in u and not u.endswith("VER") and "VER" + "" not in u:
                    if not re.search(r"VER(?:US|UK|DE|FR|IT|ES|CA|BE|NL|SE)?$", u):
                        continue
                return key
    return ""


def shop_brand_site(shop_name: str, marketplace: str) -> tuple[str, str]:
    site = MKT_TO_SITE.get(str(marketplace or "").strip(), "")
    n = shop_name or ""
    m = re.search(r"-(US|UK|DE|FR|IT|ES|CA|MX|BE|NL|SE|PL|AU|JP|IN|IE|AT)$", n, re.I)
    if m and not site:
        site = m.group(1).upper()
    brand = norm_brand(n)
    return brand, site


def ding_brand_site(channel: str, filename: str) -> tuple[str, str]:
    amz = parse_amz_channel(filename) or parse_amz_channel("AMZ" + (channel or ""))
    if amz:
        return norm_brand(amz.get("brand") or "") or norm_brand(amz.get("channel") or ""), (amz.get("site") or "").upper()
    return norm_brand(channel) or norm_brand(filename), ""


def compare_ding_sellfox(gdf: pd.DataFrame, ddf: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    sf = defaultdict(int)
    sf_name = {}
    for _, r in gdf.iterrows():
        b, s = shop_brand_site(str(r.get("shopName") or ""), str(r.get("marketplace") or ""))
        if not b or not s:
            continue
        k = (b, s, str(r.get("账期月") or ""))
        sf[k] += 1
        sf_name[k] = f"{r.get('shopName')} {r.get('marketplace')}"
    ding = defaultdict(lambda: {"n": 0, "人": set(), "文件": []})
    for _, r in ddf.iterrows():
        b, s = ding_brand_site(str(r.get("渠道") or ""), str(r.get("附件") or ""))
        if not b or not s:
            b2, s2 = ding_brand_site("", str(r.get("附件") or ""))
            b, s = b or b2, s or s2
        if not b:
            continue
        k = (b, s, str(r.get("账期月") or ""))
        ding[k]["n"] += 1
        ding[k]["人"].add(str(r.get("人") or ""))
        ding[k]["文件"].append(str(r.get("附件") or ""))
    keys = sorted(set(sf) | set(ding))
    rows = []
    for k in keys:
        b, s, ym = k
        sn, dn = sf.get(k, 0), ding[k]["n"] if k in ding else 0
        if sn == 0 and dn == 0:
            continue
        if sn > dn:
            verd = "赛狐多_钉钉漏交或未匹配到附件"
        elif sn == dn:
            verd = "次数一致" if sn >= 2 else ("两边都是1次_平台可能本来就少" if sn == 1 else "两边都是0")
        else:
            verd = "钉钉多于赛狐_核对重复交或文件名拆店"
        if sn <= 1 and dn <= 1 and sn == dn:
            verd = "两边都是1次_平台可能本来就少" if sn == 1 else verd
        rows.append(
            {
                "brand": b,
                "site": s,
                "账期月": ym,
                "赛狐店": sf_name.get(k, ""),
                "赛狐结算组": sn,
                "钉钉附件": dn,
                "人": "、".join(sorted(ding[k]["人"])) if k in ding else "",
                "结论": verd,
                "钉钉文件": "; ".join(ding[k]["文件"][:6]) if k in ding else "",
            }
        )
    cdf = pd.DataFrame(rows)
    focus_brands = {"BAINA", "CTRD", "VER", "RUYANG", "STRUSERY", "JOHNEAR"}
    lines = []
    if cdf.empty:
        return cdf, ["(无对照行)"]
    sub = cdf[cdf["brand"].isin(focus_brands)]
    leak = cdf[cdf["结论"].str.contains("漏交")]
    one = cdf[cdf["结论"].str.contains("本来就少")]
    lines.append(f"- 对照行 {len(cdf)}；赛狐多于钉钉 {len(leak)}；两边都是 1 次 {len(one)}")
    lines.append("\n### JHP / BAINA·CTRD·VER")
    for _, r in cdf[cdf["brand"].isin({"BAINA", "CTRD", "VER"})].sort_values(["brand", "site", "账期月"]).iterrows():
        lines.append(
            f"- {r['人'] or 'JHP?'} {r['brand']}-{r['site']} {r['账期月']}: 赛狐{r['赛狐结算组']} 钉钉{r['钉钉附件']} | {r['结论']} | {r['赛狐店']}"
        )
    lines.append("\n### LXJ RUYANG / LTZ STRUSERY / CLB JOHNEAR")
    for _, r in cdf[cdf["brand"].isin({"RUYANG", "STRUSERY", "JOHNEAR"})].sort_values(["人", "brand", "site", "账期月"]).iterrows():
        lines.append(
            f"- {r['人'] or '?'} {r['brand']}-{r['site']} {r['账期月']}: 赛狐{r['赛狐结算组']} 钉钉{r['钉钉附件']} | {r['结论']}"
        )
    lines.append("\n### 其余赛狐多、钉钉少（优先催补交）")
    for _, r in leak.sort_values(["账期月", "brand", "site"]).iterrows():
        if r["brand"] in focus_brands:
            continue
        lines.append(f"- {r['人'] or r['赛狐店']} {r['brand']}-{r['site']} {r['账期月']}: 赛狐{r['赛狐结算组']} 钉钉{r['钉钉附件']}")
    return cdf, lines


def fetch_groups(client: SellfoxClient, start: str, end: str) -> list[dict]:
    page = 1
    out = []
    while True:
        data = client.signed_post(
            "/api/financial/v2/settlementSummary/groupPage.json",
            {
                "timeType": "settlementEndTime",
                "startTime": start,
                "endTime": end,
                "pageNo": str(page),
                "pageSize": "200",
                "isSite": True,
            },
        )
        rows = (data or {}).get("groupVoList") or (data or {}).get("rows") or []
        if isinstance(data, list):
            rows = data
        out.extend(rows)
        total = int((data or {}).get("totalPage") or 1) if isinstance(data, dict) else 1
        print(f"settlement page {page}/{total} n={len(rows)}")
        if page >= total or not rows:
            break
        page += 1
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    cfg = SellfoxConfig.from_env()
    client = SellfoxClient(cfg)
    shops = client.list_shops()
    shop_map = {str(s.get("id")): s for s in shops}
    print("shops", len(shops), "mode", cfg.mode)

    groups = []
    for start, end in (("2026-07-01", "2026-07-31"), ("2026-08-01", "2026-08-31")):
        groups.extend(fetch_groups(client, start, end))

    g_rows = []
    for g in groups:
        sid = str(g.get("shopId") or "")
        shop = shop_map.get(sid) or {}
        end_raw = str(g.get("groupEndStr") or g.get("siteGroupEndStr") or g.get("utcFundTransferDateStr") or "")
        end = end_raw.replace("/", "-")[:10]
        ym = end[:7] if len(end) >= 7 else ""
        g_rows.append(
            {
                "shopId": sid,
                "shopName": shop.get("name") or g.get("shopName") or "",
                "marketplace": g.get("marketplaceName") or g.get("marketplaceId") or "",
                "sellerId": g.get("sellerId") or "",
                "settlementId": g.get("settlementId") or g.get("groupId") or "",
                "groupStart": g.get("groupStartStr") or g.get("siteGroupStartStr") or "",
                "groupEnd": g.get("groupEndStr") or g.get("siteGroupEndStr") or "",
                "transferAmount": g.get("transferAmount"),
                "fundTransferStatus": g.get("fundTransferStatusStr") or g.get("fundTransferStatus") or "",
                "账期月": ym,
            }
        )
    gdf = pd.DataFrame(g_rows)
    ddf = ding_amz_counts()

    OUT.mkdir(parents=True, exist_ok=True)
    gdf.to_excel(OUT / "赛狐Amazon结算组_7-8月.xlsx", index=False)
    ddf.to_excel(OUT / "钉钉Amazon附件_7-8月.xlsx", index=False)

    # 店铺名模糊对照：赛狐 shopName vs 钉钉渠道
    ding_by_m = defaultdict(int)
    for _, r in ddf.iterrows():
        ding_by_m[(r["账期月"], str(r["渠道"]).upper())] += 1
    sf_by_m = defaultdict(int)
    for _, r in gdf.iterrows():
        key = f"{r['shopName']}|{r['marketplace']}"
        sf_by_m[(r["账期月"], key)] += 1

    lines = [
        f"赛狐结算组 {len(gdf)} 条，钉钉Amazon附件 {len(ddf)} 条（不含 zip）",
        f"赛狐店铺 {len(shops)}",
        "",
        "## 赛狐按店铺×月结算组次数（0/1 重点看小店）",
    ]
    if not gdf.empty:
        ct = gdf.groupby(["shopName", "marketplace", "账期月"]).size().reset_index(name="n")
        ct.to_excel(OUT / "赛狐Amazon结算组_店铺月次数.xlsx", index=False)
        for _, r in ct.sort_values(["shopName", "账期月"]).iterrows():
            flag = "  <<仅1次" if r["n"] == 1 else ("  <<0?" if r["n"] == 0 else "")
            lines.append(f"- {r['shopName']} {r['marketplace']} {r['账期月']}: {r['n']}{flag}")

    cmp_df, focus_lines = compare_ding_sellfox(gdf, ddf)
    cmp_df.to_excel(OUT / "赛狐vs钉钉Amazon_店铺对照.xlsx", index=False)
    lines.extend(["", "## 赛狐有结算组 vs 钉钉已交附件（漏交 / 平台确实少）"])
    lines.extend(focus_lines)
    (OUT / "赛狐vs钉钉Amazon结算.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(focus_lines[:120]))
    print("wrote", OUT / "赛狐vs钉钉Amazon结算.md")


if __name__ == "__main__":
    main()
