"""Rebuild sellfox-native lizard fixtures from Tongtu P0 sample mapping.

Output (gitignored, may contain PII):
  sellfox_shipping/数据源/蜥蜴国际-p0-样例/sellfox-native-fixture/

Requires: SELLFOX_PROXY_API_KEY, EN_API/.env ERP keys, local shipping.db helpful.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

import httpx
import pandas as pd
import yaml

from sellfox_shipping.carriers.lizard.cascade import CascadingDimsLookup
from sellfox_shipping.carriers.lizard.commodity_dims import CommodityPageListDimsLookup
from sellfox_shipping.carriers.lizard.erpnext_dims import ErpnextZlmbDimsLookup
from sellfox_shipping.carriers.lizard.spreadsheet import (
    COL_REF,
    build_upload_dataframe,
    parse_tracking_return,
    write_upload_xlsx,
)
from sellfox_shipping.env_loader import load_dotenv
from sellfox_shipping.package_models import (
    SellfoxPackageAddress,
    SellfoxPackageItemRecord,
    SellfoxPackageLogistics,
    SellfoxPackageRecord,
)
from sellfox_shipping.sellfox_client import parse_sellfox_package

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "数据源" / "蜥蜴国际-p0-样例"
OUT = SAMPLE / "sellfox-native-fixture"
# Corrected Amazon IDs (P81401195 ends with 2, not 3 — verified via ERPNext Tongtool Package)
P_TO_AMZ = {
    "P81401351": "114-0404540-1361802",
    "P81401345": "113-2240947-8487449",
    "P81401339": "112-5214965-9609849",
    "P81401324": "112-4478636-4801002",
    "P81401316": "113-3243223-2085067",
    "P81401302": "114-4788045-9626627",
    "P81401293": "114-0618319-8381856",
    "P81401285": "111-4541067-4593864",
    "P81401273": "111-8700000-5742624",
    "P81401265": "112-1491871-0683429",
    "P81401256": "111-0778719-4466639",
    "P81401244": "112-4846537-8933861",
    "P81401231": "111-9012908-3205800",
    "P81401229": "114-1501501-0903440",
    "P81401217": "111-4617012-2727417",
    "P81401203": "111-4106795-3792213",
    "P81401195": "114-8410891-0563432",
    "P81401186": "113-5579900-4694666",
    "P81401178": "111-2052943-3117040",
    "P81401163": "113-6082325-4473804",
    "P81401159": "113-3935937-8465811",
    "P81401143": "111-5279062-0123433",
    "P81401135": "111-1897745-9980208",
    "P81401123": "112-0132729-7795467",
    "P81401115": "112-6270546-2549068",
    "P81401100": "111-7928535-0683454",
    "P81401096": "114-0749438-7309014",
    "P81401084": "114-4250126-3204201",
    "P81401077": "112-9002157-2911462",
    "P81401066": "112-5101032-2108252",
    "P81401055": "113-6071874-4833045",
    "P81401049": "111-8509342-5979413",
    "P81401034": "111-3397987-1202619",
    "P81401026": "111-6905168-2558662",
    "P81401013": "114-4553684-5959467",
    "P81401002": "112-3656518-6505849",
    "P81400996": "114-1501793-9020258",
    "P81400983": "113-4902279-1572229",
}


def main() -> None:
    load_dotenv(ROOT.parents[0] / "EN_API" / ".env")
    load_dotenv()
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    base = cfg["sellfox"]["proxy_base_url"].rstrip("/")
    acct = cfg["sellfox"]["proxy_account"]
    key = os.getenv("SELLFOX_PROXY_API_KEY", "")
    headers = {"Authorization": f"Bearer {key}"}
    client = httpx.Client(timeout=60)

    amz_to_sn: dict[str, str] = {}
    con = sqlite3.connect(ROOT / "data" / "shipping.db")
    for amz in set(P_TO_AMZ.values()):
        row = con.execute(
            """
            SELECT sp.package_sn FROM shipping_package_orders spo
            JOIN shipping_packages sp ON sp.id=spo.package_id
            JOIN shipping_orders so ON so.id=spo.order_id
            WHERE so.external_order_id=?
            """,
            (amz,),
        ).fetchone()
        if row:
            amz_to_sn[amz] = row[0]

    needed = set(P_TO_AMZ.values()) - set(amz_to_sn)
    page = 1
    while needed and page <= 30:
        time.sleep(1.2)
        resp = client.post(
            f"{base}/v1/{acct}/api/packageShip/v1/getPackagePage.json",
            headers=headers,
            json={
                "purchaseDateStart": "2026-07-14",
                "purchaseDateEnd": "2026-07-16",
                "pageNo": page,
                "pageSize": 50,
            },
        )
        if resp.status_code == 429:
            time.sleep(8)
            continue
        data = resp.json()
        rows = (data.get("data") or {}).get("rows") or []
        total = (data.get("data") or {}).get("totalSize") or 0
        for row in rows:
            sn = row.get("packageSn")
            aids = {
                o.get("amazonOrderId")
                for o in (row.get("orders") or [])
                if o.get("amazonOrderId")
            } | {
                it.get("amazonOrderId")
                for it in (row.get("items") or [])
                if it.get("amazonOrderId")
            }
            for aid in aids:
                if aid in needed and sn:
                    amz_to_sn[aid] = sn
                    needed.discard(aid)
        if not rows or page * 50 >= total:
            break
        page += 1

    p_to_sn = {p: amz_to_sn[a] for p, a in P_TO_AMZ.items() if a in amz_to_sn}
    if len(p_to_sn) != 38:
        raise SystemExit(f"mapped {len(p_to_sn)}/38 — missing amazon: {sorted(needed)}")

    # cache raw package rows for sns not in local db
    need_sn = set(p_to_sn.values())
    con.row_factory = sqlite3.Row
    local_sns = {
        r[0]
        for r in con.execute(
            "SELECT package_sn FROM shipping_packages WHERE package_sn IN ({})".format(
                ",".join("?" * len(need_sn))
            ),
            tuple(need_sn),
        )
    }
    api_rows: dict[str, dict] = {}
    missing_local = need_sn - local_sns
    page = 1
    while missing_local and page <= 30:
        time.sleep(1.2)
        resp = client.post(
            f"{base}/v1/{acct}/api/packageShip/v1/getPackagePage.json",
            headers=headers,
            json={
                "purchaseDateStart": "2026-07-14",
                "purchaseDateEnd": "2026-07-16",
                "pageNo": page,
                "pageSize": 50,
            },
        )
        if resp.status_code == 429:
            time.sleep(8)
            continue
        rows = (resp.json().get("data") or {}).get("rows") or []
        total = (resp.json().get("data") or {}).get("totalSize") or 0
        for row in rows:
            sn = row.get("packageSn")
            if sn in missing_local:
                api_rows[sn] = row
                missing_local.discard(sn)
        if not rows or page * 50 >= total:
            break
        page += 1

    packages: list[SellfoxPackageRecord] = []
    for _p, sn in sorted(p_to_sn.items()):
        pkg = con.execute(
            "SELECT * FROM shipping_packages WHERE package_sn=?", (sn,)
        ).fetchone()
        if pkg:
            its = con.execute(
                "SELECT * FROM shipping_package_items WHERE package_id=?",
                (pkg["id"],),
            ).fetchall()
            packages.append(
                SellfoxPackageRecord(
                    account_key="sellfox-main",
                    package_sn=sn,
                    address=SellfoxPackageAddress(
                        name=pkg["address_name"] or "",
                        address_line_1=pkg["address_line_1"] or "",
                        address_line_2=pkg["address_line_2"] or "",
                        city=pkg["address_city"] or "",
                        state_or_region=pkg["address_state_or_region"] or "",
                        postal_code=pkg["address_postal_code"] or "",
                        country=pkg["address_country"] or "",
                        country_code=pkg["address_country_code"] or "",
                        phone=pkg["address_phone"] or "",
                        mobile=pkg["address_mobile"] or "",
                    ),
                    logistics=SellfoxPackageLogistics(
                        warehouse_name=pkg["warehouse_name"] or "",
                        channel_name=pkg["channel_name"] or "",
                    ),
                    items=[
                        SellfoxPackageItemRecord(
                            external_order_id=it["external_order_id"] or "",
                            order_item_id=it["order_item_id"] or "",
                            seller_sku=it["seller_sku"] or "",
                            commodity_sku=it["commodity_sku"] or "",
                            quantity=it["quantity"] or 1,
                            variation=it["variation"] or "",
                        )
                        for it in its
                    ],
                )
            )
        else:
            packages.append(parse_sellfox_package("sellfox-main", api_rows[sn]))

    dims = CascadingDimsLookup(
        CommodityPageListDimsLookup(
            proxy_base_url=base, proxy_account=acct, proxy_api_key=key
        ),
        ErpnextZlmbDimsLookup(
            base_url=(os.getenv("ERP_URL") or "https://erpnext.vilavi.cn").rstrip("/"),
            api_key=(os.getenv("PROD_ERP_API_KEY") or os.getenv("ERP_API_KEY") or "").strip(),
            api_secret=(
                os.getenv("PROD_ERP_API_SECRET") or os.getenv("ERP_API_SECRET") or ""
            ).strip(),
        ),
    )
    dims.prefetch(
        [it.commodity_sku for p in packages for it in p.items if it.commodity_sku]
    )
    built = build_upload_dataframe(packages, dims_lookup=dims)

    OUT.mkdir(parents=True, exist_ok=True)
    write_upload_xlsx(built.dataframe, OUT / "02-sellfox-lizard-upload.xlsx")

    ret_src = next(SAMPLE.glob("03-lizard-tracking*"))
    df = pd.read_excel(ret_src)
    for i, row in df.iterrows():
        old = str(row.get(COL_REF) or "").strip()
        if old in p_to_sn:
            df.at[i, COL_REF] = p_to_sn[old]
    fixture = df[df[COL_REF].isin(set(p_to_sn.values()))].copy()
    fixture.to_excel(OUT / "03-sellfox-lizard-tracking-return.xlsx", index=False)
    df.to_excel(OUT / "03-sellfox-lizard-tracking-return-full-remap.xlsx", index=False)

    pd.DataFrame(
        [
            {
                "tongtu_ref": p,
                "amazon_order_id": P_TO_AMZ[p],
                "sellfox_package_sn": sn,
            }
            for p, sn in sorted(p_to_sn.items())
        ]
    ).to_csv(OUT / "00-tongtu-to-sellfox-package-map.csv", index=False)

    parsed = parse_tracking_return(
        OUT / "03-sellfox-lizard-tracking-return.xlsx",
        known_package_sns=set(built.dataframe["参考编号/Reference Code"]),
    )
    report = {
        "upload_rows": built.exported,
        "upload_skipped": built.skipped,
        "return_rows": len(fixture),
        "import_matched": parsed.matched,
        "import_unmatched": parsed.unmatched,
    }
    (OUT / "REPORT.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "README.md").write_text(
        "\n".join(
            [
                "# sellfox-native-fixture（本地，含 PII，不入 Git）",
                "",
                "由 `sellfox_shipping/scripts/rebuild_sellfox_lizard_fixtures.py` 生成。",
                "",
                "- `02-sellfox-lizard-upload.xlsx`：参考编号=赛狐 packageSn，重尺=pageList+ERPNext",
                "- `03-sellfox-lizard-tracking-return.xlsx`：原 03 中 38 行，参考编号换成 packageSn，物流单号保留",
                "- `00-tongtu-to-sellfox-package-map.csv`：通途 P# → Amazon → packageSn",
                "",
                "测试：`lizard-import-tracking` 对 03；勿对这批调用 submitToPlatform（历史已发货）。",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
