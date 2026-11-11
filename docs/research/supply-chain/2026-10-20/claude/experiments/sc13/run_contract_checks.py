#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SC13 contract evidence run: prove each failure mode raises a NAMED error.

Writes `out/business_phase/sc13/sc13_contract_checks.json` — one row per case
with the exception class and the message the caller would actually see, plus a
positive table (route x mode -> dates) computed from the sample config.

This is evidence, not a test suite: the assertions live in
`test_leadtime_config.py`. Run:
  uv run python docs/research/supply-chain/2026-10-20/claude/experiments/sc13/run_contract_checks.py
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import leadtime_config as lt  # noqa: E402

HERE = Path(__file__).resolve().parent
BP = HERE.parents[1] / "out" / "business_phase"
OUT = BP / "sc13"
SAMPLE = HERE / "examples" / "leadtime_config.sample.json"
REPO = next((p for p in HERE.parents if (p / ".git").exists()), HERE)


def sanitize(text: str) -> str:
    """Keep local absolute paths (repo root, OS temp / user profile) out of the evidence file."""
    text = text.replace("\\", "/")
    for prefix in (str(REPO), tempfile.gettempdir(), str(Path.home())):
        text = text.replace(prefix.replace("\\", "/"), "<local>")
    return re.sub(r"/tmp[a-z0-9_]{5,}/", "/<tmp>/", text, flags=re.IGNORECASE)


def base_doc() -> dict:
    return {
        "version": "2026-10-23.1", "effective_from": "2026-10-23",
        "profiles": [{
            "route_id": "CN->US-WEST", "warehouse": "美中-FZH-DANEEY", "mode": "slow_boat",
            "segments": {"order_to_departure": 14, "departure_to_arrival": 30,
                         "arrival_to_stock": 7},
            "source": "assumed", "sample_size": 0, "owner": "business", "notes": "示例",
        }],
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cases, rows = [], []

    def run(case: str, fn, expect: type[Exception]) -> dict:
        try:
            fn()
        except expect as exc:
            return dict(case=case, expected=expect.__name__, raised=type(exc).__name__,
                        message=sanitize(str(exc)), named_error=type(exc) is expect)
        except Exception as exc:                    # noqa: BLE001 - evidence run
            return dict(case=case, expected=expect.__name__, raised=type(exc).__name__,
                        message=sanitize(str(exc)), named_error=False)
        return dict(case=case, expected=expect.__name__, raised=None,
                    message="未报错（违反契约）", named_error=False)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        def doc_with(mutator, name: str = "cfg.json") -> Path:
            doc = base_doc()
            mutator(doc)
            p = tmp / name
            p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
            return p

        def raw(text: str) -> Path:
            p = tmp / "raw_bad.json"
            p.write_text(text, encoding="utf-8")
            return p

        cases.append(run("文件缺失", lambda: lt.load_config(OUT / "nope.json"), lt.ConfigNotFound))
        cases.append(run("非法 JSON", lambda: lt.load_config(raw("{oops")), lt.ConfigParseError))
        cases.append(run("缺 version",
                         lambda: lt.load_config(doc_with(lambda d: d.pop("version"))),
                         lt.ConfigSchemaError))
        cases.append(run("缺 segments",
                         lambda: lt.load_config(doc_with(lambda d: d["profiles"][0].pop("segments"))),
                         lt.ConfigSchemaError))
        cases.append(run("非法 mode",
                         lambda: lt.load_config(doc_with(
                             lambda d: d["profiles"][0].__setitem__("mode", "sea"))),
                         lt.ConfigSchemaError))
        cases.append(run("版本格式非法",
                         lambda: lt.load_config(doc_with(
                             lambda d: d.__setitem__("version", "v1"))), lt.ConfigVersionError))
        cases.append(run("版本不匹配",
                         lambda: lt.load_config(SAMPLE, expected_version="2026-01-01.1"),
                         lt.ConfigVersionError))
        cases.append(run("生效日晚于请求日",
                         lambda: lt.load_config(doc_with(
                             lambda d: d.__setitem__("effective_from", "2026-12-01")),
                             as_of=date(2026, 10, 23)), lt.ConfigNotEffective))
        cases.append(run("measured 但样本为 0",
                         lambda: lt.load_config(doc_with(
                             lambda d: d["profiles"][0].update({"source": "measured"}))),
                         lt.ConfigSchemaError))
        cases.append(run("重复 profile",
                         lambda: lt.load_config(doc_with(
                             lambda d: d["profiles"].append(
                                 json.loads(json.dumps(d["profiles"][0]))))),
                         lt.ConfigSchemaError))

        cfg = lt.load_config(SAMPLE)
        cases.append(run("未知 route（不回退）",
                         lambda: cfg.expected_available_date("CN->MARS", "slow_boat",
                                                             date(2026, 10, 24)),
                         lt.UnknownRoute))
        cases.append(run("下单日早于生效日",
                         lambda: cfg.expected_available_date("CN->US-WEST", "slow_boat",
                                                             date(2026, 10, 1)),
                         lt.ConfigNotEffective))

        amb_cfg = lt.load_config(doc_with(
            lambda d: d["profiles"].append(
                {**json.loads(json.dumps(d["profiles"][0])), "warehouse": "美东-CENTRADE"}),
            name="ambiguous.json"))
        cases.append(run("同 route+mode 多仓未指定 warehouse",
                         lambda: amb_cfg.expected_available_date("CN->US-WEST", "slow_boat",
                                                                 date(2026, 10, 24)),
                         lt.ConfigAmbiguous))

    # positive: the dates a caller would actually get
    for route in ("CN->US-WEST", "CN->PL"):
        for mode in lt.MODES:
            try:
                av = cfg.expected_available_date(route, mode, date(2026, 10, 24))
            except lt.UnknownRoute:
                rows.append(dict(route=route, mode=mode, in_config=False))
                continue
            rows.append(dict(route=route, mode=mode, in_config=True,
                             warehouse=av.warehouse,
                             segments=dict(av.segments),
                             total_days=av.total_days,
                             departure=av.departure_date.isoformat(),
                             arrival=av.arrival_date.isoformat(),
                             available=av.available_date.isoformat(),
                             source=av.source, sample_size=av.sample_size,
                             version=av.version, explain=sanitize(av.explain())))

    evidence = dict(
        schema_version="sc13_contract_checks/1",
        sample_config="experiments/sc13/examples/leadtime_config.sample.json",
        sample_version=cfg.version,
        sample_profiles=len(cfg.profiles),
        warnings=list(cfg.warnings),
        negative_cases=cases,
        all_named_errors=all(c["named_error"] for c in cases),
        positive_orders=rows,
        day_basis="calendar_days",
    )
    (OUT / "sc13_contract_checks.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "sc13_contract_report.md").write_text(render_report(evidence), encoding="utf-8")
    print(json.dumps(dict(cases=len(cases), all_named=evidence["all_named_errors"],
                          profiles=len(cfg.profiles), sample_version=cfg.version),
                     ensure_ascii=False))


def render_report(ev: dict) -> str:
    L = ["---\nokf: v0.1\ntype: Report\n"
         "title: SC13 交期/运输方式配置的消费端契约\n"
         f"date: {date.today().isoformat()}\n"
         "owner: claude-worker-1\n"
         "status: 我方契约已实现（loader + 计算 + 单测 + 示例），等 Jack W2 换文件即可\n"
         "artifacts:\n"
         "  - experiments/sc13/leadtime_config.py\n"
         "  - experiments/sc13/test_leadtime_config.py\n"
         "  - experiments/sc13/run_contract_checks.py\n"
         "  - experiments/sc13/examples/leadtime_config.sample.json\n"
         "  - out/business_phase/sc13/sc13_contract_checks.json\n---\n",
         "# SC13 消费端契约：交期 / 运输方式配置\n",
         "> **一句话**：我们这侧的读取器已经按契约实现——**缺文件、缺字段、版本不对、"
         "route/mode 不在配置里，一律抛具名错误，绝不回退到硬编码天数**；示例配置明确标 "
         "`source=assumed / sample_size=0 / owner=business`，等 Jack 的 W2 真配置到位后"
         "**只换文件、调用方不改**。\n",
         "## 0. 契约边界\n",
         "- Jack 产出版本化 JSON（route × warehouse × mode × 分段天数）；**我们只消费，不生产**。",
         "- 本模块不做预测、不出补货量、不算库存；只回答「这个 route+mode，今天下单，何时可用」。",
         "- **未改 SC08 评估器**；未来把 SC08 里单一的 `L` 换成 "
         "`cfg.expected_available_date(...)` 即可，接入点留白。\n",
         "## 1. Schema 与校验规则\n",
         "| 层级 | 字段 | 规则 |\n|---|---|---|",
         "| 顶层 | `version` | 必填，`YYYY-MM-DD[.N][-SUFFIX]`；可与调用方 `expected_version` 比对 |",
         "| 顶层 | `effective_from` | 必填，ISO 日期；晚于请求日/下单日则报 `ConfigNotEffective` |",
         "| 顶层 | `profiles[]` | 必填，非空列表 |",
         "| profile | `route_id` / `warehouse` | 必填非空字符串；`warehouse` 与库存口径同名 |",
         "| profile | `mode` | 必填，`slow_boat` / `fast_boat` / `air` / `3pl` |",
         "| profile | `segments` | 必填对象，三个字段均为 `>= 0` 的数字 |",
         "| profile | `source` | 必填，`measured` / `assumed` / `business` |",
         "| profile | `sample_size` | 必填整数 `>= 0`；**`measured` 时必须 > 0** |",
         "| profile | `owner` / `notes` | 必填，非空字符串 / 字符串 |",
         "",
         "> 未知字段不报错但记入 `warnings`（向前兼容 Jack 加字段）；已知字段缺失或非法一律报错。"
         "同一 `(route_id, warehouse, mode)` 重复即报错（重复 = 歧义）。\n",
         "## 2. 错误契约（全部具名，绝不静默默认）\n",
         "实测证据：`sc13_contract_checks.json`，"
         f"{len(ev['negative_cases'])} 个失败用例全部抛出具名异常："
         f"{'✅' if ev['all_named_errors'] else '❌'}。\n",
         "| 用例 | 期望异常 | 实际 | 消息（节选） |\n|---|---|---|---|"]
    for c in ev["negative_cases"]:
        msg = c["message"].replace("|", "\\|")[:78]
        L.append(f"| {c['case']} | `{c['expected']}` | {('`' + c['raised'] + '`') if c['raised'] else '**未报错**'} | {msg} |")
    L += ["",
          "异常层级：`LeadTimeConfigError` ← `ConfigNotFound` / `ConfigParseError` / "
          "`ConfigSchemaError`（带 `.field` 路径）/ `ConfigVersionError` / `ConfigNotEffective` / "
          "`UnknownRoute` / `ConfigAmbiguous`。调用方可以整体捕获基类，也可以按需精确处理。\n",
          "## 3. 计算语义\n",
          "- **自然日**（calendar days）：`可用日 = 下单日 + 三段天数`；这一点需与业务/Jack 书面确认"
          "（若改为工作日，契约要升版）。",
          "- 返回的 `Availability` 同时带回 `source / sample_size / owner / notes / version / "
          "effective_from`；`is_assumed` 为 True 时调用方必须显式处理（不得当实测用）。",
          "- `explain()` 给出一行可直接写进决策的出处说明（含版本与来源）。",
          "- **不做追溯回算**：下单日早于 `effective_from` 直接报错。\n",
          "示例（示例配置，非业务参数）：\n",
          "| route | mode | 三段天数 | 合计 | 下单 2026-10-24 → 可用 | source |",
          "|---|---|---|---:|---|---|"]
    for r in ev["positive_orders"]:
        if not r.get("in_config"):
            L.append(f"| {r['route']} | {r['mode']} | — | — | 不在示例配置中（应报 UnknownRoute） | — |")
            continue
        seg = "/".join(str(int(v)) if float(v).is_integer() else f"{v:g}"
                       for v in r["segments"].values())
        L.append(f"| {r['route']} | {r['mode']} | {seg} | {r['total_days']:g} | "
                 f"{r['available']} | {r['source']} |")
    L += ["",
          "## 4. 示例配置的声明\n",
          f"- 文件：`experiments/sc13/examples/leadtime_config.sample.json`，"
          f"版本 `{ev['sample_version']}`，{ev['sample_profiles']} 个 profile。",
          "- **这是示例，不是业务已批准参数**：每个 profile 都写死 "
          "`source=assumed`、`sample_size=0`、`owner=business`，`notes` 里重复该声明；"
          "单测 `test_sample_is_labelled_assumed_zero_sample_business` 机械校验这四条。",
          "- 版本号带 `-SAMPLE` 后缀，`explain()` 会把版本打出来，日志里一眼可辨。\n",
          "## 5. Jack W2 到位后怎么换（调用方零改动）\n",
          "1. 把 Jack 的 JSON 放到任意路径（建议 `configs/leadtime/<version>.json`），"
          "调用方 `load_config(path, expected_version=\"<W2 的 version>\")`。",
          "2. 加载即校验：缺字段/版本不符/重复键当场报错；`source=measured` 必须带 "
          "`sample_size>0`，否则拒绝（防止把假设伪装成实测）。",
          "3. **调用方一行都不用改**：它只依赖 `route_id + mode + 下单日` 与返回的 "
          "`available_date / source`；天数、版本、生效日都从配置来。",
          "4. 版本与来源要写进决策：`av.explain()` 已含版本与 source；"
          "按交接文档 §5.2 在 `LEAD_TIME_DECISIONS.md` 只追加记录（谁改、为什么、影响哪些 SKU）。",
          "5. 若 Jack 的字段名与契约不同（例如 `route` / `transport_mode`），"
          "在他交付前由我们做一次**显式映射层**（不猜、不模糊匹配），或在契约定版时改名——"
          "两种都要走一次评审，不能靠 loader 猜。\n",
          "## 6. 验收清单（给 W2 交接时用）\n",
          "- [x] 缺文件 → `ConfigNotFound`，不回退默认天数",
          "- [x] 缺字段 → `ConfigSchemaError.field` 精确到 `profiles[i].segments.x`",
          "- [x] 版本格式/版本不匹配 → `ConfigVersionError`",
          "- [x] 非法 mode → 列出允许值",
          "- [x] 未知 route/warehouse → `UnknownRoute`（不猜）",
          "- [x] 多仓歧义 → `ConfigAmbiguous`，要求显式 `warehouse`",
          "- [x] `assumed` 可被调用方识别（`is_assumed` / `source` / `explain()`）",
          "- [x] 示例配置明确标注非业务批准",
          "",
          "## 7. 边界与未决\n",
          "- 只读离线；无生产访问；不改 SC08、不出量、不 commit、不 push。",
          "- **自然日 vs 工作日**：当前按自然日，需业务确认；若改，视为契约升版。",
          "- **route_id 命名**：示例用 `CN->US-WEST` / `CN->PL`，实际以 Jack W2 为准；"
          "映射层或改名需评审。",
          "- 未实现「按 mode 反查可用 mode 列表」等便利方法——调用方需要时再加，"
          "避免超出契约。",
          "",
          "## 8. 复现\n",
          "```bash",
          "uv run python docs/research/supply-chain/2026-10-20/claude/experiments/sc13/test_leadtime_config.py",
          "uv run python docs/research/supply-chain/2026-10-20/claude/experiments/sc13/run_contract_checks.py",
          "```",
          ""]
    return "\n".join(L)


if __name__ == "__main__":
    main()
