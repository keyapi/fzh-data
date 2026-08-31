# -*- coding: utf-8 -*-
"""Extract Colab notebook cell-0 gspread service_account dict to gitignored JSON.

Does not print the private key. Overwrites secrets/gsheets-service-account.json.
"""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_JSON = REPO_ROOT / "secrets" / "gsheets-service-account.json"
MODULE_ENV = Path(__file__).resolve().parents[1] / ".env"

DEFAULT_NB = Path(
    r"g:\我的云端硬盘\Colab Notebooks"
    r"\20260706特殊规则Jeck重算4月之前备份 20260312新特殊规则 账号分人-兼容是否区分清仓 "
    r"透视表订单 20250715 的副本20250812备份 方便用于不区分清仓 20251114区分大类 "
    r"20260115细分收款费用 .ipynb"
)


def extract_credentials(nb_path: Path) -> dict:
    nb = json.loads(nb_path.read_text(encoding="utf-8"))
    src = "".join(nb["cells"][0]["source"])
    start = src.find("credentials = ")
    if start < 0:
        raise RuntimeError("credentials dict not found in notebook cell 0")
    tree = ast.parse(src[start:])
    assign = next(
        n
        for n in tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "credentials" for t in n.targets)
    )
    creds = ast.literal_eval(assign.value)
    if not isinstance(creds, dict) or creds.get("type") != "service_account":
        raise RuntimeError("parsed credentials are not a service_account dict")
    for need in ("client_email", "private_key", "project_id"):
        if not creds.get(need):
            raise RuntimeError(f"service account missing {need}")
    return creds


def ensure_module_env() -> None:
    if MODULE_ENV.exists():
        return
    example = MODULE_ENV.with_name(".env.example")
    if example.exists():
        MODULE_ENV.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")


def main() -> None:
    nb = Path(os.environ.get("COLAB_NOTEBOOK_PATH") or DEFAULT_NB)
    if not nb.exists():
        raise SystemExit(f"notebook not found: {nb}")
    creds = extract_credentials(nb)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(creds, indent=2), encoding="utf-8")
    ensure_module_env()
    print("wrote", OUT_JSON)
    print("client_email_present", bool(creds.get("client_email")))
    print("private_key_present", bool(creds.get("private_key")))
    print("project_id", creds.get("project_id"))
    print("never commit this JSON")


if __name__ == "__main__":
    main()
