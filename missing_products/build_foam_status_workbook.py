# -*- coding: utf-8 -*-
"""Read-only foam status workbook for the 25 in-stock foam Tongtu SKUs.

This script does not write EN, HM1510 or Sellfox. It records the current
situation: foam SKUs are registered to EN products, while HM1510 customer
codes are historical and all prefixed with 删除.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

HERE = Path(__file__).resolve().parent
MAIN = Path(r"D:\Work\赛狐\Cursor")
OUT = HERE / "out"
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from tongtu_data import latest_mainline_audit_path, latest_file, load_foam_status_sheet, norm


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for path in (MAIN / ".env", MAIN / "EN_API" / ".env"):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip("'\"")
    values.update({key: value for key, value in __import__("os").environ.items() if value})
    return values


def fetch_hm1510_item_count() -> Optional[int]:
    env = load_env()
    url = env.get("ERP_URL", "https://erpnext.vilavi.cn").rstrip("/")
    key = env.get("PROD_ERP_API_KEY") or env.get("ERP_API_KEY", "")
    secret = env.get("PROD_ERP_API_SECRET") or env.get("ERP_API_SECRET", "")
    if not key or not secret:
        return None
    import json as _json

    params = {
        "fields": _json.dumps(["name"]),
        "filters": _json.dumps([["name", "like", "HM1510%"]]),
        "limit_page_length": "0",
    }
    resp = requests.get(
        f"{url}/api/resource/Item",
        params=params,
        headers={"Authorization": f"token {key}:{secret}"},
        timeout=(30, 90),
    )
    resp.raise_for_status()
    data = resp.json().get("data") or []
    return len(data)


def load_hm1510_history() -> tuple[pd.DataFrame, Optional[Path]]:
    path = latest_file(OUT, "PK_HM1510客户物料号只读调查_*.json")
    if not path:
        return pd.DataFrame(), None
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("rows") or []
    df = pd.DataFrame(rows)
    return df, path


BUSINESS_NOTES = [
    ("结论", "本阶段不为 HM1510 设计登记标准，也不写 HM1510 客户物料号。"),
    ("25条海绵SKU", "25 条有库存完整 -Foam 通途 SKU 均已精确登记到至少一个 EN 产品成品变体，主线已完成。"),
    ("HM1510历史登记", "EN 的 HM1510 物料存在 75 条历史客户码记录，全部带“删除”前缀，当前活跃登记为 0。"),
    ("业务现状", "同事下单海绵时，销售订单 Excel 中上传的通途 SKU 使用“删除TTxxx-Foam”这类带删除前缀的编号。"),
    ("产品登记优先", "通途 SKU -> EN 产品成品的登记仍是销售订单导入的主链，PK#/HM1510 上的客户码不能替代产品登记。"),
    ("后续", "是否恢复/重新设计 HM1510 客户码维护方式，等映射表与库存校准方案评审后再决定。"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--audit-xlsx", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    audit_path = args.audit_xlsx or latest_mainline_audit_path()
    if not audit_path:
        print("未找到最新主线审计工作簿")
        return 1
    foam = load_foam_status_sheet(audit_path)
    history, history_path = load_hm1510_history()

    item_count: Optional[int] = None
    try:
        item_count = fetch_hm1510_item_count()
    except Exception as exc:  # noqa: BLE001
        print(f"EN API 获取 HM1510 数量失败: {exc}")

    active = 0
    total_history = 0
    if not history.empty:
        codes = history.get("ref_code", pd.Series(dtype=str)).astype(str)
        total_history = len(history)
        active = int((~codes.str.startswith("删除")).sum())

    summary = pd.DataFrame(
        [
            ("有库存海绵通途 SKU", len(foam)),
            ("已精确登记 EN 产品", int((foam["EN登记状态"].astype(str) == "已精确登记").sum())),
            ("HM1510 物料数", item_count if item_count is not None else "API 获取失败"),
            ("HM1510 历史客户码行数", total_history),
            ("HM1510 当前活跃登记", active),
            ("历史登记来源", history_path.name if history_path else "未找到"),
            ("审计底表时间", audit_path.stem),
            ("生成时间", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        ],
        columns=["指标", "值"],
    )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = args.out or (OUT / f"海绵通途SKU现状_{stamp}.xlsx")
    OUT.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="汇总", index=False)
        foam.to_excel(writer, sheet_name="25条海绵SKU现状", index=False)
        if not history.empty:
            history.to_excel(writer, sheet_name="HM1510历史登记参考", index=False)
        pd.DataFrame(BUSINESS_NOTES, columns=["项目", "说明"]).to_excel(
            writer, sheet_name="业务说明", index=False
        )

    print(f"已生成: {out_path}")
    print(
        f"海绵SKU={len(foam)} 已登记={int((foam['EN登记状态'].astype(str) == '已精确登记').sum())} "
        f"HM1510物料={item_count} 历史行={total_history} 活跃={active}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
