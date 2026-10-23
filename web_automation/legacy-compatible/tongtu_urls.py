"""Tongtool URL helpers shared by the export and OCR-login paths."""

from __future__ import annotations

ERP_HOST = "erp102.tongtool.com"
PASSPORT_HOST = "passport.tongtool.com"
INVENTORY_FRAGMENT = "goodsbalance"


def looks_like_erp_url(url: str | None) -> bool:
    """True when the browser is on the ERP site rather than the passport login page.

    Tongtool's remember-me cookie can redirect ``passport`` straight to
    ``erp102`` (via ``j_security_check``) without ever rendering the username
    field.  Treat that as an authenticated session instead of waiting for a
    login form that will never appear.
    """
    value = (url or "").strip().lower()
    if not value:
        return False
    return ERP_HOST in value and PASSPORT_HOST not in value


def is_inventory_url(url: str | None) -> bool:
    """True when the page is the stock-balance page the export needs."""
    return looks_like_erp_url(url) and INVENTORY_FRAGMENT in (url or "").lower()
