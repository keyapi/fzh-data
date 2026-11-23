"""EN whitelist bridge for the supply-workbench Desk Page (read-only demo).

Install into the trusted ``key_test`` app (see ``en_page/README.md``). The
generator writes a single self-contained HTML file into the site's ``private``
directory; this module only reads that fixed file back for a System Manager.
It accepts no path input, performs no writes, and raises ``NotFoundError`` when
the file has not been deployed.
"""
from __future__ import annotations

from pathlib import Path

try:
    import frappe
except ImportError:  # Local development has no Frappe runtime.
    frappe = None

PRIVATE_FILE = "supply_workbench.html"
REQUIRED_ROLE = "System Manager"


def _whitelist(fn):
    return frappe.whitelist()(fn) if frappe else fn


@_whitelist
def get_html():
    """Return the prebuilt workbench HTML for a logged-in System Manager."""
    if frappe is None:
        raise RuntimeError("get_html requires the Frappe runtime")

    user = frappe.session.user
    if not user or user in ("Guest",):
        frappe.throw("请登录后查看补货协同工作台", frappe.PermissionError)
    if REQUIRED_ROLE not in set(frappe.get_roles(user)):
        frappe.throw("只有 System Manager 可以查看补货协同工作台", frappe.PermissionError)

    path = Path(frappe.get_site_path("private", PRIVATE_FILE))
    if not path.is_file():
        raise frappe.NotFoundError(f"{PRIVATE_FILE} 尚未部署到站点 private 目录")
    return path.read_text(encoding="utf-8")
