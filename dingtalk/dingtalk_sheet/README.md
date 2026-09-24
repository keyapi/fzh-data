# dingtalk_sheet — 读钉钉表格

只读读取钉钉表格（workbook / alidocs）文档内容。**不写入、不修改任何钉钉文档。**

与同目录 `dingtalk_robot` 用途不同：那个是**发消息**（群机器人 webhook），这个是**读文档**。

## 它解决什么问题

供应链的头程数据（工厂发货、物流单号、批次离港/到港）不在 EN 里，而在两张人工维护的
钉钉表格里。这个模块让 Agent / 脚本能**直接读**这两张表，不用人工导出、也不用开浏览器。

| 文档 | 关键内容 |
|------|----------|
| 2026年下单表 | `2026年度订单明细`（一行 = EN销售订单编号 × 通途SKU，含工厂四件套）、`物流信息表`（通途采购单号 → `ZMT…` 物流号） |
| 发货信息总表 | `物流跟踪Tracking`（批次号 → 离港/到港/入库）、美东/美中/欧洲/FBA 的下单表与发货明细 |

## 怎么用

```bash
# 先列 sheet，确认表名
uv run python dingtalk/dingtalk_sheet/read_table.py \
    --url "https://alidocs.dingtalk.com/i/nodes/<baseId>" \
    --operator-env DINGTALK_OPERATOR_ID --list

# 读整表（推荐）
uv run python dingtalk/dingtalk_sheet/read_table.py \
    --url "https://alidocs.dingtalk.com/i/nodes/<baseId>" \
    --sheet "2026年度订单明细" --all --out /tmp/导出.xlsx
```

**凭证**：需要钉钉企业内部应用的 Client ID/Secret + **operatorId（操作人 unionId）**，
且该人须对目标文档有权限 —— 不同文档可能要不同人的 unionId。详见
[AGENT_HANDOFF.md](AGENT_HANDOFF.md) 与 [.env.example](.env.example)。

> unionId 属个人信息，**只放本机 `.env`，不进仓库**。

## 已知限制

- **只读**。
- 钉钉表格的**合并单元格只写首行**（批次号这类列要向下填充）。
- 服务端**会偶发瞬时错误**（503 / `404 uuid not exist`），已内置退避重试；
  但**整张文档持续 404** 时是文档侧问题，重试救不了。
- 单次读区域上限 **30000 单元格**；接口会用**空行把请求区域补满**，
  所以数行数必须用 `--all`（详见 [docs/reference/dingtalk-sheet-api.md](docs/reference/dingtalk-sheet-api.md)）。

## 文档

| 你想知道 | 读这个 |
|----------|--------|
| 怎么用 / 有哪些坑 | [AGENT_HANDOFF.md](AGENT_HANDOFF.md) |
| API 细节、两张表的结构、外部调研来源 | [docs/reference/dingtalk-sheet-api.md](docs/reference/dingtalk-sheet-api.md) |
| 文档索引 | [docs/index.md](docs/index.md) |
| 变更历史 | [docs/log.md](docs/log.md) |
