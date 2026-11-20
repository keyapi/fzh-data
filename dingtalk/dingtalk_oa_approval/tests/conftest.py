# -*- coding: utf-8 -*-
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_SNAPSHOT = {
    "header": ["运营账号编号", "渠道", "渠道账号", "渠道账号别名", "运营人202608"],
    "rows": [
        ["运营账号编号", "渠道", "渠道账号", "渠道账号别名", "运营人202608"],
        ["1", "Amazon", "AMZStruseryUS", "Strusery-US", "甲"],
        ["2", "Amazon", "AMZTOODDLYUS", "美国站-DaneeyUS", "乙"],
        ["3", "Amazon", "AMZDANEEYUS", "美国站-DANEEYUS", "丙"],
    ],
}


@pytest.fixture(autouse=True)
def isolated_snapshot(tmp_path, monkeypatch):
    """所有测试用临时快照，不依赖本机 channel_account_sync/out 的 gitignored 文件。"""
    path = tmp_path / "channel_account_gsheet.json"
    path.write_text(json.dumps(_SNAPSHOT, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("CHANNEL_ACCOUNT_SNAPSHOT", str(path))
    import channel_canonical

    channel_canonical.load_account_maps.cache_clear()
    yield
    channel_canonical.load_account_maps.cache_clear()
