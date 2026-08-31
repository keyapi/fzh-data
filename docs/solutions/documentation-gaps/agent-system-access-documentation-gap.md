---
title: AGENTS.md Missing ERPNext Environment Access Distinction
date: 2026-07-03
category: docs/solutions/documentation-gaps/
module: AGENTS.md (project instruction system)
problem_type: documentation_gap
component: documentation
severity: medium
root_cause: inadequate_documentation
resolution_type: documentation_update
applies_when:
  - agents need to query a specific ERPNext environment
  - new agents join the project and read AGENTS.md as their primary instruction source
symptoms:
  - AI agent wasted time trying FAC MCP tools against production (erpnext.vilavi.cn) which only supports REST API
  - FAC MCP distinction was documented in 4 module-specific files but absent from the central AGENTS.md instruction file
tags:
  - agent-onboarding
  - agents-md
  - erpnext
  - system-access
  - progressive-disclosure
related_components:
  - erpnext-integration
---

# AGENTS.md Missing ERPNext Environment Access Distinction

## Context

An AI agent (Claude Code) was asked to investigate an ERPNext permission issue on the production system (`erpnext.vilavi.cn`). The agent defaulted to using FAC MCP tools — which only work on the test system (`ensh.vilavi.cn`) — and wasted several rounds of tool calls before the user intervened and pointed out that production uses REST API, not MCP.

The root cause was a discoverability gap: AGENTS.md, described as the project's "唯一指令来源" (sole instruction source, line 1), had no mention of how to access the two ERPNext environments. The information existed but was scattered across four separate documents that an agent reading only AGENTS.md at session start would never discover:

1. **`EN_API/AGENT_HANDOFF.md` section 9** (lines 149–170) — the best single-source coverage of the environment strategy, including user-role layering and AI/agent behavior rules.

2. **`EN_API/README.md`** (lines 87–93) — the environment URL table showing `prod = https://erpnext.vilavi.cn` and `test = https://ensh.vilavi.cn`.

3. **`docs/fac-mcp-setup.md`** (lines 155–161) — current-limitations table explicitly stating "production site: FAC MCP not deployed."

4. **`docs/fac-dev-notes.md` Lesson 68** (lines 180–195) — a comparison table of FAC MCP vs REST API capabilities.

None of these documents were referenced from AGENTS.md. An agent bootstrapping from AGENTS.md alone had zero signal about which tool to use for which environment.

## Guidance

**Surface cross-cutting operational concerns in AGENTS.md via one-line pointers, even when full details live in sub-module docs.**

The fix adds a single line to AGENTS.md inside the existing blockquote under the module index (line 117):

```markdown
> **ERPNext 系统访问**: 生产 (`erpnext.vilavi.cn`) → REST API, 测试 (`ensh.vilavi.cn`) → FAC MCP + REST API. 详见 `EN_API/README.md`
```

### Design rationale

- **One line, not a whole section** — keeps AGENTS.md under 200 lines, consistent with its stated role as "project outline + route map" rather than exhaustive reference.
- **Uses existing blockquote format** — sits inside the same `<blockquote>` as module-index notes about `AGENT_HANDOFF.md`, Skill loading, and team roles, matching surrounding visual style.
- **Points to `EN_API/README.md` for details** — follows the progressive disclosure pattern already established (`AGENTS.md` → sub-module `AGENT_HANDOFF.md` → `README.md`). Does not duplicate the environment URL table.
- **Placed near the module index** (lines 115–117) — where agents already look for system-related pointers.

### When to NOT add something to AGENTS.md

The test for inclusion:
1. Does an agent need this information to correctly choose its **first tool call** for a task?
2. Is the wrong choice costly (wasted rounds, wrong environment)?

If both are true, surface it in AGENTS.md. If the information is only needed when executing a specific sub-module task, keep it in the sub-module's `AGENT_HANDOFF.md`.

## Why This Matters

**Before the fix**: An agent asked to investigate a production ERPNext issue had zero discoverable signal about which access mechanism to use. The agent's fallback was to try MCP tools — a reasonable default — but those tools pointed at the test system, silently producing wrong results. The user had to manually intervene.

**After the fix**: The first thing an agent sees in the routing layer is "production → REST API, test → FAC MCP + REST API." When the task mentions "production," the agent can immediately select the correct tool without trial and error.

**Broader impact**: This pattern applies to any multi-environment project where different access mechanisms exist per environment (staging DB vs production DB, test API keys vs live API keys, etc.). Each new cross-cutting concern costs exactly one line in AGENTS.md and one pointer to the authoritative doc.

## When to Apply

- When a new environment or access mechanism is added that changes which tools/APIs agents should use
- When you observe an agent repeatedly using the wrong tool for a given environment
- When consolidating scattered documentation and finding operational facts that affect agent routing decisions
- NOT when the information is purely procedural and only relevant after the agent has already chosen the right tool

## Examples

### Before (AGENTS.md, module index area, lines 115–116)

```markdown
> 每个模块有 `AGENT_HANDOFF.md`（Agent 参考）和 `README.md`（人读）。
> Skill 文件在 `.agents/skills/<name>/SKILL.md`，Agent 按触发词自动加载。
```

No mention of environments, access mechanisms, or which tool to use where.

### After (AGENTS.md, lines 115–117)

```markdown
> 每个模块有 `AGENT_HANDOFF.md`（Agent 参考）和 `README.md`（人读）。
> Skill 文件在 `.agents/skills/<name>/SKILL.md`，Agent 按触发词自动加载。
> **ERPNext 系统访问**: 生产 (`erpnext.vilavi.cn`) → REST API, 测试 (`ensh.vilavi.cn`) → FAC MCP + REST API. 详见 `EN_API/README.md`
```

### Agent behavior before the fix

1. Agent reads AGENTS.md at session start — sees no environment access guidance
2. User says "investigate permission issue on production ERPNext"
3. Agent sees FAC MCP tools available, tries `mcp__fac__get_document` / `mcp__fac__list_documents`
4. Tools hit test system (`ensh.vilavi.cn`), return data that doesn't reflect production
5. Agent tries 2–3 more MCP calls before user intervenes
6. User says "production uses REST API, FAC is only on test"
7. Agent switches to REST API

**Cost**: 3–4 wasted tool call rounds, user frustration, broken autonomy.

### Agent behavior after the fix

1. Agent reads AGENTS.md at session start — sees line 117
2. User says "investigate permission issue on production ERPNext"
3. Agent matches "production" against the routing rule
4. Agent immediately uses REST API (`frappe-core-api` skill or direct HTTP calls to `erpnext.vilavi.cn`)
5. First tool call hits the correct system

**Cost**: 0 wasted rounds.

### Counter-example: full section approach

Adding a dedicated `## ERPNext 环境访问` section with a full table would work but would:
- Add ~8 lines to a document targeting ≤200 lines
- Duplicate content from `EN_API/README.md` (two places to maintain if URLs change)
- Break the existing blockquote grouping pattern

The one-line approach achieves the same routing effect with zero duplication.

## Related

- `AGENTS.md` line 117 — the fix location
- `EN_API/AGENT_HANDOFF.md` section 9 (lines 149–170) — authoritative environment strategy documentation
- `EN_API/README.md` lines 87–93 — environment URL table
- `docs/fac-mcp-setup.md` lines 155–161 — FAC MCP deployment status
- `docs/fac-dev-notes.md` Lesson 68 (lines 180–195) — FAC MCP vs REST API comparison
