#!/usr/bin/env python3
"""Knowledge-base health check for docs/solutions/ (orphans, index drift, links).

Proven method: build a reverse-reference graph and flag artefacts with zero inbound
references ("orphan detection"), cross-check every generated index against disk, and
resolve every intra-repo link. Orphans that legitimately should not be routed from a
skill go into docs/solutions/exclusions.txt instead of being ignored.

Usage:
  python scripts/check_solutions_health.py            # full report; exit 1 on hard errors
  python scripts/check_solutions_health.py --strict   # orphans also fail the run
  python scripts/check_solutions_health.py --json     # machine-readable
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOL = ROOT / "docs" / "solutions"
EXCLUSIONS = SOL / "exclusions.txt"
AGENTS = ROOT / "AGENTS.md"

# 这些是"目录/清单"性质的文件，不算正文，也不参与孤儿判定
INDEX_NAMES = {"index.md", "log.md"}


def rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


def solution_docs() -> list[Path]:
    return sorted(
        p for p in SOL.rglob("*.md")
        if p.name not in INDEX_NAMES and p.parent != SOL.parent
    )


def category_dirs() -> list[Path]:
    return sorted(p for p in SOL.iterdir() if p.is_dir())


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def frontmatter(text: str) -> dict[str, str]:
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        mm = re.match(r"^([a-z_]+):\s*(.*)$", line)
        if mm:
            out[mm.group(1)] = mm.group(2).strip().strip('"').strip("'")
    return out


def reference_sources() -> list[Path]:
    """会"引用"解决方案文档的文本源 —— 只取 docs/solutions 之外的"路径上"文件。

    判断的是"Agent 顺着正常路径（AGENTS.md → skill → 模块文档）会不会落到这篇"。
    因此排除三类：
      - docs/solutions 自身（内部互链不构成路径：从孤儿链过去，两个都找不到）
      - 自动生成的清单（根 index.md / 各处 log.md —— 它们提到每一篇，会把孤儿数压成 0）
      - 第三方文档镜像（SELLFOX_API 等都是 450+ 篇的导入件，不是我们的知识）
    """
    skip_dirs = {"SELLFOX_API", "vite-api", "yiglobal-api", "sps_api"}
    src = [AGENTS, ROOT / "CONCEPTS.md", ROOT / "CONTRIBUTING.md"]
    src += sorted(p for p in (ROOT / "docs").rglob("*.md") if SOL not in p.parents)
    src += sorted((ROOT / ".agents" / "skills").rglob("SKILL.md"))
    src += sorted(ROOT.glob("*/AGENT_HANDOFF.md"))
    src += sorted(ROOT.glob("*/README.md"))
    src += sorted(ROOT.glob("*/docs/**/*.md"))
    out = []
    for p in src:
        if not p.is_file() or SOL in p.parents:
            continue
        if p.name == "log.md" or p == ROOT / "index.md":
            continue
        if skip_dirs & set(p.relative_to(ROOT).parts):
            continue
        out.append(p)
    return out


def load_exclusions() -> dict[str, str]:
    """docs/solutions/exclusions.txt: `<路径>  # 原因`，一行一条。"""
    if not EXCLUSIONS.is_file():
        return {}
    out = {}
    for line in read(EXCLUSIONS).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        path, _, why = line.partition("#")
        out[path.strip().replace("\\", "/")] = why.strip()
    return out


def check_orphans(docs: list[Path]) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """返回 (未豁免的孤儿, 已豁免的孤儿)。入链判定：正文里出现该文档的文件名或仓库相对路径。"""
    corpus = []
    for p in reference_sources():
        if p.name in INDEX_NAMES and SOL in p.parents:
            continue  # 自动清单不算入链
        try:
            corpus.append((rel(p), read(p)))
        except OSError:
            pass
    excl = load_exclusions()
    orphans, exempted = [], []
    for d in docs:
        name = d.name
        path = rel(d)
        hit = None
        for src, text in corpus:
            if src == path:
                continue
            if name in text or path in text:
                hit = src
                break
        fm = frontmatter(read(d))
        entry = (path, fm.get("title", name))
        if hit:
            continue
        if path in excl or name in excl:
            exempted.append((path, excl.get(path, excl.get(name, ""))))
        else:
            orphans.append(entry)
    return orphans, exempted


def check_category_indexes() -> list[str]:
    """每个 category 的 index.md 必须列出该目录下所有正文文档，且不列不存在的东西。"""
    errs = []
    for cat in category_dirs():
        docs = sorted(p.name for p in cat.glob("*.md") if p.name not in INDEX_NAMES)
        idx = cat / "index.md"
        if not idx.is_file():
            errs.append(f"{rel(cat)}/ 缺 index.md（OKF 第 10 条要求每个目录都有）")
            continue
        text = read(idx)
        missing = [n for n in docs if n not in text]
        if missing:
            errs.append(f"{rel(idx)} 未收录 {len(missing)} 篇：{missing[:4]}")
    return errs


DATE_KEYS = ("date", "created", "timestamp")
STANDARD_KEYS = ("okf", "type", "title", "date", "module", "tags", "problem_type", "component", "severity")


def doc_date(fm: dict[str, str]) -> str:
    """日期键历史上出现过 date / created / timestamp 三种；生成索引时兼容，
    但非标准写法会在体检里报出来（见 check_frontmatter_keys）。"""
    for k in DATE_KEYS:
        if fm.get(k):
            return fm[k]
    return "0000-00-00"


def check_frontmatter_keys() -> list[str]:
    """列出用了非标准日期键的文档 —— 不阻塞，但要让它们可见。"""
    bad = []
    for d in solution_docs():
        fm = frontmatter(read(d))
        if not fm.get("date") and any(fm.get(k) for k in ("created", "timestamp")):
            key = "created" if fm.get("created") else "timestamp"
            bad.append(f"{rel(d)}（用 `{key}:`，规范是 `date:`）")
    return bad


def master_index_content(docs: list[Path]) -> str:
    """主平表 docs/solutions/index.md 由 frontmatter 生成 —— 手工维护必漂（实测漂了 30 篇）。"""
    rows = []
    for d in docs:
        fm = frontmatter(read(d))
        rows.append((doc_date(fm), fm.get("title", d.name), rel(d).replace("docs/solutions/", "")))
    rows.sort(key=lambda r: (r[0], r[1]), reverse=True)
    out = [
        "---", "okf: v0.1", "type: Index", "title: 解决方案",
        "description: 已解决问题的记录索引（由 scripts/check_solutions_health.py --fix 生成，勿手改）",
        "tags: [solutions, index]", "---", "",
        "# 解决方案", "",
        "> 由 `scripts/check_solutions_health.py --fix` 生成，勿手改。按日期倒序。",
        "> 按类别浏览见各 `docs/solutions/<category>/index.md`。", "",
        "| 日期 | 标题 | 文件 |", "|------|------|------|",
    ]
    out += [f"| {dt} | {ti} | [{p}]({p}) |" for dt, ti, p in rows]
    return "\n".join(out) + "\n"


def check_master_index(docs: list[Path]) -> list[str]:
    idx = SOL / "index.md"
    if not idx.is_file():
        return ["docs/solutions/index.md 不存在（用 --fix 生成）"]
    text = read(idx)
    missing = [rel(p) for p in docs if p.name not in text]
    return [f"docs/solutions/index.md 未收录 {len(missing)} 篇：{missing[:4]}"] if missing else []


def check_loose_docs() -> list[str]:
    """docs/solutions 根下不该有正文（应归入某个 category）。"""
    loose = sorted(p.name for p in SOL.glob("*.md") if p.name not in INDEX_NAMES)
    return [f"docs/solutions/ 根下有 {len(loose)} 篇未归类的正文：{loose}"] if loose else []



def check_agents_counts() -> list[str]:
    """AGENTS.md「经验库路由」表里的篇数必须与磁盘一致。"""
    if not AGENTS.is_file():
        return []
    text = read(AGENTS)
    errs = []
    for cat in category_dirs():
        n = len([p for p in cat.glob("*.md") if p.name not in INDEX_NAMES])
        m = re.search(rf"`{re.escape(cat.name)}/`\s*\|\s*(\d+)", text)
        if m and int(m.group(1)) != n:
            errs.append(f"AGENTS.md 里 {cat.name}/ 写的是 {m.group(1)} 篇，磁盘是 {n} 篇")
    return errs


def check_links() -> list[str]:
    """docs/solutions 内部的相对 markdown 链接必须能解析。"""
    errs = []
    for p in list(SOL.rglob("*.md")):
        for text, target in re.findall(r"\[([^\]]+)\]\(([^)#\s]+)\)", read(p)):
            if "://" in target or target.startswith("mailto:"):
                continue
            dest = (p.parent / target).resolve()
            if not dest.exists():
                errs.append(f"{rel(p)} → `{target}` 解析不到")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser(description="docs/solutions 知识库体检")
    ap.add_argument("--strict", action="store_true", help="孤儿也算失败")
    ap.add_argument("--fix", action="store_true", help="重建主平表 docs/solutions/index.md 后再体检")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    docs = solution_docs()
    if args.fix:
        (SOL / "index.md").write_text(master_index_content(docs), encoding="utf-8")
        print(f"已重建 docs/solutions/index.md（{len(docs)} 篇）\n")

    orphans, exempted = check_orphans(docs)
    hard = {
        "category index 与磁盘不一致": check_category_indexes(),
        "全量平表缺文档": check_master_index(docs),
        "有正文游离在 docs/solutions 根下": check_loose_docs(),
        "AGENTS.md 分类表篇数漂移": check_agents_counts(),
        "相对链接解析不到": check_links(),
    }
    hard = {k: v for k, v in hard.items() if v}

    if args.json:
        print(json.dumps({
            "total_docs": len(docs),
            "orphans": [{"path": p, "title": t} for p, t in orphans],
            "exempted": [{"path": p, "reason": r} for p, r in exempted],
            "hard_errors": hard,
        }, ensure_ascii=False, indent=2))
    else:
        print(f"docs/solutions 体检：{len(docs)} 篇正文 / {len(category_dirs())} 个 category\n")
        for title, errs in hard.items():
            print(f"[FAIL] {title}")
            for e in errs:
                print(f"       - {e}")
        if not hard:
            print("[ OK ] 索引、平表、AGENTS.md 篇数、相对链接：全部一致\n")
        print(f"[ {'FAIL' if orphans and args.strict else 'WARN'} ] 孤儿文档（无任何入链，仅被自动索引收录）：{len(orphans)} 篇")
        for p, t in orphans:
            print(f"       - {p}  —  {t[:44]}")
        if orphans:
            print(f"       处理：挂到相关 skill / AGENT_HANDOFF（route，别复制内容），"
                  f"或写进 {rel(EXCLUSIONS)} 豁免")
        print(f"[ OK ] 已豁免（{rel(EXCLUSIONS)}）：{len(exempted)} 篇")
        for p, r in exempted:
            print(f"       - {p}  —  {r[:44]}")
        odd = check_frontmatter_keys()
        print(f"[ {'WARN' if odd else 'OK'} ] frontmatter 日期键非标准（规范是 `date:`）：{len(odd)} 篇")
        for b in odd:
            print(f"       - {b}")

    failed = bool(hard) or (args.strict and bool(orphans))
    if not args.json:
        print("\n结论：" + ("不通过" if failed else "通过"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
