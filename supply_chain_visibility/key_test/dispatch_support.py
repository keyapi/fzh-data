"""Import guard for the Frappe dispatch test.

Only "ModuleNotFoundError for frappe itself" is treated as an environment
skip. A missing/broken business module must raise and fail the test.
"""


def _load_dispatch_deps(importer=__import__):
    try:
        frappe_mod = importer("frappe")
    except ModuleNotFoundError as exc:
        if exc.name == "frappe":
            return None, None
        raise
    facts = importer("key_test.supply_facts", fromlist=["_normalize_filters"])
    return frappe_mod, facts._normalize_filters
