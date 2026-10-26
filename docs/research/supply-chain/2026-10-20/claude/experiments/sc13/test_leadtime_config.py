#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Acceptance examples for the SC13 lead-time config contract.

The contract's whole point is that NOTHING silently defaults, so every negative
case here asserts a SPECIFIC exception type and that the message names the field
or the version. A generic Exception would not be enough.

Run either way:
  uv run python docs/research/supply-chain/2026-10-20/claude/experiments/sc13/test_leadtime_config.py
  uv run python -m pytest docs/research/supply-chain/2026-10-20/claude/experiments/sc13/test_leadtime_config.py -q
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import leadtime_config as lt  # noqa: E402

HERE = Path(__file__).resolve().parent
SAMPLE = HERE / "examples" / "leadtime_config.sample.json"


def write(tmp: Path, doc, name: str = "cfg.json") -> Path:
    p = tmp / name
    p.write_text(doc if isinstance(doc, str) else json.dumps(doc, ensure_ascii=False),
                 encoding="utf-8")
    return p


def valid_doc(**over) -> dict:
    doc = {
        "version": "2026-10-23.1",
        "effective_from": "2026-10-23",
        "profiles": [{
            "route_id": "CN->US-WEST", "warehouse": "美中-FZH-DANEEY", "mode": "slow_boat",
            "segments": {"order_to_departure": 14, "departure_to_arrival": 30,
                         "arrival_to_stock": 7},
            "source": "assumed", "sample_size": 0, "owner": "business",
            "notes": "示例",
        }],
    }
    doc.update(over)
    return doc


# ---- 1. normal read -------------------------------------------------------

def test_sample_config_loads():
    cfg = lt.load_config(SAMPLE)
    assert cfg.version == "2026-10-23.0-SAMPLE"
    assert cfg.effective_from == date(2026, 10, 23)
    assert len(cfg.profiles) == 6
    assert {p.mode for p in cfg.profiles} == {"slow_boat", "fast_boat", "air", "3pl"}


def test_sample_is_labelled_assumed_zero_sample_business():
    """Requirement 5 is enforced mechanically, not by convention."""
    cfg = lt.load_config(SAMPLE)
    for p in cfg.profiles:
        assert p.source == "assumed"
        assert p.sample_size == 0
        assert p.owner == "business"
        assert "不是业务已批准参数" in p.notes


def test_unknown_fields_are_kept_as_warnings_not_errors():
    doc = valid_doc()
    doc["profiles"][0]["future_field"] = 1
    doc["top_future"] = True
    with tempfile.TemporaryDirectory() as tmp:
        cfg = lt.load_config(write(Path(tmp), doc))
    assert any("future_field" in w for w in cfg.warnings)
    assert any("top_future" in w for w in cfg.warnings)


# ---- 2. file missing ------------------------------------------------------

def test_missing_file_raises_config_not_found():
    try:
        lt.load_config(SAMPLE.parent / "does-not-exist.json")
    except lt.ConfigNotFound as exc:
        assert "不存在" in str(exc) and "不回退" in str(exc)
    else:
        raise AssertionError("missing file did not raise")


def test_missing_path_argument_is_a_type_error():
    try:
        lt.load_config(None)  # type: ignore[arg-type]
    except TypeError:
        pass
    else:
        raise AssertionError("None path did not raise")


# ---- 3. missing / invalid fields -----------------------------------------

def _expect(exc_type, doc=None, **kw):
    with tempfile.TemporaryDirectory() as tmp:
        path = write(Path(tmp), doc if doc is not None else valid_doc(**kw))
        try:
            lt.load_config(path)
        except exc_type as exc:
            return exc
    raise AssertionError(f"{exc_type.__name__} not raised")


def test_missing_top_level_version_names_the_field():
    doc = valid_doc()
    del doc["version"]
    exc = _expect(lt.ConfigSchemaError, doc)
    assert exc.field == "version"


def test_missing_profiles_names_the_field():
    doc = valid_doc()
    del doc["profiles"]
    exc = _expect(lt.ConfigSchemaError, doc)
    assert exc.field == "profiles"


def test_empty_profiles_rejected():
    exc = _expect(lt.ConfigSchemaError, valid_doc(profiles=[]))
    assert exc.field == "profiles"


def test_missing_profile_field_names_the_path():
    doc = valid_doc()
    del doc["profiles"][0]["segments"]
    exc = _expect(lt.ConfigSchemaError, doc)
    assert exc.field == "profiles[0].segments"


def test_missing_segment_key_names_the_path():
    doc = valid_doc()
    del doc["profiles"][0]["segments"]["arrival_to_stock"]
    exc = _expect(lt.ConfigSchemaError, doc)
    assert exc.field == "profiles[0].segments.arrival_to_stock"


def test_missing_notes_rejected():
    doc = valid_doc()
    del doc["profiles"][0]["notes"]
    exc = _expect(lt.ConfigSchemaError, doc)
    assert exc.field == "profiles[0].notes"


def test_negative_segment_rejected():
    doc = valid_doc()
    doc["profiles"][0]["segments"]["arrival_to_stock"] = -1
    exc = _expect(lt.ConfigSchemaError, doc)
    assert exc.field == "profiles[0].segments.arrival_to_stock"


def test_measured_with_zero_sample_rejected():
    doc = valid_doc()
    doc["profiles"][0]["source"] = "measured"
    doc["profiles"][0]["sample_size"] = 0
    exc = _expect(lt.ConfigSchemaError, doc)
    assert "measured" in str(exc)


def test_duplicate_profile_key_rejected():
    doc = valid_doc()
    doc["profiles"].append(json.loads(json.dumps(doc["profiles"][0])))
    exc = _expect(lt.ConfigSchemaError, doc)
    assert "重复" in str(exc)


def test_bad_json_is_a_parse_error():
    exc = _expect(lt.ConfigParseError, "{not json")
    assert "JSON" in str(exc)


# ---- 4. invalid mode ------------------------------------------------------

def test_invalid_mode_in_config_lists_allowed_values():
    doc = valid_doc()
    doc["profiles"][0]["mode"] = "sea"
    exc = _expect(lt.ConfigSchemaError, doc)
    assert exc.field == "profiles[0].mode" and "slow_boat" in str(exc)


def test_invalid_mode_at_call_time_is_explicit():
    cfg = lt.load_config(SAMPLE)
    try:
        cfg.expected_available_date("CN->US-WEST", "rocket", date(2026, 10, 24))
    except lt.ConfigSchemaError as exc:
        assert exc.field == "mode"
    else:
        raise AssertionError("invalid mode did not raise")


# ---- 5. version handling --------------------------------------------------

def test_version_mismatch_raises():
    with tempfile.TemporaryDirectory() as tmp:
        path = write(Path(tmp), valid_doc())
        try:
            lt.load_config(path, expected_version="2026-01-01.1")
        except lt.ConfigVersionError as exc:
            assert "版本不匹配" in str(exc)
        else:
            raise AssertionError("version mismatch did not raise")


def test_malformed_version_raises():
    exc = _expect(lt.ConfigVersionError, valid_doc(version="v1"))
    assert "格式" in str(exc)


def test_config_not_effective_before_effective_from():
    with tempfile.TemporaryDirectory() as tmp:
        path = write(Path(tmp), valid_doc(effective_from="2026-12-01"))
        try:
            lt.load_config(path, as_of=date(2026, 10, 23))
        except lt.ConfigNotEffective as exc:
            assert "2026-12-01" in str(exc)
        else:
            raise AssertionError("future effective_from did not raise")


def test_order_date_before_effective_from_raises():
    cfg = lt.load_config(SAMPLE)                       # effective 2026-10-23
    try:
        cfg.expected_available_date("CN->US-WEST", "slow_boat", date(2026, 10, 1))
    except lt.ConfigNotEffective as exc:
        assert "不做追溯回算" in str(exc)
    else:
        raise AssertionError("backdated order did not raise")


# ---- 6. calculation -------------------------------------------------------

def test_calc_returns_dates_and_carries_source():
    cfg = lt.load_config(SAMPLE)
    av = cfg.expected_available_date("CN->US-WEST", "slow_boat", date(2026, 10, 24))
    # 14 + 30 + 7 = 51 calendar days
    assert av.departure_date == date(2026, 11, 7)
    assert av.arrival_date == date(2026, 12, 7)
    assert av.available_date == date(2026, 12, 14)
    assert av.total_days == 51
    assert av.source == "assumed" and av.is_assumed and not av.is_measured
    assert av.version == cfg.version
    assert av.sample_size == 0
    assert "source=assumed" in av.explain() and cfg.version in av.explain()


def test_all_modes_differ():
    cfg = lt.load_config(SAMPLE)
    days = {m: cfg.expected_available_date("CN->US-WEST", m, date(2026, 10, 24)).total_days
            for m in ("slow_boat", "fast_boat", "air", "3pl")}
    assert days == {"slow_boat": 51, "fast_boat": 33, "air": 12, "3pl": 10}


def test_unknown_route_never_defaults():
    cfg = lt.load_config(SAMPLE)
    try:
        cfg.expected_available_date("CN->MARS", "slow_boat", date(2026, 10, 24))
    except lt.UnknownRoute as exc:
        assert "不回退" in str(exc)
    else:
        raise AssertionError("unknown route did not raise")


def test_unknown_warehouse_never_defaults():
    cfg = lt.load_config(SAMPLE)
    try:
        cfg.expected_available_date("CN->US-WEST", "slow_boat", date(2026, 10, 24),
                                    warehouse="不存在的仓")
    except lt.UnknownRoute:
        pass
    else:
        raise AssertionError("unknown warehouse did not raise")


def test_ambiguous_route_requires_warehouse():
    doc = valid_doc()
    second = json.loads(json.dumps(doc["profiles"][0]))
    second["warehouse"] = "美东-CENTRADE"
    doc["profiles"].append(second)
    with tempfile.TemporaryDirectory() as tmp:
        cfg = lt.load_config(write(Path(tmp), doc))
    try:
        cfg.expected_available_date("CN->US-WEST", "slow_boat", date(2026, 10, 24))
    except lt.ConfigAmbiguous as exc:
        assert "warehouse" in str(exc)
    else:
        raise AssertionError("ambiguous route did not raise")
    av = cfg.expected_available_date("CN->US-WEST", "slow_boat", date(2026, 10, 24),
                                     warehouse="美东-CENTRADE")
    assert av.warehouse == "美东-CENTRADE"


def test_order_date_must_be_a_date():
    cfg = lt.load_config(SAMPLE)
    try:
        cfg.expected_available_date("CN->US-WEST", "slow_boat", "2026-10-24")  # type: ignore[arg-type]
    except lt.ConfigSchemaError as exc:
        assert exc.field == "order_date"
    else:
        raise AssertionError("string order date did not raise")


if __name__ == "__main__":
    failed = 0
    for name, fnc in sorted(globals().items()):
        if name.startswith("test_") and callable(fnc):
            try:
                fnc()
                print(f"PASS {name}")
            except AssertionError as exc:
                failed += 1
                print(f"FAIL {name}: {exc}")
    print(f"\n{'ALL PASS' if failed == 0 else f'{failed} FAILED'}")
    sys.exit(1 if failed else 0)
