"""从通途列 + 跟踪号形态判断承运商。列优先于正则。"""

from __future__ import annotations

import re
from dataclasses import dataclass

UPS_HINTS = ("ups", "联合包裹")
FEDEX_HINTS = ("fedex", "联邦")
GLS_HINTS = ("gls",)
GOFO_HINTS = ("gofo",)
TIKTOK_HINTS = ("tiktok", "tiktok物流")
USPS_HINTS = ("usps",)


@dataclass
class RouteResult:
    carrier: str | None
    reason: str = ""


def _norm_number(s: str) -> str:
    s = (s or "").replace(" ", "").replace("\t", "").strip().upper()
    for ch in ("-", "_", "'"):
        s = s.replace(ch, "")
    return s


def split_tracking_cell(raw: str) -> list[str]:
    """一格多号（逗号/分号/空白/竖线）拆开；空单元格返回 []。"""
    if not raw or str(raw).strip().lower() in ("", "nan"):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for tok in re.split(r"[,，;；|/]+|\s+", str(raw).strip()):
        n = _norm_number(tok)
        if not n or n in seen:
            continue
        seen.add(n)
        out.append(n)
    return out


def _hay(ident: dict) -> str:
    parts = [ident.get("邮寄方式") or "", ident.get("渠道") or ""]
    return " ".join(parts).lower()


def _looks_gls_number(n: str) -> bool:
    """GLS 波兰号多为 8–12 位数字；排除 UPS 1Z、allegro …U、过短碎片。"""
    if n.startswith("1Z"):
        return False
    if n.endswith("U") and not n.isdigit():
        return False
    digits = re.sub(r"\D", "", n)
    return 8 <= len(digits) <= 14 and digits == n


def detect_carrier(number: str, ident: dict | None = None) -> RouteResult:
    ident = ident or {}
    n = _norm_number(number)
    if not n:
        return RouteResult(None, "missing_tracking")
    text = _hay(ident)
    if any(h in text for h in UPS_HINTS):
        return RouteResult("ups")
    if any(h in text for h in FEDEX_HINTS):
        return RouteResult("fedex")
    if any(h in text for h in GLS_HINTS):
        if n.startswith("1Z"):
            return RouteResult("ups")
        if not _looks_gls_number(n):
            return RouteResult(None, "not_gls_number")
        return RouteResult("gls")
    if any(h in text for h in GOFO_HINTS) or n.startswith("GFUS"):
        return RouteResult(None, "unsupported:gofo")
    if any(h in text for h in TIKTOK_HINTS):
        return RouteResult(None, "unsupported:tiktok")
    if any(h in text for h in USPS_HINTS):
        return RouteResult(None, "unsupported:usps")
    if n.startswith("1Z"):
        return RouteResult("ups")
    digits = re.sub(r"\D", "", n)
    if len(digits) in (12, 15) or (len(digits) >= 12 and digits.startswith("96")):
        return RouteResult("fedex")
    return RouteResult(None, "unknown")
