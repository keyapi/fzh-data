---
type: ImplementationPlan
title: fzh-web-automation 独立能力舱迁移实施计划
description: 将浏览器自动化迁入 fzh-data/web_automation，并建立隔离环境、固定 dispatcher、能力矩阵与安全验证。
date: 2026-08-26
status: approved-for-execution
---

# fzh-web-automation 独立能力舱迁移实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `fzh-web-automation` 的有效能力迁入 `fzh-data/web_automation/` 独立 uv 项目，让同事只 clone 一个仓库并通过统一 dispatcher 使用 API/浏览器自动化，同时不污染根 Python 环境。

**Architecture:** 根项目继续负责业务路由、数据/API 能力和 Agent 指令；`web_automation/` 是不加入 workspace 的独立 uv 项目，拥有单独的 `pyproject.toml`、`uv.lock`、`.venv` 与浏览器 profile。标准库实现的 dispatcher 读取版本化能力矩阵，先输出确定的机器状态，再按动作调用兼容脚本；bootstrap 仅在网页任务触发时同步子环境和 Chromium，OCR 通过可选 dependency group 安装。

**Tech Stack:** Python 3.12（网页能力舱）、uv 独立项目、Playwright Python、Chromium、YAML、pytest、pandas、openpyxl、可选 ddddocr/onnxruntime。

## Global Constraints

- 根项目保持 `requires-python = ">=3.10"`，根 `uv sync` 不安装 `playwright`、`ddddocr`、`onnxruntime`，也不下载 Chromium。
- `web_automation/` 不加入 uv workspace，不作为根项目 path dependency，不允许跨项目 Python import。
- 所有用户可见 Python 命令使用 `uv run python`；dispatcher 内部可用 `uv sync --project web_automation` 和 `uv run --project web_automation python ...`。
- Phase A 从相邻仓库 `origin/main` commit `04698a8fb181081221b2997ac511ffc29a474c89` 迁移；不得复制相邻工作树的 `.env`、未跟踪文件或当前落后分支内容。
- 默认人工首次登录并复用持久 profile；OCR 不是默认依赖，只在明确请求 `--with-ocr` 时安装。
- 系统级软件和运行库只报告，不自动安装；安装前必须取得用户确认。
- 赛狐导入、出入库、库存修改等写操作必须返回 `NEED_USER_CONFIRMATION`，确认范围后才允许带显式 `--confirm-scope` 执行。
- API 认证、权限、参数或业务校验错误禁止静默回退浏览器；仅能力矩阵列出的“端点缺失/不支持/服务可用性”错误允许回退。
- profiles、cookies、`.env`、下载、输出、截图、Excel 业务文件及调试 DOM/JSON 必须 gitignored。
- 新 `web_automation/docs/` 遵守 OKF：Markdown 有 YAML frontmatter，目录有 `index.md`，bundle 有 `log.md`；修改后运行 `uv run python scripts/update_index.py`。
- Phase B 的删除和去重不在本轮实施范围；必须先有调用清单、smoke test 与 API/浏览器对照证据。

---

## File map

| 文件 | 职责 |
|---|---|
| `web_automation/__init__.py`、`web_automation/scripts/__init__.py` | 让根测试可导入运行时与 dispatcher，不承载业务逻辑 |
| `web_automation/pyproject.toml` | 子项目基础浏览器依赖、OCR/dev 可选组、Python 版本边界 |
| `web_automation/.python-version` | 固定网页能力舱 Python 3.12 |
| `web_automation/uv.lock` | 可复现的子项目依赖锁；必须跟踪 |
| `web_automation/capabilities.yaml` | 版本化“平台 + 动作”路由、风险、回退和验证合同 |
| `web_automation/scripts/bootstrap.py` | 检测/sync 子环境、检测/安装 Chromium、可选 OCR |
| `web_automation/scripts/doctor.py` | 只读检查 uv/Python/依赖/Chromium/profile，输出状态 |
| `web_automation/scripts/dispatch.py` | 稳定 Agent CLI；解析动作、确认写范围、bootstrap、执行脚本 |
| `web_automation/scripts/runtime.py` | 状态、矩阵解析、错误分类和命令构造的纯标准库函数 |
| `web_automation/legacy-compatible/*.py` | Phase A 原入口兼容副本，保持脚本参数和相对目录行为 |
| `web_automation/click-based/*.py` | 赛狐导入/备货等点击式兼容脚本 |
| `web_automation/cdp-based/*.py` | 通途 CDP/OCR 探索脚本，保留但不作为默认路由 |
| `web_automation/docs/**` | OKF 索引、能力合同、迁移日志、安全边界和旧资料 |
| `tests/web_automation/conftest.py` | pytest 收集前把仓库根加入 `sys.path`，使 `web_automation.*` 可导入 |
| `tests/web_automation/**` | 不启动真实浏览器的矩阵、dispatcher、bootstrap、路径和安全测试 |
| `scripts/env_doctor.py` | 根环境只读发现网页能力舱，不安装它 |
| `AGENTS.md` | 加入短路由与固定 dispatcher 命令 |
| `.agents/skills/{web-automation,playwright-setup,tongtu-automation,sellfox-automation}/**` | Agent 入口统一指向 dispatcher |
| `.agents/skills/{stock-init,warehouse-restock}/SKILL.md` | 移除外部仓库绝对路径 |
| `warehouse_restock/*.py` | 改为仓库内 dispatcher/输出目录，不直接选择 venv |
| `missing_products/*.py` | 改用仓库相对 `web_automation/output`、`downloads` |
| `missing_products/{README.md,AGENT_HANDOFF.md}` | 更新单仓库工作流 |
| `docs/onboarding.md`、`README.md` | 非技术同事单 clone 与任务触发安装说明 |
| `.gitignore` | 覆盖子项目本地状态和敏感生成物 |

---

### Task 1: 建立能力矩阵与运行时合同

**Files:**
- Create: `web_automation/__init__.py`
- Create: `web_automation/scripts/__init__.py`
- Create: `web_automation/capabilities.yaml`
- Create: `tests/web_automation/conftest.py`
- Create: `web_automation/scripts/runtime.py`
- Create: `tests/web_automation/test_runtime.py`

**Interfaces:**
- Produces: `load_capabilities(path: Path) -> dict[str, Capability]`
- Produces: `resolve_capability(matrix: dict[str, Capability], task: str) -> Capability`
- Produces: `classify_failure(capability: Capability, code: str) -> Literal["fallback", "blocked"]`
- Produces: `build_script_command(root: Path, capability: Capability, passthrough: list[str], channel: str | None = None) -> list[str]`
- `Capability` fields: `task`, `platform`, `mode`, `risk`, `primary`, `fallback`, `allowed_fallback_codes`, `blocked_fallback_codes`, `verify`, `implementation`, `contract`, `last_verified`。

- [ ] **Step 0: 建 tests conftest，让根 pytest 能导入子项目代码**

`tests/web_automation/conftest.py`：

```python
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
```

- [ ] **Step 1: 写失败测试，固定矩阵动作和状态枚举**

```python
from pathlib import Path

import pytest

from web_automation.scripts.runtime import (
    BLOCKING_STATES,
    MODES,
    classify_failure,
    load_capabilities,
    resolve_capability,
)

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "web_automation" / "capabilities.yaml"


def test_matrix_contains_phase_a_routes():
    matrix = load_capabilities(MATRIX)
    assert {
        "tongtu.stock.export",
        "tongtu.sales.export",
        "sellfox.stock.export",
        "sellfox.other-inbound.import",
        "sellfox.other-outbound.import",
        "sellfox.restock.import",
        "web.generic.explore",
    } <= set(matrix)


def test_modes_and_states_are_closed_sets():
    assert MODES == {
        "API_ONLY",
        "API_FIRST_BROWSER_FALLBACK",
        "BROWSER_ONLY",
        "MANUAL_CONFIRM",
    }
    assert BLOCKING_STATES == {
        "NEED_BROWSER",
        "NEED_LOGIN",
        "NEED_OCR",
        "NEED_USER_CONFIRMATION",
        "BLOCKED",
    }


def test_auth_error_never_falls_back():
    cap = resolve_capability(load_capabilities(MATRIX), "sellfox.stock.export")
    assert classify_failure(cap, "AUTH_FAILED") == "blocked"
    assert classify_failure(cap, "ENDPOINT_UNSUPPORTED") == "fallback"


def test_unknown_task_is_rejected():
    with pytest.raises(KeyError, match="unknown capability"):
        resolve_capability(load_capabilities(MATRIX), "sellfox.unknown")
```

- [ ] **Step 2: 运行测试并确认因模块/矩阵不存在而失败**

Run: `uv run pytest tests/web_automation/test_runtime.py -v`

Expected: FAIL，包含 `ModuleNotFoundError` 或缺少 `capabilities.yaml`。

- [ ] **Step 3: 创建版本化能力矩阵**

矩阵使用 YAML 顶层 `version: 1` 与 `capabilities:` 映射，至少写入：

```yaml
version: 1
capabilities:
  tongtu.stock.export:
    platform: tongtu
    mode: BROWSER_ONLY
    risk: read
    primary: browser
    fallback: null
    allowed_fallback_codes: []
    blocked_fallback_codes: [AUTH_FAILED, PERMISSION_DENIED, INVALID_ARGUMENT, BUSINESS_VALIDATION]
    verify: xlsx_exists_and_has_sku_column
    implementation:
      browser: legacy-compatible/tongtu_auto_export.py
    contract: ui
    last_verified: "2026-08-26"

  tongtu.sales.export:
    platform: tongtu
    mode: BROWSER_ONLY
    risk: read
    primary: browser
    fallback: null
    allowed_fallback_codes: []
    blocked_fallback_codes: [AUTH_FAILED, PERMISSION_DENIED, INVALID_ARGUMENT, BUSINESS_VALIDATION]
    verify: xlsx_exists_and_nonempty
    implementation:
      browser: legacy-compatible/tongtu_sales_report.py
    contract: ui
    last_verified: "2026-08-26"

  sellfox.stock.export:
    platform: sellfox
    mode: API_FIRST_BROWSER_FALLBACK
    risk: read
    primary: api
    fallback: browser
    allowed_fallback_codes: [ENDPOINT_MISSING, ENDPOINT_UNSUPPORTED, SERVICE_UNAVAILABLE]
    blocked_fallback_codes: [AUTH_FAILED, PERMISSION_DENIED, INVALID_ARGUMENT, BUSINESS_VALIDATION]
    verify: warehouse_item_xlsx_exists
    implementation:
      api: legacy-compatible/sellfox_auto_export.py
      api_args: [--api]
      browser: legacy-compatible/sellfox_auto_export.py
    contract: private-cookie-api
    last_verified: "2026-08-26"

  sellfox.other-inbound.import:
    platform: sellfox
    mode: MANUAL_CONFIRM
    risk: write
    primary: browser
    fallback: null
    allowed_fallback_codes: []
    blocked_fallback_codes: [AUTH_FAILED, PERMISSION_DENIED, INVALID_ARGUMENT, BUSINESS_VALIDATION]
    verify: import_result_and_scope_summary
    implementation:
      browser: click-based/sellfox_import_other_inbound.py
    contract: ui
    last_verified: "2026-08-26"

  sellfox.other-outbound.import:
    platform: sellfox
    mode: MANUAL_CONFIRM
    risk: write
    primary: browser
    fallback: null
    allowed_fallback_codes: []
    blocked_fallback_codes: [AUTH_FAILED, PERMISSION_DENIED, INVALID_ARGUMENT, BUSINESS_VALIDATION]
    verify: import_result_and_scope_summary
    implementation:
      browser: click-based/sellfox_import_other_outbound.py
    contract: ui
    last_verified: "2026-08-26"

  sellfox.restock.import:
    platform: sellfox
    mode: MANUAL_CONFIRM
    risk: write
    primary: browser
    fallback: null
    allowed_fallback_codes: []
    blocked_fallback_codes: [AUTH_FAILED, PERMISSION_DENIED, INVALID_ARGUMENT, BUSINESS_VALIDATION]
    verify: import_result_and_scope_summary
    implementation:
      browser: click-based/sellfox_import_warehouse_restock.py
    contract: ui
    last_verified: "2026-08-26"

  web.generic.explore:
    platform: generic
    mode: BROWSER_ONLY
    risk: interactive
    primary: mcp
    fallback: null
    allowed_fallback_codes: []
    blocked_fallback_codes: [AUTH_FAILED, PERMISSION_DENIED]
    verify: agent_defined_closed_loop
    implementation:
      mcp: playwright
    contract: ui
    last_verified: "2026-08-26"
```

- [ ] **Step 4: 实现纯标准库运行时**

`runtime.py` 使用 `dataclasses.dataclass(frozen=True)`；`web_automation/__init__.py` 与 `web_automation/scripts/__init__.py` 为空文件，仅支持根测试导入。矩阵由 `yaml.safe_load` 读取；dispatcher 本身由根 `uv run python` 启动，根环境已包含 `pyyaml`，而真正执行浏览器脚本时由 bootstrap 准备子环境。所有 schema 字段缺失时抛 `ValueError("invalid capability ...")`，未知 task 抛 `KeyError("unknown capability: ...")`。

`build_script_command` 必须返回：

```python
[
    "uv", "run", "--project", str(root / "web_automation"),
    "python", str(root / "web_automation" / relative_script),
    *configured_args,
    *passthrough,
]
```

`mcp` 实现不得伪造 shell 命令，返回 `ValueError("MCP capability must be executed by the Agent")`。

- [ ] **Step 5: 运行 runtime 测试**

Run: `uv run pytest tests/web_automation/test_runtime.py -v`

Expected: PASS。

---

### Task 2: 建立独立 uv 项目和按需 bootstrap/doctor

**Files:**
- Create: `web_automation/pyproject.toml`
- Create: `web_automation/.python-version`
- Create: `web_automation/scripts/bootstrap.py`
- Create: `web_automation/scripts/doctor.py`
- Create: `tests/web_automation/test_bootstrap.py`
- Modify: `scripts/env_doctor.py`
- Modify: `tests/env_doctor/test_env_doctor.py`

**Interfaces:**
- Produces: `collect_web_facts(root: Path) -> dict[str, object]`
- Produces: `plan_bootstrap(facts: dict[str, object], with_ocr: bool) -> list[list[str]]`
- Produces CLI: `uv run python web_automation/scripts/bootstrap.py [--check|--with-ocr|--json]`
- Produces CLI: `uv run python web_automation/scripts/doctor.py [--json]`

- [ ] **Step 1: 写失败测试，确保默认计划不含 OCR**

```python
from pathlib import Path

from web_automation.scripts.bootstrap import plan_bootstrap


def test_default_bootstrap_never_installs_ocr():
    facts = {"env_ready": False, "chromium_ready": False, "ocr_ready": False}
    commands = plan_bootstrap(facts, with_ocr=False)
    flat = " ".join(" ".join(cmd) for cmd in commands)
    assert "--group ocr" not in flat
    assert "ddddocr" not in flat
    assert "onnxruntime" not in flat


def test_ocr_is_explicit_second_sync():
    facts = {"env_ready": True, "chromium_ready": True, "ocr_ready": False}
    commands = plan_bootstrap(facts, with_ocr=True)
    assert commands == [["uv", "sync", "--project", "web_automation", "--group", "ocr"]]
```

扩展根 env doctor 测试：当 `web_automation/pyproject.toml` 存在但 `.venv` 不存在时，仅报告 `web_automation_available=True`、`web_automation_ready=False`，recommendation code 为 `web_automation_on_demand`，不能包含安装命令执行结果。

- [ ] **Step 2: 运行失败测试**

Run: `uv run pytest tests/web_automation/test_bootstrap.py tests/env_doctor/test_env_doctor.py -v`

Expected: FAIL，缺少 bootstrap 或网页 facts。

- [ ] **Step 3: 创建子项目依赖边界**

`web_automation/pyproject.toml`：

```toml
[project]
name = "fzh-web-automation"
version = "1.0.0"
description = "FZH browser automation capability pod"
requires-python = ">=3.12,<3.13"
dependencies = [
  "openpyxl>=3.0",
  "pandas>=2.0",
  "pillow>=11.3.0",
  "playwright>=1.40",
  "pyyaml>=6.0",
  "requests>=2.32.5",
  "requests-toolbelt>=1.0.0",
]

[dependency-groups]
ocr = [
  "ddddocr>=1.5.6",
  "onnxruntime>=1.20.1",
]
dev = ["pytest>=9.1.1"]

[tool.uv]
default-groups = []

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = []
```

`.python-version` 写 `3.12`。不得把 OCR 放入 `[project].dependencies`。

- [ ] **Step 4: 实现 bootstrap 状态机**

`collect_web_facts` 检查：`uv`、`web_automation/.venv`、`playwright` import、`python -m playwright install --dry-run chromium` 或 Chromium executable 是否存在、`ddddocr`/`onnxruntime` import、profile 目录。所有 subprocess 使用参数数组，禁止 `shell=True`。

状态输出优先级：

1. uv 不存在 → `BLOCKED`；
2. 子环境不存在或 Playwright 未安装 → `NEED_BROWSER`；
3. 请求 OCR 但模块缺失 → `NEED_OCR`；
4. 环境和 Chromium 完整 → `READY`。

无 `--check` 时只执行 `plan_bootstrap` 生成的命令；Chromium 命令固定为：

```python
[
    "uv", "run", "--project", "web_automation",
    "python", "-m", "playwright", "install", "chromium",
]
```

- [ ] **Step 5: 实现 doctor 与根 env doctor 发现能力舱**

`doctor.py` 只调用 facts/formatter，不写磁盘。根 `scripts/env_doctor.py` 增加：

```python
"web_automation": {
    "available": (root / "web_automation" / "pyproject.toml").is_file(),
    "ready": (root / "web_automation" / ".venv").is_dir(),
}
```

并在建议中说明“网页任务触发时由 dispatcher 初始化；普通 `uv sync` 无需安装”。

- [ ] **Step 6: 生成并检查子 lockfile**

Run: `uv lock --project web_automation`

Expected: 创建 `web_automation/uv.lock`，解析成功。

Run: `uv lock --project web_automation --check`

Expected: exit 0。

- [ ] **Step 7: 运行 bootstrap/env doctor 单测**

Run: `uv run pytest tests/web_automation/test_bootstrap.py tests/env_doctor/test_env_doctor.py -v`

Expected: PASS。

---

### Task 3: 实现固定 dispatcher 与写操作范围闸门

**Files:**
- Create: `web_automation/scripts/dispatch.py`
- Create: `tests/web_automation/test_dispatch.py`

**Interfaces:**
- CLI: `uv run python web_automation/scripts/dispatch.py <task> [--check] [--with-ocr] [--confirm-scope TEXT] [--json] [-- ARGS...]`
- Produces: `RunResult(returncode: int, failure_code: str | None)`
- Produces: `DispatchResult(status: str, task: str, mode: str, channel: str | None, risk: str, command: tuple[str, ...], reason: str)`
- Produces: `dispatch(task: str, *, check: bool, with_ocr: bool, confirm_scope: str | None, passthrough: list[str], runner: Callable[..., RunResult]) -> DispatchResult`
- JSON keys: `status`, `task`, `mode`, `channel`, `risk`, `command`, `reason`。

- [ ] **Step 1: 写失败测试覆盖读、写、MCP 和回退**

```python
from web_automation.scripts.dispatch import DispatchResult, RunResult, dispatch


class FakeRunner:
    def __init__(self, results=None):
        self.calls = []
        self.results = list(results or [RunResult(0, None)])

    def __call__(self, command):
        self.calls.append(command)
        return self.results.pop(0)


def test_write_task_blocks_without_scope():
    fake_runner = FakeRunner()
    result = dispatch(
        "sellfox.other-outbound.import",
        check=False,
        with_ocr=False,
        confirm_scope=None,
        passthrough=[],
        runner=fake_runner,
    )
    assert result.status == "NEED_USER_CONFIRMATION"
    assert fake_runner.calls == []


def test_write_task_runs_with_explicit_scope():
    fake_runner = FakeRunner()
    result = dispatch(
        "sellfox.other-outbound.import",
        check=False,
        with_ocr=False,
        confirm_scope="test001-white only",
        passthrough=["input.xlsx"],
        runner=fake_runner,
    )
    assert result.status == "READY"
    assert "sellfox_import_other_outbound.py" in " ".join(fake_runner.calls[-1])


def test_generic_web_returns_agent_instruction():
    fake_runner = FakeRunner()
    result = dispatch("web.generic.explore", check=False, with_ocr=False,
                      confirm_scope=None, passthrough=[], runner=fake_runner)
    assert result.status == "READY"
    assert result.channel == "mcp"
    assert fake_runner.calls == []


def test_blocked_api_error_does_not_execute_browser():
    fake_runner = FakeRunner([RunResult(1, "AUTH_FAILED")])
    result = dispatch("sellfox.stock.export", check=False, with_ocr=False,
                      confirm_scope=None, passthrough=[], runner=fake_runner)
    assert result.status == "BLOCKED"
    assert len(fake_runner.calls) == 1
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `uv run pytest tests/web_automation/test_dispatch.py -v`

Expected: FAIL，缺少 dispatcher。

- [ ] **Step 3: 实现 dispatcher**

行为必须为：

1. 读取矩阵；
2. 未知 task 输出 `BLOCKED` 且 exit 2；
3. `risk=write` 且没有非空 `--confirm-scope` 时输出 `NEED_USER_CONFIRMATION` 且 exit 3；
4. `--check` 只输出 route/bootstrap 状态，不运行脚本；
5. `primary=mcp` 输出 Playwright MCP 探路指令，不启动 Python Playwright；
6. Python 脚本前调用 bootstrap；
7. API-first 仅在 runner 返回结构化 failure code 且 code 位于 `allowed_fallback_codes` 时执行 browser；
8. 旧脚本只返回普通非零码时统一映射为 `UNCLASSIFIED_FAILURE` 并 `BLOCKED`，不得猜测后回退。

为兼容当前 `sellfox_auto_export.py --api` 尚未产生结构化错误码，Phase A 中 API 失败默认阻断并建议用户改用显式 `--channel browser`；`--channel browser` 只对矩阵声明 browser implementation 的读操作开放，不能绕过写操作确认。

- [ ] **Step 4: 运行 dispatcher 单测**

Run: `uv run pytest tests/web_automation/test_dispatch.py -v`

Expected: PASS。

---

### Task 4: 从远端 main 迁入兼容脚本，不携带本地状态

**Files:**
- Create: `web_automation/legacy-compatible/*.py`
- Create: `web_automation/click-based/*.py`
- Create: `web_automation/cdp-based/*.py`
- Create: `web_automation/.env.example`
- Create: `web_automation/.mcp.json`
- Create: `tests/web_automation/test_migrated_entrypoints.py`

**Interfaces:**
- All migrated script paths in `capabilities.yaml` must exist.
- Existing CLI arguments remain unchanged during Phase A.
- Script-local entrypoints preserve their CLI, while profiles/downloads/output are normalized to the `web_automation/` root.

- [ ] **Step 1: 写迁移清单测试**

测试断言以下文件存在且可由 `ast.parse` 解析：

```python
EXPECTED = [
    "legacy-compatible/tongtu_auto_export.py",
    "legacy-compatible/tongtu_sales_report.py",
    "legacy-compatible/process_sales_report.py",
    "legacy-compatible/generate_tongtu_import.py",
    "legacy-compatible/merge_inventory.py",
    "legacy-compatible/inspect_warehouse.py",
    "legacy-compatible/mcp_to_output.py",
    "legacy-compatible/sellfox_auto_export.py",
    "legacy-compatible/sellfox_import_update.py",
    "legacy-compatible/sellfox_restock_api.py",
    "legacy-compatible/commodity_import_template.py",
    "legacy-compatible/ddddocr_login.py",
    "legacy-compatible/tongtu_login_ocr.py",
    "legacy-compatible/sellfox_login_ocr.py",
    "click-based/sellfox_import_other_inbound.py",
    "click-based/sellfox_import_other_outbound.py",
    "click-based/sellfox_import_warehouse_restock.py",
    "click-based/sellfox_restock_allocate_ship.py",
    "click-based/sellfox_restock_receive.py",
]
```

测试还断言任何 `.py` 不包含 `D:\\Work\\赛狐\\网页自动化`。

- [ ] **Step 2: 从 git object 复制，不从工作树复制**

使用 `git -C "D:/Work/赛狐/网页自动化" show "origin/main:<path>"` 或 `git archive origin/main` 提取上面清单以及 `cdp-based/`；不得复制：`.env`、profiles、cookies、Excel、截图、downloads/output、`.codex/`、`.claude/`、工作树未跟踪的 `SKILL_*.md`。

根级源脚本放入 `legacy-compatible/`，源 `click-based/` 与 `cdp-based/` 保留目录名。把源 `.env.example` 和 `.mcp.json` 放在 `web_automation/` 根。

- [ ] **Step 3: 修复兼容目录内的 sibling import**

所有浏览器 profile 与下载/output 统一位于 `web_automation/` 根，便于根模块稳定发现。迁入后把兼容脚本的目录常量改为：

```python
SCRIPT_DIR = Path(__file__).resolve().parent
WEB_ROOT = SCRIPT_DIR.parent if SCRIPT_DIR.name in {"legacy-compatible", "click-based", "cdp-based"} else SCRIPT_DIR
PROFILE_DIR = WEB_ROOT / "chrome-profile"  # 赛狐脚本使用 sellfox-profile
DOWNLOADS_DIR = WEB_ROOT / "downloads"
OUTPUT_DIR = WEB_ROOT / "output"
```

`tongtu_auto_export.py` 的 `from tongtu_login_ocr import ...` 等导入保持同目录可解析；如果入口由绝对文件路径执行，Python 已把脚本目录加入 `sys.path`，不新增 package 抽象。`click-based` 脚本若依赖根级 sibling，显式加入：

```python
SCRIPT_DIR = Path(__file__).resolve().parent
LEGACY_DIR = SCRIPT_DIR.parent / "legacy-compatible"
if str(LEGACY_DIR) not in sys.path:
    sys.path.insert(0, str(LEGACY_DIR))
```

只做必要路径适配，不重构选择器和业务流程。

- [ ] **Step 4: 运行语法/清单测试**

Run: `uv run pytest tests/web_automation/test_migrated_entrypoints.py -v`

Expected: PASS。

- [ ] **Step 5: 子环境 import smoke test**

Run: `uv run --project web_automation python -c "import playwright, pandas, openpyxl, requests, yaml; print('READY')"`

Expected: `READY`。此步骤允许创建子 `.venv`，但不得安装 OCR group。

---

### Task 5: 迁移并改造 Agent Skills

**Files:**
- Create/Replace: `.agents/skills/web-automation/SKILL.md`
- Create/Replace: `.agents/skills/playwright-setup/SKILL.md`
- Create/Replace: `.agents/skills/tongtu-automation/SKILL.md`
- Create/Replace: `.agents/skills/tongtu-automation/references/**`
- Create/Replace: `.agents/skills/sellfox-automation/SKILL.md`
- Create/Replace: `.agents/skills/sellfox-automation/references/**`
- Modify: `.agents/skills/stock-init/SKILL.md`
- Modify: `.agents/skills/warehouse-restock/SKILL.md`
- Modify: `AGENTS.md`
- Create: `tests/web_automation/test_agent_routes.py`

**Interfaces:**
- Every browser business skill starts with the same dispatcher command.
- Skills do not tell weak models to choose a venv or external path.

- [ ] **Step 1: 写失败测试查找旧路径和固定入口**

```python
SKILLS = [
    ".agents/skills/web-automation/SKILL.md",
    ".agents/skills/playwright-setup/SKILL.md",
    ".agents/skills/tongtu-automation/SKILL.md",
    ".agents/skills/sellfox-automation/SKILL.md",
    ".agents/skills/stock-init/SKILL.md",
    ".agents/skills/warehouse-restock/SKILL.md",
]


def test_skills_never_reference_external_repo():
    for path in SKILLS:
        text = (ROOT / path).read_text(encoding="utf-8-sig")
        assert "D:\\Work\\赛狐\\网页自动化" not in text
        assert "fzh-web-automation" not in text or "历史来源" in text


def test_browser_skills_use_dispatcher():
    for path in SKILLS[:4]:
        text = (ROOT / path).read_text(encoding="utf-8-sig")
        assert "web_automation/scripts/dispatch.py" in text
```

- [ ] **Step 2: 迁入源 skills/references**

从 `origin/main` 提取 4 个 skills；保留通途 ExtJS、赛狐 Element UI、选择器、登录和库存备份知识。不要迁入源 `okf` skill，因为根项目已有自己的 OKF 规则。

- [ ] **Step 3: 把执行规则改为 dispatcher-first**

统一模板：

```bash
uv run python web_automation/scripts/dispatch.py <task> --check
uv run python web_automation/scripts/dispatch.py <task> -- [原脚本参数]
```

写动作模板必须是：

```bash
uv run python web_automation/scripts/dispatch.py sellfox.restock.import \
  --confirm-scope "用户明确确认的文件/SKU/仓库范围" -- <file.xlsx>
```

OCR 模板仅在用户明确要求全自动登录时加入 `--with-ocr`。

- [ ] **Step 4: 更新 AGENTS.md 短路由**

在模块索引加入 `web-automation`，关键规则加入：任何网页任务先运行 dispatcher；Agent 不得自行拼绝对路径/venv/安装 OCR；`READY/NEED_*` 状态按字面执行。控制 AGENTS.md 仍接近 200 行，不复制长选择器说明。

- [ ] **Step 5: 运行 Agent 路由测试**

Run: `uv run pytest tests/web_automation/test_agent_routes.py -v`

Expected: PASS。

---

### Task 6: 消除根项目对外部仓库和 Windows venv 路径的依赖

**Files:**
- Modify: `warehouse_restock/run_full_restock_flow.py`
- Modify: `warehouse_restock/test_e2e_flow.py`
- Modify: `missing_products/identify_missing_products.py`
- Modify: `missing_products/audit_three_systems.py`
- Create/Modify: `tests/web_automation/test_repo_paths.py`
- Modify: `tests/missing_products/test_audit_three_systems.py`（仅把期望数据目录改为仓库内 `web_automation/`）

**Interfaces:**
- Produces: `WEB_AUTOMATION = REPO_ROOT / "web_automation"`
- Produces: `run_web_task(task: str, *args: str, confirm_scope: str | None = None) -> int`
- Root modules consume files from `web_automation/output` and `web_automation/downloads` only.

- [ ] **Step 1: 写失败测试扫描外部路径**

测试扫描 tracked `.py` 和本任务列出的 Markdown，排除 `.claude/settings.local.json` 与历史设计文档，断言不出现：

```text
D:\Work\赛狐\网页自动化
D:/Work/赛狐/网页自动化
```

另测 Windows/Posix 均不拼 `.venv/Scripts/python.exe` 或 `.venv/bin/python`。

- [ ] **Step 2: 改造 warehouse restock 调度器**

删除 `WEB_AUTO`、`CURSOR_VENV`、`WEB_VENV`。增加：

```python
REPO_ROOT = Path(__file__).resolve().parent.parent
DISPATCH = REPO_ROOT / "web_automation" / "scripts" / "dispatch.py"


def run_web_task(task: str, *extra_args: str, confirm_scope: str | None = None) -> int:
    args = ["uv", "run", "python", str(DISPATCH), task]
    if confirm_scope:
        args.extend(["--confirm-scope", confirm_scope])
    if extra_args:
        args.extend(["--", *extra_args])
    return subprocess.run(args, cwd=REPO_ROOT, env={**os.environ, "PYTHONIOENCODING": "utf-8"}).returncode
```

导出调用 `sellfox.stock.export`；其他出库和备货导入必须从用户已确认的 prompt 构造 `confirm_scope`。生成根项目 Excel 仍用当前 `sys.executable`，不要调用 `.venv` 绝对路径。

- [ ] **Step 3: 修复 E2E Step 5 自递归**

删除 `step_5_warehouse_restock` 中先调用 `test_e2e_flow.py` 自身的这段：

```python
ret = run_script(Path(__file__).resolve(), Path(__file__).resolve().parent, CURSOR_VENV)
```

只运行 `build_saihu_warehouse_restock.py`。真实写操作测试仍默认使用 `test001-white`，不得扩展范围。

- [ ] **Step 4: 改造 missing_products 数据目录**

把 `_WEB/WEB` 改为：

```python
_REPO_ROOT = Path(__file__).resolve().parent.parent
_WEB = _REPO_ROOT / "web_automation"
```

凭证仍按用户现有约定从父仓库主 checkout/环境变量读取；本任务不复制 `.env` 到 worktree。

- [ ] **Step 5: 运行路径和现有 missing-products 测试**

Run: `uv run pytest tests/web_automation/test_repo_paths.py tests/missing_products -v`

Expected: PASS。

---

### Task 7: 建立 gitignore 与敏感状态防线

**Files:**
- Modify: `.gitignore`
- Create: `web_automation/.gitignore`
- Create: `tests/web_automation/test_gitignore.py`

**Interfaces:**
- Child `uv.lock` is tracked; child `.venv` and runtime state are ignored.

- [ ] **Step 1: 写失败测试检查 ignore 行为**

使用 `git check-ignore` 断言以下路径被忽略：

```text
web_automation/.venv/
web_automation/profiles/
web_automation/chrome-profile/
web_automation/sellfox-profile/
web_automation/downloads/a.xlsx
web_automation/output/a.xlsx
web_automation/mcp_cookies.json
web_automation/sellfox_cookies.json
web_automation/.env
web_automation/debug_page.json
web_automation/screenshot.png
```

并断言 `web_automation/uv.lock` **不**被忽略。

- [ ] **Step 2: 写最小 ignore 规则**

子 `.gitignore` 必须覆盖 `.venv/`、profiles、cookie、`.env`、downloads/output、截图、debug 文件和业务 Excel；不得包含 `uv.lock`。根 `.gitignore` 加对应 `web_automation/**` 防御规则，但用 `!web_automation/uv.lock` 保证 lock 可跟踪。

- [ ] **Step 3: 运行 ignore 测试**

Run: `uv run pytest tests/web_automation/test_gitignore.py -v`

Expected: PASS。

---

### Task 8: 迁移 OKF 文档并更新非技术同事入口

**Files:**
- Create: `web_automation/docs/index.md`
- Create: `web_automation/docs/log.md`
- Create: `web_automation/docs/reference/index.md`
- Create: `web_automation/docs/reference/capability-matrix.md`
- Create: `web_automation/docs/reference/security-and-local-state.md`
- Create/Adapt: `web_automation/docs/reference/{technical-decisions,tongtu-pitfalls,sellfox-pitfalls,ddddocr-setup,tongtu-captcha-ocr}.md`
- Create/Adapt: `web_automation/docs/lessons/**`
- Create: `web_automation/docs/solutions/index.md`
- Create/Adapt: `web_automation/docs/solutions/integration-issues/ddddocr-playwright-login-fixes.md`
- Modify: `README.md`
- Modify: `docs/onboarding.md`
- Modify: `missing_products/README.md`
- Modify: `missing_products/AGENT_HANDOFF.md`
- Modify: `index.md` via generator
- Create: `tests/web_automation/test_docs.py`

**Interfaces:**
- Every new Markdown document starts with YAML frontmatter containing `type:`.
- `web_automation/docs/index.md` links capability matrix, safety, setup and migration log.

- [ ] **Step 1: 写失败测试检查 frontmatter、索引和旧路径**

测试遍历 `web_automation/docs/**/*.md`：首行是 `---`、frontmatter 含 `type:`；每个 docs 目录有 `index.md`；`web_automation/docs/log.md` 存在；用户入口文档不包含外部绝对路径。

- [ ] **Step 2: 迁入并适配源知识文档**

从 `origin/main` 提取仍有价值的 reference/lessons/solutions；统一加/保留 OKF frontmatter。删除仅描述双仓 clone、Gitee 镜像贡献或旧仓初始化的内容，不删除选择器、验证码、profile、库存备份和页面陷阱知识。

- [ ] **Step 3: 写 capability-matrix 和安全文档**

`capability-matrix.md` 解释四种 mode、允许/禁止回退错误、`private-cookie-api` 与正式 Sellfox OpenAPI 的区别、最近验证日期更新规则。`security-and-local-state.md` 明确 profile/cookie/凭证只在本机，首次登录优先人工，OCR 可选，写操作范围确认。

- [ ] **Step 4: 更新 README/onboarding**

非技术同事只需：clone → 根 `uv sync` → 表达业务目标。网页任务由 Agent 执行：

```bash
uv run python web_automation/scripts/dispatch.py tongtu.stock.export --check
```

若 `NEED_BROWSER`，dispatcher/bootstrap 建子环境；若 `NEED_LOGIN`，让用户在打开的浏览器登录；若 `NEED_OCR`，说明 OCR 可选并先询问；若 `NEED_USER_CONFIRMATION`，先确认具体文件/SKU/仓库范围。

- [ ] **Step 5: 更新根文档索引**

Run: `uv run python scripts/update_index.py`

Expected: 输出索引更新，`index.md` 出现 `web_automation`。

- [ ] **Step 6: 运行文档测试和索引检查**

Run: `uv run pytest tests/web_automation/test_docs.py -v`

Run: `uv run python scripts/update_index.py --check`

Expected: 均 PASS，并报告 index up to date。

---

### Task 9: Phase A 综合验证与迁移证据

**Files:**
- Create: `web_automation/docs/log.md` 新记录
- Modify tests only if a verified portability defect is found

**Interfaces:**
- No real Sellfox/Tongtool write operation is part of automated verification.
- Browser smoke checks stop before business-side import/confirmation unless user separately confirms test scope.

- [ ] **Step 1: 运行根测试子集**

Run:

```bash
uv run pytest \
  tests/web_automation \
  tests/env_doctor \
  tests/missing_products -v
```

Expected: PASS。

- [ ] **Step 2: 验证根环境隔离**

Run:

```bash
uv run python -c "import importlib.util as i; assert i.find_spec('playwright') is None; assert i.find_spec('ddddocr') is None; assert i.find_spec('onnxruntime') is None; print('ROOT_ISOLATED')"
```

Expected: `ROOT_ISOLATED`。如果开发者根环境此前手动安装过这些包，则改为检查 `uv tree --depth 1` 不包含它们，并在 log 记录环境例外。

- [ ] **Step 3: 验证默认子环境无 OCR**

Run:

```bash
uv run --project web_automation python -c "import playwright; import importlib.util as i; assert i.find_spec('ddddocr') is None; assert i.find_spec('onnxruntime') is None; print('BROWSER_ONLY_READY')"
```

Expected: `BROWSER_ONLY_READY`。

- [ ] **Step 4: 检查 dispatcher 状态，不执行真实业务动作**

Run:

```bash
uv run python web_automation/scripts/dispatch.py tongtu.stock.export --check --json
uv run python web_automation/scripts/dispatch.py sellfox.stock.export --check --json
uv run python web_automation/scripts/dispatch.py sellfox.restock.import --check --json
```

Expected: 前两项返回 route/bootstrap 状态；写项返回 `NEED_USER_CONFIRMATION`，且未启动导入脚本。

- [ ] **Step 5: 安装/检测 Chromium 并做本地空白页 smoke test**

Run: `uv run python web_automation/scripts/bootstrap.py`

Run:

```bash
uv run --project web_automation python -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(headless=True); page=b.new_page(); page.set_content('<title>ok</title>'); assert page.title()=='ok'; b.close(); p.stop(); print('CHROMIUM_READY')"
```

Expected: `CHROMIUM_READY`。该测试不访问第三方网站。

- [ ] **Step 6: 搜索残留外部路径和敏感文件**

Run: `git grep -n -E 'D:\\Work\\赛狐\\网页自动化|D:/Work/赛狐/网页自动化' -- ':!.claude/settings.local.json' ':!docs/superpowers/**'`

Expected: zero output。

Run: `git status --short`

Expected: 不出现 `.env`、profiles、cookies、Excel、截图、downloads/output；`web_automation/uv.lock` 应出现为 tracked candidate。

- [ ] **Step 7: 执行四条凭证扫描**

对 `git diff --cached` 或准备提交的 diff 执行 `AGENTS.md` 第 9 条四个 regex。Expected: 全部 zero output。若文档示例触发，改成明显占位符，不能跳过扫描。

- [ ] **Step 8: 记录 boil-the-lake 迁移报告**

在 `web_automation/docs/log.md` 写：源 commit、计划迁移文件数、实际迁移文件数、跳过文件及原因、测试数、失败/修复、根/子依赖隔离结果、Chromium smoke 结果、凭证扫描结果。数量必须对账，不能只写“迁移完成”。

- [ ] **Step 9: 最终索引检查**

Run: `uv run python scripts/update_index.py && uv run python scripts/update_index.py --check`

Expected: `OK: index.md is up to date`，并输出“已同步更新根目录索引”。

---

### Task 10: Phase B 清理的显式延期门槛

**Files:**
- Create: `web_automation/docs/reference/phase-b-retirement-gates.md`

**Interfaces:**
- No code deletion in this task.
- Each candidate retirement row includes: caller inventory, API parity, browser parity, sample scope, last verification, rollback path, decision。

- [ ] **Step 1: 写 Phase B 门槛文档**

列出 `click-based/` 重复入口、`sellfox_restock_api.py` 私有 cookie API、根级兼容脚本、OCR 探索脚本等候选，但全部初始状态为 `KEEP_PENDING_EVIDENCE`。

删除条件必须同时满足：

1. `git grep` 无调用者或调用者已迁移；
2. `--help`/import smoke 与业务样本闭环通过；
3. API 与浏览器输出的 sheet、列、行数和关键汇总一致；
4. 写操作只在测试商品/明确范围验证；
5. 有回滚路径和最近验证日期；
6. 用户单独批准 Phase B。

- [ ] **Step 2: 运行文档规范测试**

Run: `uv run pytest tests/web_automation/test_docs.py -v`

Expected: PASS。

- [ ] **Step 3: 停止，不删除旧实现**

本轮交付完成后保留所有 Phase A 兼容脚本。不得因“看起来重复”删除 `click-based/`、OCR、私有 API 或通用 Playwright 能力。

---

## Execution order and review gates

1. Tasks 1–3 先建立可测试合同，不复制业务脚本前先固定路由和安全闸门。
2. Task 4 只从 `origin/main@04698a8` 迁入 tracked 文件。
3. Tasks 5–8 接入 Agent、根模块与文档。
4. Task 9 完成后才可称 Phase A 完成。
5. Task 10 只记录 Phase B 门槛；任何删除另开计划和 PR。

## Commit boundaries

只有用户明确要求提交时才创建 commit；建议边界如下：

1. `feat(web-automation): add isolated runtime and dispatcher`
2. `feat(web-automation): migrate compatible browser scripts`
3. `docs(web-automation): route agents through capability pod`
4. `test(web-automation): verify isolation and migration safety`

每个 commit 都必须在当前功能分支，禁止直接提交或 push `main`。
