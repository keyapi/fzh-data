# -*- coding: utf-8 -*-
"""audit_sources（U1 只读盘点/快照）单元测试 —— 全程不联网。"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tongtool_order_cost import audit_sources as A  # noqa: E402


class FakeSheetReader:
    """只读协议实现 + 一个「被调用就会炸」的写方法（证明快照从不写）。"""

    def __init__(self, books, fail_reads=(), formula_books=None):
        self.books = books
        self.formula_books = formula_books or {}
        self.fail_reads = set(fail_reads)
        self.read_calls = []
        self.write_calls = []

    def list_worksheets(self, spreadsheet):
        book = self.books[spreadsheet]
        return [
            A.WorksheetMeta(
                title=title,
                row_count=len(values),
                col_count=len(values[0]) if values else 0,
            )
            for title, values in book.items()
        ]

    def read_values(self, spreadsheet, worksheet, render_option="values"):
        self.read_calls.append((spreadsheet, worksheet, render_option))
        if f"{spreadsheet}::{worksheet}" in self.fail_reads:
            raise RuntimeError("simulated read failure")
        if render_option == "formulas":
            book = self.formula_books.get(spreadsheet, {})
            if worksheet in book:
                return book[worksheet]
        return self.books[spreadsheet][worksheet]

    # 禁止调用的写方法
    def update(self, *args, **kwargs):  # pragma: no cover - 不应被调用
        self.write_calls.append((args, kwargs))
        raise AssertionError("write attempted on read-only reader")


def _july_book():
    return {
        "通途订单202607": {
            "2026年7月订单": [
                ["订单号", "通途SKU", "物流商运费"],
                ["A-1", "SKU-1", "12.5"],
                ["A-2", "SKU-2", ""],
            ],
            "2026年7月FBA订单": [["订单号", "通途SKU"], ["B-1", "SKU-3"]],
            "写回2026年7月订单": [["订单号", "产品成本"], ["A-1", "30"]],
            "写回2026年7月FBA订单": [["订单号", "产品成本"], ["B-1", "40"]],
            "弃用2026年7月订单": [["订单号"], ["A-1"]],
            "透视表2品类": [["品类", "利润"], ["床", "100"]],
        }
    }


def test_classify_roles_by_prefix_and_headers():
    assert A.classify_worksheet("2026年7月订单", ["订单号", "通途SKU"]) == A.RAW
    assert A.classify_worksheet("2026年7月FBA订单", []) == A.RAW_FBA
    assert A.classify_worksheet("写回2026年7月订单", []) == A.WRITEBACK
    assert A.classify_worksheet("写回2026年7月FBA订单", []) == A.WRITEBACK_FBA
    assert (
        A.classify_worksheet("写回2026年7月FBA订单和非FBA订单", [])
        == A.WRITEBACK_COMBINED
    )
    assert (
        A.classify_worksheet("检查运营人员-写回2026年7月FBA订单和非FBA订单", [])
        == A.CHECK
    )
    assert A.classify_worksheet("透视表2品类", []) == A.PIVOT
    assert A.classify_worksheet("弃用2026年7月订单", []) == A.ARCHIVE
    assert A.classify_worksheet("备份账号", []) == A.BACKUP
    assert A.classify_worksheet("处理特殊订单", ["订单号"]) == A.RAW
    assert A.classify_worksheet("处理特殊订单", ["备注"]) == A.OTHER


def test_derived_sheets_are_never_classified_raw():
    for title in (
        "写回2026年7月订单",
        "写回2026年7月FBA订单",
        "写回2026年7月FBA订单和非FBA订单",
        "检查运营人员-写回2026年7月FBA订单和非FBA订单",
    ):
        # 即便带着 订单号 列，也不能被当原始表
        assert A.classify_worksheet(title, ["订单号", "通途SKU"]) != A.RAW


def test_snapshot_records_all_and_only_raw_as_raw(tmp_path):
    reader = FakeSheetReader(_july_book())
    specs = [
        A.SourceSpec("raw", "通途订单202607", "2026年7月订单", required=True, required_columns=("订单号",)),
        A.SourceSpec("wb", "通途订单202607", "写回2026年7月订单"),
    ]
    manifest = A.snapshot_sources(reader, specs, tmp_path)

    assert A.require_successful(manifest) is None
    raw = manifest.find("raw")
    assert raw.status == "ok" and raw.role == A.RAW
    assert raw.data_rows == 2 and raw.column_count == 3
    assert raw.columns == ["订单号", "通途SKU", "物流商运费"]
    assert (tmp_path / raw.path).exists()

    wb = manifest.find("wb")
    assert wb.role == A.WRITEBACK
    # CSV 落盘原样保留（含空字符串单元格）
    text = (tmp_path / raw.path).read_text(encoding="utf-8-sig")
    assert "A-2,SKU-2," in text.replace("\r\n", "\n")


def test_snapshot_fails_on_missing_required_header(tmp_path):
    book = {"通途订单202607": {"2026年7月订单": [["通途SKU"], ["SKU-1"]]}}
    reader = FakeSheetReader(book)
    specs = [
        A.SourceSpec("raw", "通途订单202607", "2026年7月订单", required=True, required_columns=("订单号",))
    ]
    manifest = A.snapshot_sources(reader, specs, tmp_path)
    rec = manifest.find("raw")
    assert rec.status == "failed"
    assert "订单号" in rec.error
    assert manifest.failures and manifest.failures[0]["key"] == "raw"
    try:
        A.require_successful(manifest)
        raise AssertionError("应当阻断")
    except RuntimeError as exc:
        assert "已阻断" in str(exc)


def test_snapshot_missing_worksheet_is_recorded_not_crashed(tmp_path):
    reader = FakeSheetReader(_july_book())
    specs = [A.SourceSpec("ghost", "通途订单202607", "不存在的表")]
    manifest = A.snapshot_sources(reader, specs, tmp_path)
    assert manifest.find("ghost").status == "failed"
    assert "worksheet 不存在" in manifest.find("ghost").error


def test_partial_read_failure_isolated(tmp_path):
    reader = FakeSheetReader(
        _july_book(), fail_reads={"通途订单202607::写回2026年7月订单"}
    )
    specs = [
        A.SourceSpec("raw", "通途订单202607", "2026年7月订单", required=True),
        A.SourceSpec("wb", "通途订单202607", "写回2026年7月订单"),
    ]
    manifest = A.snapshot_sources(reader, specs, tmp_path)
    assert manifest.find("raw").status == "ok"
    assert manifest.find("wb").status == "failed"
    assert "simulated read failure" in manifest.find("wb").error
    A.require_successful(manifest)  # 非必需源失败不阻断


def test_hash_is_deterministic_and_content_sensitive():
    rows_a = [["订单号", "x"], ["A", "1"]]
    rows_b = [["订单号", "x"], ["A", "1"]]
    rows_c = [["订单号", "x"], ["A", "2"]]
    assert A._sha256_of_rows(rows_a) == A._sha256_of_rows(rows_b)
    assert A._sha256_of_rows(rows_a) != A._sha256_of_rows(rows_c)


def test_snapshot_never_invokes_write_method(tmp_path):
    reader = FakeSheetReader(_july_book())
    specs = [A.SourceSpec("raw", "通途订单202607", "2026年7月订单", required=True)]
    A.snapshot_sources(reader, specs, tmp_path)
    assert reader.write_calls == []


def test_snapshot_freezes_values_and_formulas_separately(tmp_path):
    book = {"二次加工成本2022": {"绍兴二次加工成本": [["键", "成本"], ["K1", "10"]]}}
    formula_books = {
        "二次加工成本2022": {"绍兴二次加工成本": [["键", "成本"], ["K1", "=1+9"]]}
    }
    reader = FakeSheetReader(book, formula_books=formula_books)
    specs = [
        A.SourceSpec(
            "sx_values", "二次加工成本2022", "绍兴二次加工成本", render_option="values"
        ),
        A.SourceSpec(
            "sx_formulas", "二次加工成本2022", "绍兴二次加工成本", render_option="formulas"
        ),
    ]
    manifest = A.snapshot_sources(reader, specs, tmp_path)

    v = manifest.find("sx_values")
    f = manifest.find("sx_formulas")
    assert v.status == "ok" and f.status == "ok"
    assert v.render_option == "values" and f.render_option == "formulas"
    assert v.sha256 != f.sha256
    assert v.path != f.path
    assert "=1+9" in (tmp_path / f.path).read_text(encoding="utf-8-sig")
    assert "=1+9" not in (tmp_path / v.path).read_text(encoding="utf-8-sig")


def test_required_formula_source_failure_keeps_neighbors(tmp_path):
    book = {
        "二次加工成本2022": {
            "绍兴二次加工成本": [["键", "成本"], ["K1", "10"]],
            "import皮壳成本": [["键", "皮壳成本"], ["K1", "3"]],
        }
    }
    reader = FakeSheetReader(book, fail_reads={"二次加工成本2022::绍兴二次加工成本"})
    specs = [
        A.SourceSpec(
            "sx_processing_formulas",
            "二次加工成本2022",
            "绍兴二次加工成本",
            required=True,
            render_option="formulas",
        ),
        A.SourceSpec("shell_cost_import_values", "二次加工成本2022", "import皮壳成本"),
    ]
    manifest = A.snapshot_sources(reader, specs, tmp_path)

    rec = manifest.find("sx_processing_formulas")
    assert rec.status == "failed"
    assert rec.render_option == "formulas"
    assert "simulated read failure" in rec.error
    assert manifest.find("shell_cost_import_values").status == "ok"

    import pytest

    with pytest.raises(RuntimeError):
        A.require_successful(manifest)


def test_snapshot_with_render_options_never_writes(tmp_path):
    book = {"二次加工成本2022": {"绍兴二次加工成本": [["键", "成本"], ["K1", "10"]]}}
    formula_books = {
        "二次加工成本2022": {"绍兴二次加工成本": [["键", "成本"], ["K1", "=1+9"]]}
    }
    reader = FakeSheetReader(book, formula_books=formula_books)
    specs = [
        A.SourceSpec("v", "二次加工成本2022", "绍兴二次加工成本", render_option="values"),
        A.SourceSpec("f", "二次加工成本2022", "绍兴二次加工成本", render_option="formulas"),
    ]
    A.snapshot_sources(reader, specs, tmp_path)
    assert reader.write_calls == []
    assert ("二次加工成本2022", "绍兴二次加工成本", "formulas") in reader.read_calls


def test_require_single_choice_blocks_ambiguous_candidates():
    assert A.require_single_choice(["a"], role="fx") == "a"
    assert A.require_single_choice([], role="fx") is None
    assert A.require_single_choice(["fx1", "fx2"], role="fx", explicit="fx2") == "fx2"

    import pytest

    with pytest.raises(ValueError):
        A.require_single_choice(["fx1", "fx2"], role="fx")
    with pytest.raises(ValueError):
        A.require_single_choice(["fx1", "fx2"], role="fx", explicit="nope")


def test_readonly_reader_exposes_no_write_methods():
    A.assert_no_write_methods(A.GspreadSheetReader(object()), "GspreadSheetReader")

    class Evil:
        def read_values(self, *a):
            return []

        def update(self, *a):
            return None

    try:
        A.assert_no_write_methods(Evil(), "Evil")
        raise AssertionError("应当检出写方法")
    except AssertionError as exc:
        assert "update" in str(exc)


def test_manifest_roundtrip_json(tmp_path):
    reader = FakeSheetReader(_july_book())
    manifest = A.snapshot_sources(
        reader, [A.SourceSpec("raw", "通途订单202607", "2026年7月订单", required=True)], tmp_path
    )
    path = A.write_manifest(manifest, tmp_path)
    import json

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["sources"][0]["key"] == "raw"
    assert data["sources"][0]["role"] == A.RAW


def _cli():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "audit_monthly_profitability",
        _ROOT / "scripts" / "audit_monthly_profitability.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cli_derive_names():
    m = _cli()
    assert m._derive_names("202607") == ("通途订单202607", "2026年7月订单")
    assert m._derive_names("202512") == ("通途订单202512", "2025年12月订单")


def test_cli_default_specs_requires_only_raw_and_finds_archives():
    m = _cli()
    titles = [
        "2026年7月订单",
        "2026年7月FBA订单",
        "写回2026年7月订单",
        "写回2026年7月FBA订单",
        "写回2026年7月FBA订单和非FBA订单",
        "检查运营人员-写回2026年7月FBA订单和非FBA订单",
        "弃用2026年7月订单 20260911",
        "弃用2026年7月订单",
        "透视表2品类",
        "2026年6月订单",
    ]
    specs = m.default_specs("202607", titles, "通途订单202607")
    keys = [s.key for s in specs]
    raw = next(s for s in specs if s.key == "raw")
    assert raw.required is True
    assert raw.required_columns == ("订单号", "通途SKU")
    assert "透视表2品类" not in [s.worksheet for s in specs]
    assert "2026年6月订单" not in [s.worksheet for s in specs]
    assert keys.count("archive_0") == 1 and keys.count("archive_1") == 1
    assert [s.worksheet for s in specs if s.key.startswith("archive")] == [
        "弃用2026年7月订单 20260911",
        "弃用2026年7月订单",
    ]
    assert sum(s.required for s in specs) == 1  # 只有 raw 必需


def test_cli_extra_specs_parsing():
    m = _cli()
    specs = m._extra_specs(["bom=和财务部共享::EN产品BOM成本列表20260202"])
    assert specs[0].key == "bom"
    assert specs[0].spreadsheet == "和财务部共享"
    assert specs[0].worksheet == "EN产品BOM成本列表20260202"
    import pytest

    with pytest.raises(ValueError):
        m._extra_specs(["badformat"])


def test_cli_ustx_cost_specs_render_options_and_required():
    m = _cli()
    specs = m.ustx_cost_specs("二次加工成本2022")
    by_key = {s.key: s for s in specs}

    assert by_key["sx_processing_values"].render_option == "values"
    assert by_key["sx_processing_formulas"].render_option == "formulas"
    assert by_key["ustx_estimate_values"].render_option == "values"
    assert by_key["ustx_estimate_formulas"].render_option == "formulas"
    assert by_key["usnj_estimate_values"].render_option == "values"

    # 同表分别冻结值/公式，但 key 与读模式必须不同
    assert (
        by_key["sx_processing_values"].worksheet
        == by_key["sx_processing_formulas"].worksheet
        == "绍兴二次加工成本"
    )

    required_keys = {s.key for s in specs if s.required}
    assert required_keys == {
        "sx_processing_values",
        "sx_processing_formulas",
        "ustx_estimate_values",
        "ustx_estimate_formulas",
        "shell_cost_import_values",
        "bom_cost_import_values",
    }
    assert by_key["usnj_estimate_values"].required is False
    assert all(s.spreadsheet == "二次加工成本2022" for s in specs)


def test_resilient_fetch_isolates_failure_and_keeps_neighbors():
    def fetch(ids):
        if "BAD" in ids:
            raise RuntimeError("boom")
        return [{"name": i} for i in ids]

    failures: list[str] = []
    failed: set[str] = set()
    rows = A.resilient_fetch(fetch, ["A", "BAD", "C"], failures, failed, "order")
    assert rows == [{"name": "A"}, {"name": "C"}]
    assert failed == {"BAD"}
    assert failures == ["order BAD: RuntimeError: boom"]


def test_resilient_fetch_empty_input_makes_no_call():
    def fetch(ids):  # pragma: no cover
        raise AssertionError("should not be called")

    assert A.resilient_fetch(fetch, [], [], set(), "x") == []


def test_chunked_splits_in_order():
    assert list(A.chunked(["a", "b", "c"], 2)) == [["a", "b"], ["c"]]


def test_cli_exposes_no_write_option():
    m = _cli()
    parser = m.build_parser()
    opts: set[str] = set()
    for action in parser._actions:
        opts.update(action.option_strings)
        if hasattr(action, "choices") and action.choices:
            opts.update(str(c) for c in action.choices)
    forbidden = ("apply", "write", "update", "upload", "submit", "delete", "append")
    hit = [o for o in opts if any(f in o.lower() for f in forbidden)]
    assert hit == [], f"CLI 出现了写操作标志: {hit}"


def test_cli_module_does_not_import_monthly_upload():
    src = (_ROOT / "scripts" / "audit_monthly_profitability.py").read_text(encoding="utf-8")
    assert "upload_monthly_order_sheet" not in src
    assert "remap_gsheet_sku" not in src
