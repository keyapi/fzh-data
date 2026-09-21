"""catalog 完整性 + 与 AGENTS.md 模块索引的防漂移断言。

这一组是「人读的索引」与「机读的目录」不脱节的唯一保证。
"""

from __future__ import annotations

import pytest
import yaml

from intent_router.catalog import (
    CATALOG_PATH,
    find_agents_md,
    load_catalog,
    parse_agents_md_modules,
)

CATALOG = load_catalog()
AGENTS_MD = find_agents_md()


def test_agents_md_is_findable():
    assert AGENTS_MD is not None and AGENTS_MD.is_file()


def test_parser_finds_a_plausible_number_of_modules():
    declared = parse_agents_md_modules(AGENTS_MD)
    assert len(declared) >= 30
    assert "item-cost" in declared and "stock-init" in declared


def test_catalog_skill_set_equals_agents_md_table():
    declared = parse_agents_md_modules(AGENTS_MD)
    in_catalog = set(CATALOG.skills)
    assert declared == in_catalog, (
        f"只在 AGENTS.md 里：{sorted(declared - in_catalog)}；"
        f"只在 catalog 里：{sorted(in_catalog - declared)}"
    )


def test_catalog_never_defines_none_option():
    assert "none" not in CATALOG.skills
    raw = yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8"))
    assert all(option["skill"] != "none" for option in raw["options"])


def test_no_duplicate_skills():
    assert len(CATALOG.skills) == len(set(CATALOG.skills))


@pytest.mark.parametrize("option", CATALOG.options, ids=lambda option: option["skill"])
def test_every_entry_is_usable(option):
    assert option["coverage"].strip()
    assert option["exclusions"].strip()
    assert option.get("summary", "").strip()
    examples = option.get("examples")
    assert isinstance(examples, list) and examples, f"{option['skill']} 缺 examples"
    assert all(isinstance(example, str) and example.strip() for example in examples)


@pytest.mark.parametrize("option", CATALOG.options, ids=lambda option: option["skill"])
def test_directory_exists_or_entry_is_external(option):
    directory = option.get("dir")
    if option.get("external"):
        assert directory is None, f"{option['skill']} 标了 external 却给了目录"
        return
    assert directory, f"{option['skill']} 缺 dir"
    assert (AGENTS_MD.parent / directory).is_dir(), f"{option['skill']} 的目录不存在：{directory}"


@pytest.mark.parametrize("option", CATALOG.options, ids=lambda option: option["skill"])
def test_web_task_points_at_a_real_capability(option):
    capability_id = option.get("web_task")
    if not capability_id:
        return
    capabilities_path = AGENTS_MD.parent / "web_automation" / "capabilities.yaml"
    text = capabilities_path.read_text(encoding="utf-8")
    assert f"{capability_id}:" in text, f"{option['skill']} 的 web_task 不存在：{capability_id}"


def test_option_for_lookup():
    assert CATALOG.option_for("item-cost")["dir"] == "item_cost_sx/"
    assert CATALOG.option_for("nope") is None
    assert CATALOG.option_for(None) is None


def test_load_catalog_rejects_none_option(tmp_path):
    path = tmp_path / "catalog.yaml"
    path.write_text(
        "version: 1\nmodel: jev-latest\noptions:\n  - skill: none\n    coverage: c\n    exclusions: e\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="none"):
        load_catalog(path)


def test_load_catalog_rejects_missing_required_field(tmp_path):
    path = tmp_path / "catalog.yaml"
    path.write_text(
        "version: 1\nmodel: jev-latest\noptions:\n  - skill: foo\n    coverage: c\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="exclusions"):
        load_catalog(path)


def test_load_catalog_rejects_duplicate_skills(tmp_path):
    path = tmp_path / "catalog.yaml"
    path.write_text(
        "version: 1\nmodel: jev-latest\noptions:\n"
        "  - skill: foo\n    coverage: c\n    exclusions: e\n"
        "  - skill: foo\n    coverage: c\n    exclusions: e\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="重复"):
        load_catalog(path)


def test_load_catalog_rejects_bad_structure(tmp_path):
    path = tmp_path / "catalog.yaml"
    path.write_text("version: 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="结构"):
        load_catalog(path)
