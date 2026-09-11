from pathlib import Path

import pandas as pd
import pytest

from ding_xlsx import (
    enrich,
    exclude_keys,
    flatten_sale_account,
    id_text,
    unique_key,
)
from nas_admin import nas_credentials


def test_id_text_keeps_21_digit_string():
    assert id_text("202607231544000528489") == "202607231544000528489"
    assert id_text(202607231544000528489) == "202607231544000528489"
    assert id_text("2.026072315440005e+20") != "202607231544000528489"


def test_unique_key_matches_registry_formula():
    row = pd.Series(
        {
            "审批编号": "202607231544000528489",
            "账期日期": "2026-07-18",
            "销售账户_展开": "AMZRosoonSE",
            "销售额": "123.45",
        }
    )
    assert unique_key(row) == "202607231544000528489|2026-07-18|AMZRosoonSE|123.45"


def test_flatten_sale_account_prefers_amz_column():
    row = pd.Series(
        {
            "选择平台": "亚马逊",
            "AMZRosoonSE账户": "AMZRosoonSE",
            "新平台销售账户": "should-not-win",
        }
    )
    assert flatten_sale_account(row) == ("AMZRosoonSE", "AMZRosoonSE账户")


def test_enrich_filters_july_and_exclude_keys():
    df = pd.DataFrame(
        [
            {
                "审批编号": "202607231544000528489",
                "账期日期": "2026-07-18",
                "发起时间": "2026-07-23 15:44:00",
                "选择平台": "亚马逊",
                "AMZ账户": "AMZRosoonSE",
                "销售额": "1",
            },
            {
                "审批编号": "202608061717000057610",
                "账期日期": "2026-08-04",
                "发起时间": "2026-08-06 17:17:00",
                "选择平台": "亚马逊",
                "AMZ账户": "AMZJohnaUS",
                "销售额": "2",
            },
        ]
    )
    en = enrich(df)
    july = en[en["账期月"] == "2026-07"]
    assert len(july) == 1
    dropped = exclude_keys(en, {unique_key(en.iloc[0])})
    assert len(dropped) == 1
    assert dropped.iloc[0]["账期月"] == "2026-08"


def test_nas_credentials_require_env(monkeypatch, tmp_path):
    monkeypatch.setattr("nas_admin.NAS_ENV", tmp_path / "missing.env")
    for key in (
        "NAS_ADMIN_USER",
        "NAS_SSH_USER",
        "NAS_USERNAME",
        "NAS_SSH_PASSWORD",
        "NAS_PASSWORD",
        "NAS_URL",
    ):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(RuntimeError, match="NAS_ADMIN_USER"):
        nas_credentials()


def test_nas_credentials_does_not_fall_back_to_dsm_api_user(monkeypatch, tmp_path):
    """NAS_USERNAME 是 DSM API 账号（看不见「财务部」），不能被当成管理员账号静默采用。"""
    env = tmp_path / ".env"
    env.write_text(
        "NAS_USERNAME=fzh.test\nNAS_SSH_PASSWORD=pw\nNAS_URL=https://nas.invalid\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("nas_admin.NAS_ENV", env)
    for k in ("NAS_ADMIN_USER", "NAS_SSH_USER", "NAS_SSH_PASSWORD", "NAS_PASSWORD", "NAS_URL"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(RuntimeError, match="NAS_ADMIN_USER"):
        nas_credentials()


def test_nas_credentials_reads_admin_user(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "NAS_ADMIN_USER=someadmin\nNAS_SSH_PASSWORD=pw\nNAS_URL=https://nas.invalid\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("nas_admin.NAS_ENV", env)
    for k in ("NAS_ADMIN_USER", "NAS_SSH_USER", "NAS_SSH_PASSWORD", "NAS_PASSWORD", "NAS_URL"):
        monkeypatch.delenv(k, raising=False)
    url, user, pwd = nas_credentials()
    assert (url, user, pwd) == ("https://nas.invalid", "someadmin", "pw")


def test_module_has_no_literal_nas_admin_or_personal_path():
    root = Path(__file__).resolve().parents[1]
    offenders = []
    for p in root.rglob("*"):
        if p.suffix.lower() not in {".py", ".md", ".example", ".json"}:
            continue
        if "person_folders.local.json" in p.name:
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        needle_nas = "fzh" + ".nas"
        needle_path = "王" + "忠于"
        if needle_nas in text or needle_path in text:
            offenders.append(str(p.relative_to(root)))
    assert not offenders, offenders
