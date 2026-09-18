"""离线单测：CLI 输入装载（通途 xlsx 筛 GLS + 去重；txt 号+邮编）。"""

import pandas as pd

from gls_track.cli import _load_records

FRAME = pd.DataFrame(
    [
        {"发货日期": "2026-08-03", "邮寄方式": "GLS-Poland>>GLS-Poland", "跟踪号": "29626350334", "邮编": "12305", "国家/地区": "DE"},
        {"发货日期": "2026-08-03", "邮寄方式": "GLS-Poland>>GLS-Poland", "跟踪号": "29626350334", "邮编": "12305", "国家/地区": "DE"},
        {"发货日期": "2026-08-03", "邮寄方式": "GLS-Poland>>GLS-NL", "跟踪号": "29626573708", "邮编": "5662 HH", "国家/地区": "NL"},
        {"发货日期": "2026-08-03", "邮寄方式": "GLS-Poland>>GLS-Poland", "跟踪号": "2962657xxxx", "邮编": None, "国家/地区": "FR"},
        {"发货日期": "2026-08-03", "邮寄方式": "GLS-Poland>>GLS-Poland", "跟踪号": "", "邮编": "0000", "国家/地区": "PL"},
        {"发货日期": "2026-08-03", "邮寄方式": "US-FedEx>>US-FedEx", "跟踪号": "123456789012", "邮编": "10001", "国家/地区": "US"},
        # 一格多号：应拆成 2 个真 GLS 号
        {"发货日期": "2026-08-03", "邮寄方式": "GLS-Poland>>GLS-Poland", "跟踪号": "29626378449, 29626378441", "邮编": "60306", "国家/地区": "DE"},
    ]
)


def test_load_xlsx_filters_dedupes_and_keeps_postal(tmp_path):
    path = tmp_path / "orders.xlsx"
    FRAME.to_excel(path, index=False)
    recs = _load_records(str(path), "gls-poland", limit=None)
    nos = [r["跟踪号"] for r in recs]
    # 去重、排除空号/FedEx；一格多号拆成 29626378449 / 29626378441
    assert nos == ["29626350334", "29626573708", "2962657xxxx", "29626378449", "29626378441"]
    by_no = {r["跟踪号"]: r for r in recs}
    assert by_no["29626350334"]["邮编"] == "12305"
    assert by_no["2962657xxxx"]["邮编"] == ""  # 无邮编 → 摘要
    assert by_no["29626573708"]["国家/地区"] == "NL"
    assert by_no["29626378449"]["邮编"] == "60306"
    assert by_no["29626378441"]["邮编"] == "60306"


def test_load_txt(tmp_path):
    path = tmp_path / "nos.txt"
    path.write_text("# comment\n29626350334 12305\n2962657xxxx\n", encoding="utf-8")
    recs = _load_records(str(path), "gls-poland", limit=1)
    assert len(recs) == 1 and recs[0]["跟踪号"] == "29626350334" and recs[0]["邮编"] == "12305"
    recs = _load_records(str(path), "gls-poland", limit=None)
    assert recs[1]["邮编"] == ""  # 无邮编第二号
