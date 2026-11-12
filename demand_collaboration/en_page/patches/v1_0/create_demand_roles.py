"""Create the two demand collaboration roles idempotently."""
import frappe


def execute():
    for role in ("Demand Contributor", "Demand Reviewer"):
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
                ignore_permissions=True
            )
