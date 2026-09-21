"""读取 catalog.yaml（运行时目录真源），并把 AGENTS.md 的模块索引表解析成集合。

防漂移：运行时不读 AGENTS.md（解析散文太脆），但 tests/test_catalog.py 会断言
catalog.yaml 的 skill 集合与 AGENTS.md 模块索引表的集合完全相等。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

_PKG_DIR = Path(__file__).resolve().parent
CATALOG_PATH = _PKG_DIR / "catalog.yaml"

_SECTION_HEADING = "## 模块索引"
_AGENTS_LEVELS = 6

# 只匹配行首 `skill` | 形式的表格行；兼容 — 目录、{a,b,c} 展开、跨行重复目录
_ROW_RE = re.compile(r"^\|\s*`(?P<skill>[A-Za-z0-9_-]+)`\s*\|")


@dataclass(frozen=True)
class Catalog:
    options: tuple[dict, ...]
    model: str
    version: int

    @property
    def skills(self) -> tuple[str, ...]:
        return tuple(option["skill"] for option in self.options)

    def option_for(self, skill: str | None) -> dict | None:
        if not skill:
            return None
        for option in self.options:
            if option["skill"] == skill:
                return option
        return None


def find_agents_md(start: Path | None = None, *, levels: int = _AGENTS_LEVELS) -> Path | None:
    """就近找 AGENTS.md。worktree 与普通检出里 parents[1] 都是仓库根。"""
    base = (start or _PKG_DIR).resolve()
    for directory in [base, *base.parents[:levels]]:
        candidate = directory / "AGENTS.md"
        if candidate.is_file():
            return candidate
    return None


def parse_agents_md_modules(agents_md: Path) -> set[str]:
    """只扫「## 模块索引」小节，取表格行首反引号包裹的 skill 名。"""
    inside = False
    names: set[str] = set()
    for line in agents_md.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            if inside:
                break
            inside = line.strip() == _SECTION_HEADING
            continue
        if not inside:
            continue
        match = _ROW_RE.match(line)
        if match:
            names.add(match.group("skill"))
    return names


def load_catalog(path: Path | None = None) -> Catalog:
    path = path or CATALOG_PATH
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("options"), list):
        raise ValueError(f"{path} 结构不对：需要 version / model / options 三个字段")

    options: list[dict] = []
    seen: set[str] = set()
    for raw in data["options"]:
        if not isinstance(raw, dict) or not raw.get("skill"):
            raise ValueError(f"{path} 里有一条目缺少 skill 字段")
        skill = raw["skill"]
        if skill == "none":
            raise ValueError(f"{path} 不能定义 none 选项（由 build_payload 追加）")
        if skill in seen:
            raise ValueError(f"{path} 里 skill 重复：{skill}")
        for field in ("coverage", "exclusions"):
            if not raw.get(field):
                raise ValueError(f"{path} 的 {skill} 缺少 {field} 字段")
        seen.add(skill)
        options.append(raw)

    return Catalog(
        options=tuple(options),
        model=str(data.get("model") or "jev-latest"),
        version=int(data.get("version") or 1),
    )


def main(argv: list[str] | None = None) -> int:
    """`python -m intent_router.catalog` —— 打印 catalog 与 AGENTS.md 的差异，供断点排查。"""
    import argparse

    parser = argparse.ArgumentParser(description="检查 catalog.yaml 与 AGENTS.md 模块索引是否同步")
    parser.add_argument("--agents-md", type=Path, default=None)
    args = parser.parse_args(argv)

    catalog = load_catalog()
    agents_md = args.agents_md or find_agents_md()
    if agents_md is None:
        print(f"未找到 AGENTS.md；catalog 里有 {len(catalog.skills)} 个模块")
        return 1

    declared = parse_agents_md_modules(agents_md)
    in_catalog = set(catalog.skills)
    print(f"AGENTS.md：{agents_md}")
    print(f"模块索引表 {len(declared)} 项 / catalog {len(in_catalog)} 项")
    only_declared = sorted(declared - in_catalog)
    only_catalog = sorted(in_catalog - declared)
    if not only_declared and not only_catalog:
        print("两边集合一致")
        return 0
    if only_declared:
        print("只在 AGENTS.md 里（catalog 缺）：" + ", ".join(only_declared))
    if only_catalog:
        print("只在 catalog 里（AGENTS.md 缺）：" + ", ".join(only_catalog))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
