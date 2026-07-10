# erpnext — ERPNext 工单数据排查模块

> 检测"一键完工"造成的生产数据异常，生成分类排查报告。

## 快速开始

```bash
# ① 凭证初始化（首次使用）
uv run python erpnext/scripts/setup.py

# ② 拉取目标月份数据
uv run python erpnext/scripts/fetch.py --month 2026-06

# ③ 生成 Excel 报告
uv run python erpnext/scripts/gen_report.py
# → erpnext/data/2026-06_工单排查报告.xlsx
```

## 目录

```
erpnext/
├── AGENT_HANDOFF.md              ← Agent 入口
├── README.md                     ← 你在这里
├── scripts/
│   ├── setup.py                  ← 凭证检查 + 环境初始化
│   ├── fetch.py                  ← API 数据拉取 (WO / JC / SE / Version)
│   └── gen_report.py             ← Excel 分类报告生成
├── data/                         ← 输出报告 (不提交 git)
└── docs/                         ← OKF v0.1 文档
```

## 前置条件

- Python >= 3.10 + uv
- ERPNext API 凭证 (key + secret)
- 运行 `setup.py` 自动检查并引导配置
