---
okf: v0.1
type: Roadmap
title: 统一 AI 接入 C′ — PoC 路线图
description: 壳 #113 + 板 #116 已合并；Portal PoC 交付；运营审 DEFERRED
tags: [roadmap, open-webui, ivyeaops, sellfox, portal]
timestamp: 2026-07-24
---

# 路线图

## 已完成（壳 PoC）

- [x] S1–S4 + CI/Terminal 天花板实测
- [x] PR [#113](https://github.com/keyapi/fzh-data/pull/113) 合并（2026-07-24）

## 已完成（板 PoC 技术）

- [x] B1–B6 + PR [#116](https://github.com/keyapi/fzh-data/pull/116) 合并（2026-07-24）

## 已完成（Portal PoC）

- [x] nginx `/chat` → OWUI、`/ops` → board stub、可选 `/oidc`
- [x] E2E 自测 `portal/docs/specs/2026-07-24-portal-e2e.md`（10/10 PASS）
- [ ] Portal PR 合并（本切片）

## 延期（不阻塞 Portal）

- [ ] **运营审** — 状态 **DEFERRED**；简报 [board/docs/specs/ops-review-brief.md](../board/docs/specs/ops-review-brief.md)

## 之后

- [ ] 钉钉 live SSO（需 App 密钥）+ oauth2-proxy
- [ ] 子域或 OWUI 官方子路径成熟后收紧 `/chat` 资产劫持
- [ ] 扩展 READ_DATASETS；赛狐写 API 后再谈 operate

## 明确不做（当前阶段）

广告写操作、全量看板、bare-metal Open Terminal、未验证 `advertise/` 当真理、IvyeaOps AGPL vendoring。
