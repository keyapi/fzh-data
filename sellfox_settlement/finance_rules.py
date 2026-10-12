"""Versioned finance-policy config. Pending rules stay side by side."""
from __future__ import annotations

from pathlib import Path

import yaml


DEFAULT_PATH = Path(__file__).with_name("finance_rules.yaml")


def load_finance_rules(path=None):
    rules = yaml.safe_load(Path(path or DEFAULT_PATH).read_text(encoding="utf-8"))
    status = rules.get("status")
    selected = rules.get("selected_income_candidate", "unconfirmed")
    candidates = set(rules.get("income_candidates") or {})
    if status == "pending_ZJ":
        if selected not in (None, "unconfirmed"):
            raise ValueError("income candidate cannot be selected while ZJ has not confirmed")
    elif status == "confirmed":
        if selected not in candidates:
            raise ValueError("confirmed income candidate is not in the config")
    else:
        raise ValueError("unknown finance rules status")
    if not candidates:
        raise ValueError("finance rules need at least one income candidate")
    return rules


def selected_income_candidate(rules):
    if rules.get("status") != "confirmed":
        return None
    return rules["selected_income_candidate"]
