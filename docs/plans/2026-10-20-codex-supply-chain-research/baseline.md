---
okf: v0.1
type: Reference
title: G0固定基线与G1验收扩展版本
date: 2026-10-20
---

# G0基线

本文件登记既有固定版本，不修改或移动历史tag。G1扩展是新版本，不静默覆盖冻结内容。两份PR继续独立维护；本文件不表示真实数据回放或生产上线已经完成。

| 来源 | 固定版本 | 用途 |
|---|---|---|
| Codex #301 | **`5708609d6b1a4a40e8b633dac37a79334f1bdb16`** | G0共同框架、对齐边界、C01–C13、D01–D05/B01–B07 |
| Claude #300 G0 | tag **`supply-chain-g0-baseline-20261020`** → **`b23c319a7233a93714a3c9857db64c8ebb879a01`** | 08事实契约；已实际解析tag指向 |
| Claude较早切片标签 | `supply-chain-g1-slice-20261020` → `92767c8f1d012ddeb9bf3a384444ebf2f5f8ea7e` | 历史切片版本，**不能仅按此标签名称推断它已含当前两仓/六个月/最新映射来源** |
| 本轮交接读取版本 | **`d784ef0f835b3df5a3e37eda54d510f25b110bd0`** 的11/12/13与08 | 两仓×2026-04..09的G1说明；另叠加用户本轮映射与生产只读补充 |

固定源码入口：[Codex G0树](https://github.com/keyapi/fzh-data/tree/5708609d6b1a4a40e8b633dac37a79334f1bdb16/docs/plans/2026-10-20-codex-supply-chain-research)、[Claude G0树](https://github.com/keyapi/fzh-data/tree/b23c319a7233a93714a3c9857db64c8ebb879a01/docs/research/supply-chain/2026-10-20/claude)、[本轮Claude交接树](https://github.com/keyapi/fzh-data/tree/d784ef0f835b3df5a3e37eda54d510f25b110bd0/docs/research/supply-chain/2026-10-20/claude)。后续引用SHA，不使用不断变化的分支内容代替冻结版本。

## 冻结内容与Git blob SHA-256

以下按`git show <固定SHA>:<路径>`原始bytes计算；不是Windows检出后CRLF文件的hash。Codex路径前缀为本bundle；Claude路径前缀为`docs/research/supply-chain/2026-10-20/claude/`。

| 来源/文件 | 冻结范围 | SHA-256 |
|---|---|---|
| Codex `common-framework.md` | 总体链条与分层契约 | `5ae92ec01e8a27757ee1d6398a7d49a20c4626cbc17b3727a58eb9780161c025` |
| Codex `alignment-status.md` | §3互斥余额与需求周期边界 | `a2dc348c6c3ca031c8487b80828e580aed83c344b8fb5b814a8676d44029ef56` |
| Codex `semantic-examples.md` | C01–C13及限制 | `e9a094b2e0cf58b7f6891ae6f7cb4bb69661c31bc8a8f6f64f8b309ce5c04b96` |
| Codex `contract_examples.py` | C01–C13原始执行参照 | `af2a86ae45169379054c06e90192ab6c0cca40aef091d433ee19b9190e5f719e` |
| Codex `decisions.md` | D01–D05 / B01–B07 | `24a7953865d4be2a84df7b552997d805f9b180863012d0429e87595764a5abb3` |
| Claude G0 `08-fact-contract.md` | 事实契约 | `3a6a9aadc028484aef2b38bc6ac60b2fac6a7e56b33a7ed5537f3060b2488494` |
| Claude交接版 `08-fact-contract.md` | 新增G1库存历史边界及V17 | `131e7244fe83d25c99d58646c998c73f98c934ead1e50491ec719da13344aa9c` |

对比上述两版08：§2.1/§2.4内容相同；§2.3新增当前库存/无连续历史的G1说明，互斥桶规范未变。详见[定向复核](review-08-g0.md)。

## G1扩展v1

- 任务来自用户转交的Claude12与本轮补充，范围/映射优先级见[g1-slice.md](g1-slice.md)。不回到五月至七月/单仓旧切片。
- 在原C01–C13之上增加C14–C20；源文件仍为`contract_examples.py`，冻结G0旧内容始终可按上表SHA恢复。扩展及本地结果见[semantic-examples.md](semantic-examples.md)。
- C16的取消方式、C18的修订号/互斥分类、C20的30个合成信号均是明示测试设定，不自动成为真实业务规则/覆盖率。
- 本轮仅核仓库版本、文档、合成输入；不读取本地真实xlsx、GSheet、库存或生产API。用户已明确EN单据采用生产只读，由Claude回放工作线执行，无需继续等待测试/生产二选一；本轮不执行该取数任务。
- 后续任何规范变化需记录影响、输入/输出和验证，再发布扩展版本；不得只改tag含义。数据库/计划引擎/展示入口的备选继续保留。
