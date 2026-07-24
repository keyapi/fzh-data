---
okf: v0.1
type: Roadmap
title: 统一 AI 接入 C′ — PoC 路线图
description: 壳已验收；板 B1–B6 技术跑通；Portal 待运营审后
tags: [roadmap, open-webui, ivyeaops, sellfox]
timestamp: 2026-07-24
---

# 路线图

## 已完成（壳 PoC）

- [x] S1–S4 + CI/Terminal 天花板实测

## 已完成（板 PoC 技术）

- [x] B1 clone `IvyeaOps-sellfox` / `sellfox-readonly-poc`
- [x] B2–B3 sellfox_openapi + sellers probe（99 店）
- [x] B4 aggregate ingest（1922 行）
- [x] B5 否词/收割候选 + 写路径硬禁
- [x] B6 偏差清单 + candidates 导出

## 进行中 / 下一步

- [ ] 壳 PR #113 合并
- [ ] 板 PR（本分支）合并
- [ ] 运营审 `board/docs/reference/deviations.md` 与 `board/out/candidates.csv`

## 之后

- [ ] Portal：nginx `/chat` `/ops` + 钉钉
- [ ] 扩展 READ_DATASETS；赛狐写 API 后再谈 operate

## 明确不做（当前阶段）

广告写操作、全量看板、bare-metal Open Terminal、未验证 `advertise/` 当真理。
