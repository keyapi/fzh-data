# -*- coding: utf-8 -*-
"""渠道账号快照：大小写冲突只警告，真歧义 raise。"""
import json

import pytest

import channel_canonical


def _write(tmp_path, rows):
    path = tmp_path / "snap.json"
    header = ["运营账号编号", "渠道", "渠道账号", "渠道账号别名"]
    path.write_text(json.dumps({"header": header, "rows": [header, *rows]}, ensure_ascii=False), encoding="utf-8")
    return path


def test_case_only_conflict_warns_not_raises(tmp_path, monkeypatch, capsys):
    path = _write(
        tmp_path,
        [
            ["1", "Amazon", "AMZTOODDLYUS", "美国站-DaneeyUS"],
            ["2", "Amazon", "AMZDANEEYUS", "美国站-DANEEYUS"],
        ],
    )
    monkeypatch.setenv("CHANNEL_ACCOUNT_SNAPSHOT", str(path))
    channel_canonical.load_account_maps.cache_clear()
    to_canon, _display = channel_canonical.load_account_maps()
    # first-wins（与 Colab 的 drop_duplicates keep='first' 一致），但有醒目 WARN
    assert to_canon["美国站-DANEEYUS"] == "AMZTOODDLYUS"
    assert "WARN" in capsys.readouterr().err
    channel_canonical.load_account_maps.cache_clear()


def test_real_conflict_raises(tmp_path, monkeypatch):
    path = _write(
        tmp_path,
        [
            ["1", "Amazon", "AMZACC1", "别名X"],
            ["2", "Amazon", "AMZACC2", "别名Y"],  # 与上一条不同写法的同一 token 不可能，改用重复别名
        ],
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    data["rows"][2][3] = "别名 X"  # norm_token 去空格后与「别名X」相同 → 真歧义
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("CHANNEL_ACCOUNT_SNAPSHOT", str(path))
    channel_canonical.load_account_maps.cache_clear()
    with pytest.raises(ValueError, match="别名冲突"):
        channel_canonical.load_account_maps()
    channel_canonical.load_account_maps.cache_clear()
