---
okf: v0.1
type: Roadmap
title: 统一 AI 接入 C′ — PoC 路线图
description: 壳已验收；板与 Portal 后续
tags: [roadmap, open-webui, ivyeaops, sellfox]
timestamp: 2026-07-24
---

# 路线图

## 已完成（壳 PoC）

- [x] S1 compose：OWUI + Docker-only Open Terminal
- [x] S2 api.vilavi.cn 模型冒烟
- [x] S3 赛狐只读 Tool 真拉取 + JSON summary
- [x] S4 Skill + 运营步骤；自定义模型绑定
- [x] 能力天花板实测：Terminal 深挖 / CI（Pyodide）对照

## 进行中 / 下一步

- [ ] 壳 PR 合并（#113）与文档索引同步
- [ ] **板 PoC** B1–B6：IvyeaOps fork → sellfox_openapi → sellers + 搜索词规范化 → optimizer 只读候选（关写）

## 之后

- [ ] Portal：nginx `/chat` `/ops` + 钉钉（两条 PoC 都绿后再开）
- [ ] 扩展 READ_DATASETS；赛狐广告写 API 到位后再谈 operate

## 明确不做（当前阶段）

广告写操作、全量运营看板、bare-metal Open Terminal、把未验证 `advertise/` 输出当真理。
