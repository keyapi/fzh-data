import datetime as dt
import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "upload_monthly_order_sheet.py"
_spec = importlib.util.spec_from_file_location("upload_monthly_order_sheet", _SCRIPT)
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)


@pytest.mark.parametrize("n,exp", [(1, "A"), (26, "Z"), (27, "AA"), (52, "AZ"), (78, "BZ"), (702, "ZZ"), (703, "AAA")])
def test_column_letter(n, exp):
    assert m.column_letter(n) == exp


def test_derive_names():
    assert m.derive_names("202607") == ("通途订单202607", "2026年7月订单")
    assert m.derive_names("202612") == ("通途订单202612", "2026年12月订单")
    with pytest.raises(ValueError):
        m.derive_names("202613")


def test_default_archive_name():
    assert m.default_archive_name("2026年7月订单", dt.date(2026, 9, 11)) == "弃用2026年7月订单 20260911"


def test_unique_title():
    assert m.unique_title(set(), "弃用X") == "弃用X"
    assert m.unique_title({"弃用X"}, "弃用X") == "弃用X (2)"
    assert m.unique_title({"弃用X", "弃用X (2)"}, "弃用X") == "弃用X (3)"


def test_norm_compare():
    assert m.norm("0") == m.norm(0.0) == ("num", 0.0)          # 0 vs 0.0 不误报
    assert m.norm("1,234.50") == m.norm(1234.5)
    assert m.norm("") == m.norm(None) == ("empty",)
    assert m.norm("08:53") != m.norm("0853")


def test_col_numeric_sum():
    assert m.col_numeric_sum(["1", "2.5", "", None, "x", "1,000"]) == 1003.5
