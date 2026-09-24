---
okf: v0.1
type: Reference
title: 扫描类脚本防"静默丢数"——反转匹配方向
date: 2026-09-23
category: best-practices
module: pb_reconciliation
problem_type: best_practice
component: tooling
severity: high
applies_when:
  - "写或改靠 glob/通配符扫目录取输入的脚本"
  - "脚本产出要交给财务或下游系统，错数据会一路流过去"
  - "输入文件名由人手从第三方系统导出，可能出现拼写错误或命名漂移"
  - "扫描结果还参与范围判定（截止、分批、分月），漏一个会影响整段"
tags:
  - silent-data-loss
  - glob
  - scanner
  - data-pipeline
  - fail-loud
  - count-reconcile
---

# 扫描类脚本防"静默丢数"——反转匹配方向

## Context

本仓库大量脚本靠通配符扫目录取输入：`stock_init/`、`item_cost_sx/`、`multi_attr_saihu/`、
`warehouse_restock/`、`category/`、`pb_reconciliation/`、`tongtool_order_cost/` 等都是这个形状。
这类"找到多少算多少"的写法有一个共同弱点：**匹配不上的文件会静默消失**——脚本照常跑完、照常出文件，
只是少了几行，没有任何信号。

真实代价（`pb_reconciliation/reconcile_pb.py`，2026-07 数据）：

- `20260730/invoice/invocie x37 ....csv` —— 文件名把 `invoice` 拼成 `invocie`，
  `glob("**/invoice*.csv")` 匹配不到 → **37 张发票 / $2,232.28 直接消失**。
- 更糟的是该日文件夹落在扫描序列中间：当时的口径是"首个 0 付款的日文件夹即停止"，
  该文件夹因匹配不到而"0 付款" → 判定提前停止 → **连带丢掉整个 202608 月份**。
  一个字符的拼写错误，放大了两个数量级。
- 同期 `merge_invoices.py` 也因同一个拼写少合并了 37 张，产生的对账附件已发给财务。

## Guidance

**核心：反转匹配方向 —— 不要"拿通配符去筛"，而是"读全部再判定"。**

1. **枚举而非匹配**
   先 `os.listdir` 列出目录下**所有**文件，再逐个判定该不该用；
   而不是反过来"用 pattern 去筛，筛不到就当没有"。
   前者筛不中会留下"待判定项"，后者筛不中什么都不剩。

2. **显式排除清单，而不是隐式正则**
   把业务上明确不要的东西写成可读的名单：`NotUsed/` 子目录、文件名含 `不用` / `副本` /
   `OA提交` / `未用`。留在名单外的默认**必须**被识别。名单是能被人 review 的；
   `invoice*.csv` 这种通配符不是。

3. **识别不了就停机（fail loud）**
   某个日文件夹的 `invoice/` 下有 `.csv`，却一个都没匹配上 `invoice*.csv`
   → **报错退出**，并把该目录下所有 `.csv` 列出来。
   这是最低成本的补丁：把"静默丢弃"变成"人工看一眼"。

   ```python
   for day_dir in day_dirs:
       inv_dir = os.path.join(day_dir, "invoice")
       if not os.path.isdir(inv_dir) or any(os.path.dirname(f) == inv_dir for f in csvs):
           continue
       others = [f for f in glob.glob(os.path.join(inv_dir, "*.csv")) if "NotUsed" not in f]
       if others:
           problems.append(f"{inv_dir} 下没有任何 invoice*.csv，只有：{[os.path.basename(f) for f in others]}")
   ```
   （`pb_reconciliation/reconcile_pb.py` 的 `collect_day_folders`；`merge_invoices.py` 同款。）

4. **结构断言（自校验）**
   文件名里常常自带元数据，拿它跟文件内容对账：`invoice x37 ....csv` 声明 37 张，
   就读文件数 H 行是否也是 37，不一致就报错。拼写错误往往伴随这种不一致。

5. **"跳过"和"排除"同样要校验，不能只是不处理**
   只要有"这个不纳入"的分支，就顺手断一句"它本该已经被处理过"：
   ```python
   # 锚点之前的日文件夹跳过，但要确认其发票都已在表内，否则就是漏数
   skipped.append((label, len(invs), sorted(invs - old_sheet_set)))
   ```
   否则"跳过"会悄悄变成"漏数"（`reconcile_pb.py` 的 `select_day_folders`）。

6. **每步出报告，数量对账**
   入 N 行 → 出 M 行，N−M 去哪了？逐文件夹打印"发票数 / 已付 / 未付 / 纳入或跳过"，
   差数在报告里可追溯。这与 `AGENTS.md`「把湖煮干」是同一条。

## Why This Matters

- **成本不对称**：静默丢数 → 错文件送到财务 → 事后翻账；报错停机 → 人看一眼再跑。
  后者几乎免费，前者可能要以月计的返工。
- **会放大**：只要扫描结果参与"范围判定"（截止 / 分批 / 分月 / 分页），
  漏一个单元就可能改变整个范围。匹配错误从"少一行"升级成"少一个月"。
- **数量对账是唯一能自动发现的方式**：内容和金额都可能看着"合理"，
  只有张数/行数/小计对不上才会暴露。

## When to Apply

- 新写或改动任何靠 glob / 通配符 / 文件名前缀取输入的脚本。
- 脚本产物交给财务、ERPNext 导入、下游系统——错了会流出去。
- 输入文件名由人手从第三方系统（SPS / 通途 / 赛狐 / 钉钉）导出，命名不受控。
- 扫描结果参与范围判定（"截止到哪天""这个月还是那个月"）。

## Examples

**Before（静默丢弃）**

```python
csvs = [f for f in glob.glob(os.path.join(root, "**", "invoice*.csv"), recursive=True)
        if "NotUsed" not in f]
# 拼错的文件不在这里 → 静默消失；下游照常出文件
```

**After（枚举 + 排除清单 + 未识别即报）**

```python
# 1) 只认日文件夹的 invoice/ 一层（<日文件夹>/878/invoice/ 这类补充子目录天然不查：
#    20260727 的 878 子目录 8 张与当日主导出 100% 交集，是重复副本）
day_dirs = [os.path.join(root, d) for d in sorted(os.listdir(root))
            if len(d) == 8 and d.isdigit() and os.path.isdir(os.path.join(root, d))]
# 2) 每个日文件夹都要能说出"用了哪个文件"；说不出就停机
for day_dir in day_dirs:
    inv_dir = os.path.join(day_dir, "invoice")
    if not os.path.isdir(inv_dir) or any(os.path.dirname(f) == inv_dir for f in csvs):
        continue
    others = [f for f in glob.glob(os.path.join(inv_dir, "*.csv")) if "NotUsed" not in f]
    if others:
        problems.append(f"{inv_dir} 下没有任何 invoice*.csv，只有：{[os.path.basename(f) for f in others]}")
if problems:
    print("扫描发现问题，不写入：")
    for p in problems:
        print("  - " + p)
    return 1
```

实测效果：改完后第一次 `--dry-run` 立刻抓出 `20260727/878/invoice/03-10 invoice x8 ....csv`
（评估后确认是重复副本、应排除），以及 `20260730` 的 `invocie`（真漏数）。
两个都是以前"跑完全绿"的。

## Related

- [PB 对账表月度更新](../workflow-issues/pb-reconciliation-monthly-update.md) —— 本模式的实例来源
- [Excel 交付物金额核对](../tooling-decisions/excel-formula-cells-and-recalc-verification.md) —— 同一轮排查的另一个学习
- `reconcile_pb.py` `collect_day_folders` / `select_day_folders`；`merge_invoices.py` `collect_day_files`
- `AGENTS.md`「把湖煮干」：每步出报告、未匹配记录必须保留、数量对账、列验证全覆盖
