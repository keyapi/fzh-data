"""配置层：加载 / 校验 / 哈希 / 来源 / 不可变性。

参数口径见 decision-defaults.md（2026-11-24）；本文件只测配置对象本身，
不涉及 decide/refresh（本任务不改变决策行为）。
"""
import json
from dataclasses import FrozenInstanceError

import pytest

from supply_copilot.cli import main
from supply_copilot.config import (
    PARAMS,
    SCHEMA_VERSION,
    ConfigError,
    load_config,
    scope_rank,
)

DEFAULTS_HASH = load_config().config_hash


def write_config(tmp_path, doc, name="cfg.json"):
    path = tmp_path / name
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def file_doc(values, *, scope=None, version="cfg-test.1", schema=SCHEMA_VERSION):
    doc = {"schema_version": schema, "config_version": version, "values": values}
    if scope is not None:
        doc["scope"] = scope
    return doc


# --- 1) 默认加载 -----------------------------------------------------------

def test_defaults_load_all_params():
    cfg = load_config()
    assert cfg.schema_version == SCHEMA_VERSION
    assert len(cfg.values) == len(PARAMS) == 49
    assert cfg.defaulted == tuple(PARAMS)
    assert all(source == "default" for source in cfg.sources.values())
    assert cfg["moq"] is None and cfg["order_multiple"] is None   # 自有工厂无 MOQ
    assert cfg["review_period_R"] == 7
    assert len(cfg.config_hash) == 64 and cfg.config_hash == DEFAULTS_HASH
    json.dumps(cfg.to_dict(), ensure_ascii=False)   # to_dict 可 JSON 序列化
    assert cfg.to_dict()["values"]["abc_breaks"]["sales_share"] == [0.8, 0.95]


# --- 2) 文件覆盖 + 来源 ----------------------------------------------------

def test_file_override_tracks_source_and_scope(tmp_path):
    path = write_config(tmp_path, file_doc({"review_period_R": 10},
                                           scope={"branch": "USNJ"}))
    cfg = load_config(path)
    assert cfg["review_period_R"] == 10
    assert cfg.sources["review_period_R"] == "file"
    assert cfg.scopes["review_period_R"] == {"branch": "USNJ"}
    assert scope_rank(cfg.scopes["review_period_R"]) == 1
    assert "review_period_R" not in cfg.defaulted
    assert cfg.sources["moq"] == "default" and "moq" in cfg.defaulted
    assert cfg.config_version == "cfg-test.1"
    assert cfg.config_hash != DEFAULTS_HASH
    assert cfg.path == str(path)


def test_override_precedence_over_file(tmp_path):
    path = write_config(tmp_path, file_doc({"review_period_R": 10},
                                           scope={"branch": "USNJ"}))
    cfg = load_config(path, overrides={"review_period_R": 9})
    assert cfg["review_period_R"] == 9
    assert cfg.sources["review_period_R"] == "override"
    assert cfg.config_hash != load_config(path).config_hash


# --- 3) 未知键拒绝 ---------------------------------------------------------

def test_unknown_param_rejected_with_suggestion(tmp_path):
    path = write_config(tmp_path, file_doc({"MOQ": 10}))
    with pytest.raises(ConfigError) as exc:
        load_config(path)
    assert "未知参数 MOQ" in str(exc.value)
    assert "moq" in str(exc.value)      # 近名建议


def test_unknown_nested_field_rejected(tmp_path):
    values = {"soft_budget_warning": {
        "amount_ratio": 1.2, "qty_ratio": 1.2,
        "threshold_min": 0.1, "threshold_max": 1.0, "extra_field": 1}}
    path = write_config(tmp_path, file_doc(values))
    with pytest.raises(ConfigError) as exc:
        load_config(path)
    assert "未知字段" in str(exc.value) and "extra_field" in str(exc.value)


def test_unknown_variable_in_overrides_rejected():
    with pytest.raises(ConfigError) as exc:
        load_config(overrides={"MOQ": 10})
    assert "overrides: 未知参数 MOQ" in str(exc.value)


# --- 4) 越界 / 枚举 / 类型 / 不变式 ---------------------------------------

@pytest.mark.parametrize("bad", [0, 31])
def test_out_of_range_rejected(tmp_path, bad):
    path = write_config(tmp_path, file_doc({"review_period_R": bad},
                                           scope={"branch": "USNJ"}))
    with pytest.raises(ConfigError) as exc:
        load_config(path)
    assert "review_period_R" in str(exc.value)
    assert "下限" in str(exc.value) or "上限" in str(exc.value)


def test_enum_rejected(tmp_path):
    path = write_config(tmp_path, file_doc({"inventory_policy": "magic"},
                                           scope={"branch": "USNJ"}))
    with pytest.raises(ConfigError) as exc:
        load_config(path)
    assert "inventory_policy" in str(exc.value) and "只允许" in str(exc.value)


def test_wrong_type_rejected(tmp_path):
    path = write_config(tmp_path, file_doc({"review_period_R": "7"},
                                           scope={"branch": "USNJ"}))
    with pytest.raises(ConfigError) as exc:
        load_config(path)
    assert "需要整数" in str(exc.value)


def test_age_threshold_ordering_enforced(tmp_path):
    bad = {"ok_max_hours": 24, "warn_max_hours": 24, "hold_after_hours": 20,
           "warn_hours_min": 12, "warn_hours_max": 24,
           "hold_hours_min": 24, "hold_hours_max": 72}
    path = write_config(tmp_path, file_doc({"inventory_age": bad},
                                           scope={"branch": "USNJ"}))
    with pytest.raises(ConfigError) as exc:
        load_config(path)
    assert "hold_after_hours" in str(exc.value)


def test_abc_breaks_must_be_ordered(tmp_path):
    path = write_config(tmp_path, file_doc(
        {"abc_breaks": {"sales_share": [0.95, 0.8]}}, scope={"branch": "USNJ"}))
    with pytest.raises(ConfigError) as exc:
        load_config(path)
    assert "sales_share" in str(exc.value) and "递增" in str(exc.value)


def test_new_quantile_requires_new_version(tmp_path):
    preset = {"name": "balance", "A": 0.97, "B": 0.9, "C": 0.85, "D": 0.85}
    path = write_config(tmp_path, file_doc({"quantile_preset": preset},
                                           scope={"branch": "USNJ"}))
    with pytest.raises(ConfigError) as exc:
        load_config(path)
    assert "分位 0.97 不在" in str(exc.value)


# --- 5) 作用域校验 ---------------------------------------------------------

def test_global_scope_rejected_for_branch_only_param(tmp_path):
    path = write_config(tmp_path, file_doc({"moq": 10}))
    with pytest.raises(ConfigError) as exc:
        load_config(path)
    assert "moq.scope" in str(exc.value) and "不能全局设置" in str(exc.value)


def test_sku_exception_requires_pool_form_uom_period(tmp_path):
    partial = {"branch": "USNJ", "sku": "KS0001", "warehouse_pool": "美东USNJ"}
    path = write_config(tmp_path, file_doc({"moq": {"value": 120, "scope": partial}}))
    with pytest.raises(ConfigError) as exc:
        load_config(path)
    message = str(exc.value)
    assert "SKU 例外必须同时带仓/形态/UOM/期间" in message
    assert "physical_form" in message and "uom" in message and "period" in message


def test_complete_sku_exception_accepted(tmp_path):
    scope = {"branch": "USNJ", "sku": "KS0001", "warehouse_pool": "美东USNJ",
             "physical_form": "成品", "uom": "个",
             "period": ["2026-11-01", "2026-11-30"]}
    path = write_config(tmp_path, file_doc(
        {"moq": {"value": 120, "scope": scope, "expires_at": "2026-12-01"}}))
    cfg = load_config(path)
    assert cfg["moq"] == 120
    assert cfg.scopes["moq"]["sku"] == "KS0001"
    assert scope_rank(cfg.scopes["moq"]) == 3


def test_scope_level_not_allowed_for_param(tmp_path):
    values = {"fva_metric": {"primary": "fva_wape",
                             "secondary": ["bias"], "frozen": True,
                             "allowed_extra": ["mase"]}}
    path = write_config(tmp_path, file_doc(values, scope={"branch": "USNJ"}))
    with pytest.raises(ConfigError) as exc:
        load_config(path)
    assert "fva_metric.scope.branch" in str(exc.value)


# --- 6) 受保护硬约束 -------------------------------------------------------

def test_protected_constraints_cannot_be_overridden(tmp_path):
    path = write_config(tmp_path, file_doc({"auto_order": False}))
    with pytest.raises(ConfigError) as exc:
        load_config(path)
    assert "受保护硬约束" in str(exc.value)
    with pytest.raises(ConfigError):
        load_config(overrides={"unknown_as_zero": False})


def test_protected_defaults_are_false():
    cfg = load_config()
    for key in ("auto_order", "write_en_business",
                "allow_self_approval", "unknown_as_zero"):
        assert cfg[key] is False and PARAMS[key].protected


# --- 7) schema_version -----------------------------------------------------

def test_schema_major_mismatch_rejected(tmp_path):
    path = write_config(tmp_path, file_doc({}, schema="supply-config/v2"))
    with pytest.raises(ConfigError) as exc:
        load_config(path)
    assert "unsupported_schema" in str(exc.value)


def test_schema_missing_rejected(tmp_path):
    path = write_config(tmp_path, {"values": {}})
    with pytest.raises(ConfigError) as exc:
        load_config(path)
    assert "缺少 schema_version" in str(exc.value)


def test_schema_minor_accepted(tmp_path):
    path = write_config(tmp_path, file_doc({}, schema="supply-config/v1.2"))
    assert load_config(path).schema_version == SCHEMA_VERSION


# --- 8) 哈希稳定 -----------------------------------------------------------

def test_hash_stable_across_key_order(tmp_path):
    a = {"review_period_R": 10,
         "soft_budget_warning": {"amount_ratio": 1.2, "qty_ratio": 1.2,
                                 "threshold_min": 0.1, "threshold_max": 1.0}}
    b = dict(reversed(list(a.items())))
    b["soft_budget_warning"] = dict(reversed(list(a["soft_budget_warning"].items())))
    path_a = write_config(tmp_path, file_doc(a, scope={"branch": "USNJ"}), "a.json")
    path_b = write_config(tmp_path, file_doc(b, scope={"branch": "USNJ"}), "b.json")
    assert load_config(path_a).config_hash == load_config(path_b).config_hash


def test_hash_ignores_metadata_and_matches_equal_content(tmp_path):
    # 显式写入与默认相同的值 → 内容哈希不变
    path = write_config(tmp_path, file_doc(
        {"review_period_R": 7}, version="whatever.9", scope={"branch": "USNJ"}))
    cfg = load_config(path)
    assert cfg.config_hash == DEFAULTS_HASH
    assert cfg.config_version == "whatever.9"


# --- 9) explain 来源 -------------------------------------------------------

def test_explain_reports_value_source_default_range_scope(tmp_path):
    path = write_config(tmp_path, file_doc({"review_period_R": 10},
                                           scope={"branch": "USNJ"}))
    rows = {row["key"]: row for row in load_config(path).explain()}
    assert len(rows) == len(PARAMS)

    overridden = rows["review_period_R"]
    assert overridden["value"] == 10 and overridden["source"] == "file"
    assert overridden["default"] == 7
    assert overridden["range"] == "1–30"
    assert overridden["scopes"] == ["branch", "segment"]
    assert overridden["scope"] == {"branch": "USNJ"}

    untouched = rows["moq"]
    assert untouched["source"] == "default" and untouched["value"] is None
    assert untouched["default"] is None and untouched["nullable"] is True
    assert rows["auto_order"]["choices"] == [False]


# --- 10) 不可变性 ----------------------------------------------------------

def test_config_is_immutable_including_nested():
    cfg = load_config()
    with pytest.raises(FrozenInstanceError):
        cfg.values = {}
    with pytest.raises(TypeError):
        cfg.values["moq"] = 1
    with pytest.raises(TypeError):
        cfg.values["quantile_preset"]["A"] = 0.5
    assert isinstance(cfg.values["abc_breaks"]["sales_share"], tuple)
    # to_dict 返回可变拷贝，改它不影响配置
    copy = cfg.to_dict()
    copy["values"]["moq"] = 99
    assert cfg["moq"] is None


# --- 11) CLI（只读） -------------------------------------------------------

def test_cli_hash_and_validate(tmp_path, capsys):
    path = write_config(tmp_path, file_doc({"review_period_R": 10},
                                           scope={"branch": "USNJ"}))
    assert main(["config", "hash", "--config", str(path)]) == 0
    assert capsys.readouterr().out.strip() == load_config(path).config_hash

    assert main(["config", "validate", "--config", str(path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok" and payload["params"] == 49
    assert "review_period_R" not in payload["defaulted"]


def test_cli_show_and_invalid_file(tmp_path, capsys):
    assert main(["config", "show"]) == 0
    out = capsys.readouterr().out
    assert "sha256=" in out and "auto_order" in out and "[false]" in out

    bad = write_config(tmp_path, file_doc({"review_period_R": 99},
                                          scope={"branch": "USNJ"}), "bad.json")
    assert main(["config", "validate", "--config", str(bad)]) == 2
    assert "review_period_R" in capsys.readouterr().err
