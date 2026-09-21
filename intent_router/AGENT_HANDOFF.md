---
okf: v0.1
type: Handoff
title: intent_router — Agent 交接
description: 中文意图 → 本仓库模块路由的函数表、请求契约、阈值语义与边界条件
updated: 2026-09-21
---

# intent_router — Agent 交接

> 中文意图 → 本仓库模块路由。**入口文档**，需要细节再按下方索引深入。

## 一句话

`route("一句中文请求")` → 模块名 + 目录 + 置信度，或明确告诉你「无法判定」。**不执行任何业务动作。**

## 怎么跑

```bash
uv run python -m intent_router.cli route "<中文请求>" [选项]
uv run python -m intent_router.cli catalog [--json]
python -m intent_router.catalog          # 检查 catalog ↔ AGENTS.md 是否同步
```

| 选项 | 默认 | 含义 |
|------|------|------|
| `--min-confidence` | `0.5` | 低于此值即判「无法判定」 |
| `--model` | `jev-latest` | 覆盖 catalog 里的 model |
| `--timeout` | `60` | 单次请求超时（秒） |
| `--json` | off | 输出完整 RouteResult JSON |
| `--show-candidates` | off | 打印完整候选概率分布 |
| `--env-file` | – | 显式指定 `.env`，替代上溯查找 |
| `--verbose` | off | 把已加载的 `.env` 打到 stderr |

退出码：`0` 命中 · `1` 缺凭证/用法错 · `2` API 错误 · `3` 需人工介入。

### ⚠️ 在 worktree 里不要 `uv run`

会另建一个 `.venv`（见 `parcel_track/AGENT_HANDOFF.md` 同款约定）。用父仓库解释器：

```powershell
$WT = "D:\Work\赛狐\Cursor\.claude\worktrees\<name>"
$env:PYTHONPATH = $WT
& "D:\Work\赛狐\Cursor\.venv\Scripts\python.exe" -m pytest intent_router/tests -q
```

## 函数表

| 文件 | 函数 | 作用 |
|------|------|------|
| `cli.py` | `main(argv=None) -> int` | CLI 入口，返回退出码（测试直调断言退出码） |
| `router.py` | `route(text, *, catalog, api_key, min_confidence=0.5, model=None, timeout=60) -> RouteResult` | 一次完整路由 |
| `router.py` | `call_typesafe(payload, api_key, *, timeout) -> dict` | POST + 退避重试，失败抛 `HttpError` |
| `router.py` | `resolve_api_key(env_file=None) -> str \| None` | 已 export 优先 → `--env-file` → 上溯 |
| `typesafe.py` | `build_payload(state, options, *, model, criteria_style="object") -> dict` | 构造请求体，追加 `none` |
| `typesafe.py` | `parse_answer(body) -> dict` | 严格校验并抽取三个答案，坏数据抛 `ValueError` |
| `typesafe.py` | `normalize_option(raw, known) -> str \| None` | 归一模型回显的变体；归不了返回 `None`（fail closed） |
| `typesafe.py` | `apply_gate(*, skill, confidence, min_confidence, none_winner) -> str` | 三态闸门 |
| `catalog.py` | `load_catalog(path=None) -> Catalog` | 读并校验 `catalog.yaml` |
| `catalog.py` | `parse_agents_md_modules(agents_md) -> set[str]` | 解析 AGENTS.md 模块索引表 |
| `env.py` | `load_env(start=None, *, levels=6) -> list[Path]` | 有界上溯加载 `.env` |

## 请求契约

一次 POST 问**三个问题**（官方文档：并行评估，几乎不额外增加延迟）：

| question key | 类型 | 作用 | 是否参与闸门 |
|---|---|---|---|
| `module` | choice（全部模块 + `none`） | 路由到哪个模块 | ★ 是 |
| `ambiguity` | noul | 请求是否缺关键限定 | 否，仅展示 |
| `verb` | choice | 动作类型（query/generate/apply/reconcile/…） | 否，仅展示 |

- question key（`module`/`ambiguity`/`verb`）是**我方的**，不发给模型。
- criteria 值是 object `{coverage, exclusions, examples}`。**选项名和描述都会送给模型**，
  所以 `exclusions`（"不用于…"）才是把兄弟模块分开的关键。
- `none` 选项**恒由 `build_payload` 追加在最后**，不进 `catalog.yaml` —— 防止重新生成 catalog 时被漏掉。
- criteria 用 object 形式已实测通过（HTTP 200）。若哪天被 422 拒绝，一行开关切
  `criteria_style="string"`（`build_payload` 的保险丝）。

## 阈值语义

```python
gate = apply_gate(skill=..., confidence=..., min_confidence=..., none_winner=...)
# "ok"             → 命中
# "low_confidence" → 有最佳猜测但没把握
# "none"           → 模型选了 none，或回显了 catalog 之外的选项（fail closed）
```

**`confidence` 是分布集中度，不是正确率。** 实测 0.97–1.00、几近饱和（连 `none` 胜出时也有 0.99），
所以 `--min-confidence` 实际上不触发。**兜底靠 `none` 选项**，实测有效。默认总打印 top-3 候选，
这是发现「自信的错」的窗口。

`歧义度` 只在「无法判定」分支显示：实测跨 0.87–0.98，清晰请求 0.95 与域外请求 0.96 几乎重叠，
**不具区分度**，方向正确但没有可用信号 —— 不要拿它当闸门。

## 边界条件

- **`none` 胜出 vs 未知选项**：两者都 `gate == "none"`，但 `reason` 不同，`skill` 分别是
  `"none"` / `None`。未知选项会记在 `raw_choice` 里便于排查。
- **响应校验是 fail closed**：缺字段、`probabilities` 之和不在 0.98–1.02、`confidence` 非数值
  → 一律 `ValueError`，不当成"大概没问题"。
- **重试只针对 429 / 529**，退避 1s、2s，共 3 次尝试。`401`（坏 key）与 `422`（校验失败）
  **立即失败** —— 422 的响应体会指明坏字段，是最有价值的排错信号。
- **`AGENTS.md` 表格解析**：必须容忍字面量 `—` 目录（`frappe-*` 两行）、brace 展开
  （`web-automation` 行）、跨行重复目录（`SELLFOX_API/` 出现两次）。

## 新增 / 修改模块时

`catalog.yaml` 是**运行时唯一真源**，与 `AGENTS.md` 模块索引表一一对应。
`tests/test_catalog.py::test_catalog_skill_set_equals_agents_md_table` 断言两边集合**完全相等**：
任一边增删模块而另一边没跟上，测试就红并打出差集。

所以给仓库加模块时要**同时**改三处：`AGENTS.md` 模块索引表、`catalog.yaml`、以及
`.agents/skills/<name>/SKILL.md`。`catalog.yaml` 里的 `coverage`/`exclusions`/`examples`
必须人工写 —— **路由准确率就活在这里**。

> 为什么不用自动派生：`.agents/skills/` 的目录数比 AGENTS.md 模块索引表多十几个、且互有出入；
> 触发信息散在三种形状（`triggers:` 列表 / `trigger:` 单值 / 内嵌在 description /
> 5 个完全没有）；目录还是多对一（`sellfox-api` 与 `sellfox-combo-create` 同指 `SELLFOX_API/`）。

## 测试

```bash
uv run python -m pytest intent_router/tests -q          # 离线，176 项；live 自动 skip
INTENT_ROUTER_LIVE=1 uv run python -m pytest intent_router/tests/test_live_typesafe.py -q -s   # 真实调用
```

- `test_typesafe.py` 纯函数（payload 形状、解析校验、归一化、闸门真值表）
- `test_router.py` `monkeypatch` HTTP 边界（成功 / 429 退避 / 401 快败 / 529 耗尽）
- `test_catalog.py` ★ 与 AGENTS.md 的防漂移断言
- `test_env.py` 模拟 worktree 上溯到 `parents[4]`
- `test_cli.py` 三态输出与退出码
- `test_live_typesafe.py` opt-in 真实调用，10 条标注样例 —— **唯一真正测准确率的地方**

## 实测基线（2026-09-21）

10 条标注中文样例 **10/10 命中**，`confidence` 0.97–1.00（catalog 33→35 项期间重跑 3 次均 10/10）；
模糊请求与域外请求均正确落 `none`。
单次请求约 5550 输入 token ≈ $0.00023。

## See also

- [`README.md`](README.md) — 人读版
- [`docs/reference/typesafe-contract.md`](docs/reference/typesafe-contract.md) — System One 请求/响应契约
- [`docs/index.md`](docs/index.md) — 文档索引
