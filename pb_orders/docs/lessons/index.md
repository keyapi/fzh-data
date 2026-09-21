---
okf: v0.1
type: Index
title: pb_orders 经验教训
tags: [pb, orders, lessons, index]
timestamp: 2026-09-21
---

# 经验教训

## L1. pandas 3.0 下 Colab 写法会直接报错，且有一处会静默失效

迁移 Colab（pandas 2.x）代码到本仓库（pandas 3.0.2）时踩到三个点：

| 写法 | pandas 3.0 结果 | 正确写法 |
|------|----------------|---------|
| `df.fillna(method='ffill')` | 已删除，报错 | `df.ffill()` |
| `df.groupby(k).apply(lambda x: x.ffill(), include_groups=True)` | `ValueError: include_groups=True is no longer allowed` | —— |
| `df.groupby(k).ffill()` | 能跑，但**分组键被丢掉**（后续 `sort_values(['PO Number'])` → `KeyError`） | `pd.concat([keys, df.groupby(k).ffill()], axis=1)` |
| `df['列'].fillna('', inplace=True)` | 能跑，但 CoW 下**静默不生效**（列值没变） | `df['列'] = df['列'].fillna('')` |

**教训**：跨 pandas 大版本迁移，不能只看"有没有报错"——`groupby.ffill()` 丢列、
`fillna(inplace=True)` 失效都属于**能跑但结果是错的**，必须用真实数据对行数/列数做断言。

**Why**：groupby 的 `apply` 在 3.0 默认 `include_groups=False`（键不进函数），
而 `groupby().ffill()` 作为 transform 返回时同样不含分组键；`inplace` 在 Copy-on-Write 下作用于临时副本。

## L2. pypdf 的 `copy(page)` 不隔离 `/Contents`，`scale_by` 会污染同源拷贝

notebook 里对同一页做两份裁切用 `from copy import copy; pageCopy1 = copy(page)`。
迁到 pypdf 6.x 后输出**标签页被缩小成 0.732 倍**（和打包单一个倍率），
但页面的 mediabox 却是对的 —— 说明 `scale_by` 缩放的是**内容流**，而两份拷贝共用同一个 `/Contents` 间接对象。

实测：`copy(p)` 后 `c1 is c2 == False`、`c1.mediabox` 与 `c2.mediabox` 互相独立，
但 `c1.get("/Contents") is c2.get("/Contents") == True`。

我先后试了三条路，前两条都是坑：

1. ❌ 「页交给 writer 后再给克隆的 `/Contents` 调 `scale_by`」→
   `ValueError: Cannot update PdfReader with external object`（`scale_by` 内部走
   `replace_contents` → `_replace_object`，只能改归属该 reader 的对象）。
2. ❌ 「两趟处理、每趟重新打开源文件、各写一个中间 PDF，再交替合并」→ 结果正确，但
   **同一张图在成品里存了两份**：图片对象 130→260、体积 12.8MB→24MB（超出邮件附件限制）。
   顺手试了 `PdfWriter.compress_identical_objects()`，只把 260 压到 181，仍不达标。
3. ✅ 「**同一个 `PdfReader` 只读一遍**，两份拷贝只改页字典；缩放自己实现」——
   `_scale_boxes_about_origin` 缩放各 box、`_prepend_scale_matrix` 往内容前置 `cm` 矩阵，
   图片资源保持共享。实测 130 个图片对象 / 13.0MB，与 Colab 一致，且比中间文件方案快 25 倍。

**Why**：`merge_page` 和 `scale_by` 都是**就地改写**页的 `/Contents`；
只要两页指向同一个流，一次改写就同时影响两页。而"让两份各自独立"最省事的做法（复制成两个文件）
会顺手把图片也复制一遍 —— 独立性和体积是**两个**约束，得同时满足。

## L3. 视觉"看起来不对"要先量几何，别靠肉眼

一开始我肉眼比对渲染图，觉得"我的标签左边被裁掉更多"，怀疑裁切坐标错了。
实际量下来：mediabox / cropbox / `/Rotate` **完全一致**，只是两天的订单地址文本长度不同，
同一个绝对裁切点自然切在不同字符上。

**教训**：比对打印件是否一致，先比 `mediabox/cropbox/rotate` + 图片 bbox + 渲染像素尺寸，
这几项一致基本就等价；肉眼比对内容只会被"内容本身不同"误导（不同订单的标签本来就不同）。

## L4. 「无货 SKU」在 Colab 里是死代码

cell 13 的参数是 `#@param {type: "string"}` 的**字符串** `"['A','B']"`，
而代码是 `[sku.lower() for sku in zero_stock_skus]` —— 遍历字符串得到的是**单个字符**，
再 `isin()` 自然永不命中。所以过滤从未生效，历史文件夹里也只有 `PB_0_导入_原始_`、从无 `PB_1/PB_2`。

**教训**：接手老脚本时，先确认某个分支**是否真的会执行**（看历史产物有没有对应文件），
再决定"照搬"还是"修好"。这次两件事都做了：默认留空保持与现状等价的不过滤行为，同时把参数解析修成真正可用。

## L5. 凭证不落仓库：worktree 下要向上找父仓库

Colab cell 29 **明文硬编码了服务账号私钥**。迁到本地时改读
`secrets/gsheets-service-account.json`，但 gitignore 的 `secrets/` 只在**父仓库**存在
（见 `CONCEPTS.md`「凭证在父仓库不在 worktree」），共享 helper 的 `REPO_ROOT` 在 worktree 里指向 worktree 根，
于是构建路径 / 读取都会失败。

**解法**：先尊重用户已设的 `GSPREAD_SERVICE_ACCOUNT_FILE`，其次用共享 helper 的路径，
都没有就从模块目录**逐级向上**找 `secrets/gsheets-service-account.json`，找到就写进环境变量给共享 helper 用。

## L6. Colab 参数里的「人类备注」比代码更危险

backup 里的 3 个历史无货 SKU（如 `CEN803NLINEN-BLACK-138`）看着像配置，实际因为 L4 从来没生效，
所以"它一直放在里面也没影响"。同一天实测：这 3 个 SKU 的 ASN 实发数量与订单数量**完全相等**（都发了）。
若照抄参数并"顺手修好"过滤，就会误删 6 件实发订单。

**教训**：把老参数从"看着有用"改成"真的有用"之前，先用独立数据源（这里是 ASN 发货 CSV）验证参数当下是否仍然成立。

## L7. 迁移代码时，"保持列类型"也是保真的一部分

逐单元格对比新旧产物时，5000 个单元格里只有 50 处不同：`PO Line #` 我是 `1`、Colab 是 `'1'`。
原因是我为了排序稳妥加了一句 `pd.to_numeric(df['PO Line #'])`，把整列从字符串变成了整数。

notebook 本来就按**字典序**排序（而且 `dtype` 里明确声明了 str），所以这一句既没必要、又改变了导出值。

**教训**：迁移时任何"顺手加固"都可能改变输出；凡是要动的，先过一遍"原实现怎么做的 → 我改了什么 → 产物会不会变"。
验收靠逐单元格 diff，不靠肉眼扫。

## L8. 最好的验收标准是老工具自己的输出，而不是"看起来对"

本次碰巧用户当天已经用原 notebook 跑过同一批数据并把结果放在 `20260921/Colab处理/`，
于是能做真正的 A/B：

- 通途 xlsx 逐单元格 diff → 5000 个单元格 **0 处不同**
- 背贴 PDF 渲染像素 diff（200dpi）→ **完全相同**，连文件字节数都一致
- 标签 PDF 像素 diff → 差异**只剩时间戳那一条竖带**（我的运行时刻 vs Colab 的 16:44），
  差异区域的坐标范围（x 382..396）正好证明"只差时间戳"

**教训**：迁移类任务的黄金标准是「同一输入，新旧工具输出是否等价」。
只要有可能拿到老工具自己的产物，就别满足于"我自己看着没问题"——
本次正是靠它才发现 `copy(page)` 的缩放污染和 `PO Line #` 的类型漂移两个真实缺陷。
差异像素的**空间分布**（而不是差异比例）才是判定"差异是否可解释"的关键。
