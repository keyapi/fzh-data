# pb_reconciliation — Pottery Barn 对账月度更新

每月把 PB 付款和对账数据整理成给财务的对账表。核心是 `reconcile_pb.py`，自动化：追加付款、补录发票、截止判定、双开票映射、不重不漏校验、颜色标记、Notes 区块更新。

**入口**：[AGENT_HANDOFF.md](AGENT_HANDOFF.md)（完整交接，Agent/人通用）→ [docs/](docs/)（OKF 文档）

**快速上手**：
```bash
python reconcile_pb.py --dry-run   # 看报告（只读）
python reconcile_pb.py --write     # 生成时间戳新文件
```

数据文件在 `D:\Work\美国\Tracy Miller\PB orders\`（仓库外）。每次使用前改脚本顶部常量（当月邮件批次、发票文件夹、双开票映射、UPS 备注）。
