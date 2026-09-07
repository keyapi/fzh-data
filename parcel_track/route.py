"""从通途列 + 跟踪号形态判断承运商。列优先于正则。"""

from __future__ import annotations

import re
from dataclasses import dataclass

UPS_HINTS = ("ups", "联合包裹")
FEDEX_HINTS = ("fedex", "联邦")
GLS_HINTS = ("gls",)
GOFO_HINTS = ("gofo",)


@dataclass
class RouteResult:
    carrier: str | None
    reason: str = ""


def _norm_number(s: str) -> str:
    s = (s or "").replace(" ", "").replace("\t", "").strip().upper()
    for ch in ("-", "_", ",", "，", "'"):
        s = s.replace(ch, "")
    return s


def _hay(ident: dict) -> str:
    parts = [ident.get("邮寄方式") or "", ident.get("渠道") or ""]
    return " ".join(parts).lower()


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
        return RouteResult(None, "unsupported:gls")
    if any(h in text for h in GOFO_HINTS) or n.startswith("GFUS"):
        return RouteResult(None, "unsupported:gofo")
    if n.startswith("1Z"):
        return RouteResult("ups")
    digits = re.sub(r"\D", "", n)
    if len(digits) in (12, 15) or (len(digits) >= 12 and digits.startswith("96")):
        return RouteResult("fedex")
    return RouteResult(None, "unknown")
