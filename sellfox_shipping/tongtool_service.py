"""通途订单标记服务：美东100.xls → EN(Tongtool Package) → 本地赛狐包裹匹配 → 持久化标记。

Web 上传与 CLI 共用本模块（用户要求两者一致——目的都只是读取文件 + 匹配标记）。

链路（已在 2026-08-11 实测 114/114 全部匹配）：
    参考编号 P81678873（通途包裹号）
      → ERPNext GET /api/resource/Tongtool Package/{P}
      → order_links[0].order_id = "CUS-112-9957834-2887428"（带渠道前缀）
      → 去前缀 split('-',1)[1] = "112-9957834-2887428"（Amazon 订单号）
      → 本地包裹 orders[].external_order_id 匹配 → 标记 is_tongtool
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests

from sellfox_shipping.env_loader import load_dotenv


@dataclass
class TongtoolMatchResult:
    total: int = 0
    matched: int = 0
    unmatched_count: int = 0
    matched_rows: list[dict] = field(default_factory=list)
    unmatched_rows: list[dict] = field(default_factory=list)
    skipped_duplicates: int = 0

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "matched": self.matched,
            "unmatched_count": self.unmatched_count,
            "skipped_duplicates": self.skipped_duplicates,
            "matched_rows": self.matched_rows,
            "unmatched_rows": self.unmatched_rows,
        }


def read_p_numbers_from_xls(path: str | Path) -> list[str]:
    """读取 xls/xlsx 的「参考编号/Reference Code」列，返回去重后的 P 号。"""
    import pandas as pd

    df = pd.read_excel(str(path), dtype=str)
    col = "参考编号/Reference Code"
    if col not in df.columns:
        # 兼容可能的英文列名
        for alt in ("Reference Code", "参考编号", "reference"):
            if alt in df.columns:
                col = alt
                break
        else:
            raise ValueError(
                f"xls 缺少列 {col}，实际列: {list(df.columns)}"
            )
    seen: list[str] = []
    for raw in df[col].tolist():
        val = str(raw or "").strip()
        if val and val not in seen:
            seen.append(val)
    return seen


def lookup_tongtool_order(p_number: str) -> tuple[str | None, str]:
    """ERPNext 查 Tongtool Package，返回 (带前缀订单号, 状态/原因)。"""
    load_dotenv(Path(__file__).resolve().parents[1] / "EN_API" / ".env")
    load_dotenv()
    key = (os.getenv("PROD_ERP_API_KEY") or os.getenv("ERP_API_KEY") or "").strip()
    sec = (
        os.getenv("PROD_ERP_API_SECRET") or os.getenv("ERP_API_SECRET") or ""
    ).strip()
    if not key or not sec:
        return None, "en_credentials_missing"
    base = (os.getenv("ERP_URL") or "https://erpnext.vilavi.cn").strip().rstrip("/")
    try:
        resp = requests.get(
            f"{base}/api/resource/Tongtool Package/{p_number}",
            headers={"Authorization": f"token {key}:{sec}"},
            timeout=30,
        )
    except requests.RequestException as exc:
        return None, f"en_network:{type(exc).__name__}"
    if resp.status_code != 200:
        return None, f"en_http_{resp.status_code}"
    data = resp.json().get("data") or {}
    links = data.get("order_links") or []
    if not links:
        return None, "no_order_links"
    order_id = str(links[0].get("order_id") or "").strip()
    if not order_id:
        return None, "empty_order_id"
    return order_id, "ok"


def order_id_to_amazon(order_id: str) -> str:
    """去掉渠道前缀，返回 Amazon 订单号。

    通途订单号形如 'CUS-112-9957834-2887428' / 'TOODDLYUS-114-0404540-1361802'，
    前缀是字母；Amazon 订单号形如 '112-9957834-2887428'（三段数字）。若本身已是
    Amazon 格式则原样返回。
    """
    s = (order_id or "").strip()
    import re

    if re.match(r"^\d+-\d+-\d+$", s):
        return s
    return s.split("-", 1)[1] if "-" in s else s


def _order_index(repo, account_key: str) -> dict[str, list[str]]:
    """构建 Amazon 订单号 -> package_sn 索引（复用仓库查询，避免 sqlite 内部依赖）。"""
    return repo.index_packages_by_external_order(account_key)


def _warehouse_from_filename(filename: str) -> str:
    """从通途上传文件名中提取发货仓库标识。

    半成品必须在成品之前检查，因为"半成品"包含"成品"二字。
    """
    name = (filename or "").strip()
    if not name:
        return ""
    if "皮壳" in name:
        return "FZH-DANEEY-皮壳仓库"
    if "退货" in name:
        return "FZH-DANEEY-退货产品仓"
    if "半成品" in name:
        return "FZH-DANEEY-半成品仓"
    if "成品" in name:
        return "FZH-DANEEY-成品仓"
    return ""


def _shipping_method_from_filename(filename: str) -> str:
    """从通途上传文件名中提取发货方式/承运商。

    后续可扩展：尾程七条、vite、usps 等。
    """
    name = (filename or "").strip()
    if not name:
        return ""
    if "蜴国际" in name:
        return "蜴国际"
    # 后续扩展点：尾程七条、vite、usps
    return ""


def match_and_mark(
    repo,
    *,
    account_key: str,
    xls_path: str | Path,
    actor: str = "cli",
    en_interval_s: float = 0.0,
    max_workers: int = 4,
    shipping_warehouse: str = "",
) -> TongtoolMatchResult:
    """读 xls → EN 查通途订单 → 匹配本地包裹 → 持久化 is_tongtool 标记。

    EN 查询用 ThreadPoolExecutor 并行（114 个 P 号串行需 60s+，Web 请求会超时）；
    EN 端无间隔限制时 ``en_interval_s=0`` 最快，如需稳妥可调到 0.1。
    """
    from concurrent.futures import ThreadPoolExecutor

    p_numbers = read_p_numbers_from_xls(xls_path)
    result = TongtoolMatchResult(total=len(p_numbers))
    index = _order_index(repo, account_key)
    marked_sns: set[str] = set()
    wh = shipping_warehouse or _warehouse_from_filename(str(xls_path))
    sm = _shipping_method_from_filename(str(xls_path))

    def _lookup(p: str):
        order_id, status = lookup_tongtool_order(p)
        if en_interval_s > 0:
            time.sleep(en_interval_s)
        return p, order_id, status

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        lookup_results = list(pool.map(_lookup, p_numbers))

    for p, order_id, status in lookup_results:
        if not order_id:
            result.unmatched_count += 1
            result.unmatched_rows.append(
                {"p_number": p, "reason": status, "detail": ""}
            )
            continue
        amazon = order_id_to_amazon(order_id)
        pkgs = index.get(amazon, [])
        if not pkgs:
            result.unmatched_count += 1
            result.unmatched_rows.append(
                {
                    "p_number": p,
                    "reason": "no_local_package",
                    "detail": f"{order_id} -> {amazon}",
                }
            )
            continue
        result.matched += 1
        # 一个 P 号可能对应多个包裹（极少），通常 1 个
        for pkg_sn in pkgs:
            result.matched_rows.append(
                {
                    "p_number": p,
                    "order_id": order_id,
                    "amazon_order_id": amazon,
                    "package_sn": pkg_sn,
                }
            )
            if pkg_sn not in marked_sns:
                repo.mark_tongtool(
                    account_key=account_key,
                    package_sn=pkg_sn,
                    p_numbers=[p],
                    shipping_warehouse=wh,
                    shipping_method=sm,
                )
                marked_sns.add(pkg_sn)

    return result
