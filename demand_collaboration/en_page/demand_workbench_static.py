"""EN whitelist bridge for the demand-workbench Desk Page (static demo mirror).

Install into the trusted ``key_test`` app (see ``en_page/README.md``). The
generator writes a self-contained HTML file into the site's ``private``
directory; this module only reads that fixed file back for a System Manager.
No path input, no writes, no network calls.
"""
from __future__ import annotations

from pathlib import Path

try:
    import frappe
except ImportError:  # Local development has no Frappe runtime.
    frappe = None

PRIVATE_FILE = "demand_workbench.html"
REQUIRED_ROLE = "System Manager"


def _whitelist(fn):
    return frappe.whitelist()(fn) if frappe else fn


@_whitelist
def get_html():
    """Return the prebuilt demo workbench HTML for a logged-in System Manager."""
    if frappe is None:
        raise RuntimeError("get_html requires the Frappe runtime")

    user = frappe.session.user
    if not user or user == "Guest":
        frappe.throw("请登录后查看订货协同工作台", frappe.PermissionError)
    if REQUIRED_ROLE not in set(frappe.get_roles(user)):
        frappe.throw("只有 System Manager 可以查看订货协同工作台", frappe.PermissionError)

    path = Path(frappe.get_site_path("private", PRIVATE_FILE))
    if not path.is_file():
        raise frappe.NotFoundError(f"{PRIVATE_FILE} 尚未部署到站点 private 目录")
    return path.read_text(encoding="utf-8")
