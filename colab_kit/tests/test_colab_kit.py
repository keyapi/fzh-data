"""colab_kit 的本地纯函数单测（不碰网络）。

网络命令（fetch/write/verify/guard）用真实 notebook 手测，见 AGENT_HANDOFF.md；
这里只锁住"容易写错且写错很难发现"的那几个纯函数。
"""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from colab_kit import colab_kit as ck  # noqa: E402


def make_nb(*sources: str, cell_type: str = "code") -> dict:
    return {"cells": [ck.new_cell(cell_type, s) for s in sources], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}


def write_nb(tmp_path: pathlib.Path, nb: dict, name: str = "nb.ipynb") -> pathlib.Path:
    p = tmp_path / name
    ck.dump_notebook(nb, p)
    return p


# ── 魔法行中和：必须保留缩进 ────────────────────────────────────────────


def test_neutralize_magics_preserves_indentation():
    """丢缩进会得到假 IndentationError —— 这是实测踩过的坑。"""
    src = ck.split_source("if x:\n    !zip -q a.zip b\n    print(1)\n")
    out = ck.neutralize_magics(src)
    assert "    pass  # !zip" in out
    compile(out, "<t>", "exec")  # 不抛 = 缩进保留了


def test_neutralize_magics_without_indent_still_valid():
    src = ck.split_source("!pip install foo\nx = 1\n")
    compile(ck.neutralize_magics(src), "<t>", "exec")


def test_compile_cell_accepts_magic_lines():
    cell = ck.new_cell("code", "!zip -q a.zip b\nprint('ok')\n")
    ck.compile_cell(cell)  # 不抛即通过


def test_compile_cell_rejects_broken_syntax():
    cell = ck.new_cell("code", "def f(:\n")
    with pytest.raises(SyntaxError):
        ck.compile_cell(cell)


# ── 备份格 / 插入 ──────────────────────────────────────────────────────


def test_backup_cell_clones_next_to_original(tmp_path, monkeypatch):
    nb = make_nb("A\n", "B\n")
    nb["cells"][0]["outputs"] = [{"output_type": "stream", "text": "noise"}]
    path = write_nb(tmp_path, nb)
    monkeypatch.setattr(sys, "argv", ["colab_kit", "backup-cell", str(path), "--index", "0", "--after", "1"])
    assert ck.main() == 0

    after = ck.load_notebook(path)
    assert len(after["cells"]) == 3
    assert ck.cell_source(after["cells"][2]) == "A\n"  # 原文逐字
    assert after["cells"][2]["id"] != after["cells"][0]["id"]  # 新 id
    assert after["cells"][2]["outputs"] == []  # 输出不跟着抄


def test_insert_after_adds_cell_at_right_index(tmp_path, monkeypatch):
    nb = make_nb("A\n", "B\n")
    path = write_nb(tmp_path, nb)
    payload = tmp_path / "new.py"
    payload.write_text("print('new')\n", encoding="utf-8")
    monkeypatch.setattr(
        sys, "argv",
        ["colab_kit", "insert", str(path), "--after", "0", "--from", str(payload), "--title", "3.x 备份"],
    )
    assert ck.main() == 0

    after = ck.load_notebook(path)
    assert len(after["cells"]) == 3
    assert ck.cell_source(after["cells"][1]).startswith("#@title 3.x 备份\n")
    assert ck.cell_source(after["cells"][2]) == "B\n"  # 原来的 B 被推到后面


# ── sed：唯一命中保护 ──────────────────────────────────────────────────


def test_sed_replaces_when_unique(tmp_path, monkeypatch):
    nb = make_nb("x = 1\n")
    path = write_nb(tmp_path, nb)
    monkeypatch.setattr(
        sys, "argv",
        ["colab_kit", "sed", str(path), "--index", "0", "--old", "x = 1", "--new", "x = 2"],
    )
    assert ck.main() == 0
    assert ck.cell_source(ck.load_notebook(path)["cells"][0]) == "x = 2\n"


def test_sed_refuses_ambiguous_old_without_all(tmp_path, monkeypatch):
    nb = make_nb("a\na\n")
    path = write_nb(tmp_path, nb)
    monkeypatch.setattr(
        sys, "argv",
        ["colab_kit", "sed", str(path), "--index", "0", "--old", "a", "--new", "b"],
    )
    assert ck.main() == 1  # 拒绝
    assert ck.cell_source(ck.load_notebook(path)["cells"][0]) == "a\na\n"  # 一字未改


def test_sed_reports_missing_old(tmp_path, monkeypatch):
    nb = make_nb("a\n")
    path = write_nb(tmp_path, nb)
    monkeypatch.setattr(
        sys, "argv",
        ["colab_kit", "sed", str(path), "--index", "0", "--old", "zzz", "--new", "b"],
    )
    assert ck.main() == 1


# ── 差异比对（verify / diff 的核心） ────────────────────────────────────


def test_compare_cells_detects_only_the_touched_cell():
    a = make_nb("A\n", "B\n", "C\n")
    b = make_nb("A\n", "B2\n", "C\n")
    assert ck.compare_cells(a, b) == [1]


def test_compare_cells_flags_length_difference():
    a = make_nb("A\n")
    b = make_nb("A\n", "B\n")
    assert ck.compare_cells(a, b) == [1]


def test_compare_cells_identical_is_empty():
    import copy

    a = make_nb("A\n", "B\n")
    assert ck.compare_cells(a, copy.deepcopy(a)) == []


# ── find / cells 输出 ──────────────────────────────────────────────────


def test_find_locate_anchor(tmp_path, monkeypatch, capsys):
    nb = make_nb("merged_sku = ', '.join(x)\n", "# merged_sku = ', '.join(x)\n")
    path = write_nb(tmp_path, nb)
    monkeypatch.setattr(sys, "argv", ["colab_kit", "find", str(path), "--text", "merged_sku = "])
    assert ck.main() == 0
    out = capsys.readouterr().out
    assert "命中 2 格" in out  # 生效行 + 注释掉的老代码 —— 所以 sed 的唯一命中保护是必要的


def test_roundtrip_json_shape_stable(tmp_path):
    """写盘再读回，cell 结构与 Colab 落盘习惯一致（indent=1、source 为行列表）。"""
    nb = make_nb("A\n", "B\n")
    path = write_nb(tmp_path, nb)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(raw["cells"][0]["source"], list)
    assert raw["cells"][0]["cell_type"] == "code"
    assert "id" in raw["cells"][0]
    assert ck.compare_cells(nb, ck.load_notebook(path)) == []
