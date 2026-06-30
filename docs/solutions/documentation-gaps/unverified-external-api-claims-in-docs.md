---
title: Verify External API Claims Against Official Documentation Before Committing to Docs
date: 2026-06-30
category: documentation-gaps
module: advertise
problem_type: documentation_gap
component: documentation
severity: medium
root_cause: inadequate_documentation
resolution_type: documentation_update
related_components:
  - tooling
tags:
  - amazon-ads-api
  - documentation-verification
  - sponsored-products
  - api-reference
  - roadmap-planning
  - external-api
  - data-sources
applies_when:
  - documenting external API capabilities without consulting official provider docs
  - creating project roadmaps based on unverified external data source references
  - referencing third-party API report type IDs without cross-checking against provider documentation
symptoms:
  - "documentation claims API report type IDs that do not exist in the official API (e.g., `spAdGroups` for SP)"
  - roadmap features planned for API endpoints that have no programmatic access
  - console-only features mislabeled as having API support in reference docs
---

# Verify External API Claims Against Official Documentation Before Committing to Docs

## Context

The `fzh-data` project's Amazon advertising module (`advertise/`) documented 9 "missing" Sponsored Products report types in `advertise/docs/reference/data-sources.md`, each with specific API identifiers and priorities. These claims originated from the v0.3 expert research sprint (2026-06-17) and propagated into the roadmap, AGENT_HANDOFF, and column-mappings reference — all of which treated them as established facts.

When three parallel web-search agents verified each claim against Amazon's official Ads API documentation on 2026-06-30, **5 of the 9 were wrong**: 2 were console-only (no API access), and 3 didn't exist as claimed. The module's stated data coverage ("4/13 SP report types") was inflated, the roadmap contained phantom work items, and every downstream document that cited these reports inherited the errors.

This is a textbook case of documentation drift: writing claims about an external system without verifying each one against the authoritative source. The cost was not just wrong data — it was an entire web of interconnected documents built on a faulty foundation.

## Guidance

**Before committing any external API claim to project documentation, verify it against the official provider docs and include the citation URL.**

Six concrete requirements:

1. **Include the official source URL as a citation for every external claim.** Link to the specific page, not just the documentation homepage. For Amazon Ads API: `advertising.amazon.com/API/docs/` or `advertising.amazon.com/help/`.

2. **Mark unverified claims explicitly.** If a claim cannot be confirmed at write time, tag it: "TBC — needs verification against [official docs URL]" or "UNVERIFIED — claim from [source], not found in official API reference."

3. **Distinguish between API-accessible and console-only data sources.** A console-only report cannot be automated. Always specify the access method.

4. **Verify identifiers against the vendor's enumeration, not naming conventions.** Amazon's `spPurchasedProduct` is a real identifier; `spAdGroups` (for SP) is not — it was guessed from naming convention. Look up the vendor's complete list.

5. **Add verification timestamp and caveats when fixing.** The corrected `data-sources.md` now has ✅/⚠️/❌ status flags with a "校验时间: 2026-06-30" header.

6. **Apply this discipline to ALL external references.** Third-party tool capabilities, competitor benchmarks, industry statistics — every claim about an external system needs a citation trail.

## Why This Matters

**5 of 9 planned integrations were incorrect.** The verification revealed:

| Report | Claimed | Actual |
|--------|---------|--------|
| Search Term Impression Share | API `spSearchTermImpressionShare` | Console only — Amazon never shipped API support despite years of community requests |
| Performance Over Time | Standalone report | Console only — equivalent data available via `spCampaigns` + `timeUnit: DAILY` |
| Budget | Beta report | Does NOT exist — Budget Usage API (`/sp/campaigns/budget/usage`) is a separate API, not a report type |
| Ad Group (SP) | `spAdGroups` | Does NOT exist for SP — use `spCampaigns` + `groupBy: adGroup` |
| Video | `spVideo` | Does NOT exist — SB Video uses `creativeType: video` filter; SP Video metrics are in standard SP reports |

**Concrete impact:**

- **Phantom roadmap items**: "补充报告 (Purchased Product + Impression Share + Perf Over Time)" — 2 of those 3 cannot be automated
- **Inflated data-coverage**: AGENT_HANDOFF stated "4/13 SP 报告" when the real API-accessible count is closer to 6-7
- **Agent confusion**: An agent reading the old docs would confidently tell a user to "export the Budget report" — a report that doesn't exist
- **Trust erosion**: When readers discover multiple wrong claims, they learn to distrust all documentation. Recovering from that is expensive.

**Root cause**: Absence of a verification step in the documentation workflow. Plausible-sounding names and API IDs (likely inferred from naming conventions or community discussions) were written down without cross-checking against the official source. No process caught the mismatch before the content was committed and disseminated.

## When to Apply

- **Before documenting any external API endpoint, report type, or data source.** Open the vendor's official docs and confirm each claim.
- **Before including external data sources in roadmaps or plans.** Verify existence, access method, and schema compatibility. If unverifiable, add a dependency: "Needs verification before starting."
- **When writing reference docs that cite external capabilities.** Every "System X provides Y" claim needs a citation URL to System X's docs.
- **When agents research external APIs.** After gathering from web searches and blogs, cross-check against official docs. Default to the official source if secondary sources contradict.
- **During periodic documentation audits.** Re-verify claims against current official docs — APIs evolve and URLs change.

## Examples

### Before/After: The data-sources.md Table

**Before** (all 9 reports presented as established API types):

```
| # | 报告 | API ID | 优先级 |
|---|------|--------|--------|
| 1 | Purchased Product | spPurchasedProduct | 高 |
| 2 | Search Term Impression Share | spSearchTermImpressionShare | 高 |
| 3 | Performance Over Time | (时间序列) | 高 |
| 4 | Budget | (beta) | 中 |
| ...
```

**After** (verified with status flags, official URLs, and access methods):

```
| # | 报告 | 原 API ID | 校验 | 实际获取方式 | 官网文档 URL |
|---|------|-----------|------|-------------|-------------|
| 1 | Purchased Product | spPurchasedProduct | ✅ CONFIRMED | Ads Console + API v3 | [link] |
| 2 | Search Term Impression Share | spSearchTermImpressionShare | ⚠️ CONSOLE ONLY | Ads Console（API 不支持） | [link] |
| 3 | Performance Over Time | — | ⚠️ CONSOLE ONLY | 等效数据可用 spCampaigns+DAILY | [link] |
| 4 | Budget | — | ❌ NOT FOUND | 有 Budget Usage API 但不含建议预算 | [link] |
| ...
```

### Template for Citing External Sources

```markdown
### [Report/Endpoint Name]

- **Official name**: [exact name from vendor docs]
- **Identifier**: [API endpoint or report type ID]
- **Access method**: [API / Console / File Export / Not Available]
- **Official documentation**: [direct URL]
- **Verification date**: [YYYY-MM-DD]
- **Status**: [CONFIRMED / CONSOLE ONLY / NOT FOUND / TBC]
```

### How One Wrong Claim Cascaded

The `spSearchTermImpressionShare` claim propagated through 5 interconnected documents:

1. `data-sources.md` listed it as API-accessible with high priority
2. `roadmap.md` added it as a Phase 4+ work item
3. `AGENT_HANDOFF.md` used it to calculate "4/13" data coverage
4. `column-mappings.md` structured assumptions around it
5. Every agent and team member who read those docs built mental models on it

Fixing one wrong claim meant fixing 5 documents. Verifying at write time would have prevented all of it.

### Follow-up (2026-06-30): 优麦云 + 卖家精灵

同一核验流程应用于第三方工具声明后，同样发现错误：

| 工具 | 原声明 | 核验结果 |
|------|--------|---------|
| 优麦云 | "仅 Excel 导出、无 API" | 已有 MCP API (`sellerspace.com/mcp/`)，10 维度读写 |
| 卖家精灵 | MCP 端点 `open.sellersprite.com/mcp/22` | 只是文档页面，真实端点为 `mcp.sellersprite.com/sse` |

这类错误的模式一致：**早期调研时的印象/二手信息被当作确定事实写入了文档**，后续无人对照官方来源复查。Lesson 13 的规则完全适用于第三方工具。

## Related

- `advertise/docs/reference/data-sources.md` — The file that was corrected with verification status for all 9 SP report types
- `advertise/docs/reference/source-urls.md` — 60+ research URLs including the Amazon Ads API report types overview used for cross-verification
- `advertise/docs/lessons/lessons-learned.md` — 12 existing lessons for the Amazon advertising module
- `advertise/docs/research/2026-06-16-amazon-advertising-analysis-research.md` — Original research doc that likely introduced the unverified claims
