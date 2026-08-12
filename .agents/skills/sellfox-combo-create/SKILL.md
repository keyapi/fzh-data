---
name: sellfox-combo-create
description: >
  赛狐组合商品/套件 SKU 的完整自动化流程：检测底层商品是否存在、查重、
  创建组合 SKU、设置分类、回读校验，以及在线商品/订单配对处理。
  当用户提到"组合商品"、"组合SKU"、"套件SKU"、"TJ#"、"childSkus"、
  "赛狐创建套件"、"底层商品检测"、"组合商品导入"、"套件#分类"或
  "订单配对错误"时触发。
  不要用于普通多属性 SPU 创建（用 multi-attr），不要用于通途有库存三方主线
  （用 missing-products），不要直接改已发货订单包裹配对（API 会拒绝）。
compatibility: >
  需要 SELLFOX_API/client.py 和 sellfox_combo_ops.py；代理 Key 存在根 .env 的
  SELLFOX_PROXY_API_KEY。所有写操作默认 dry-run，--apply 前必须用户确认。
metadata:
  module: SELLFOX_API
  scripts: SELLFOX_API/sellfox_combo_ops.py
  updated: 2026-08-19
---

# 赛狐组合商品/套件 SKU 创建与校验

## Read First

1. `../../docs/solutions/conventions/sellfox-combo-sku-create-pairing-workflow.md` — 本流程的完整背景、API、权限和已建成对象。
2. `../sellfox-api/SKILL.md` — 代理 API 的 Key、账号、curl/Python 用法。
3. `../missing-products/SKILL.md` — 赛狐缺 SKU、缺属性时的三方主线边界。
4. `../multi-attr/SKILL.md` — 多属性 SPU 导入规则，创建普通 SKU 时不要误用组合流程。
5. `../../missing_products/docs/lessons/2026-08-11-tongtu-en-sellfox-mainline-completion.md` — 赛狐属性只能用 Excel 导入的完整复盘。
6. `../../docs/solutions/conventions/tongtu-en-sellfox-instock-sku-mainline.md` — 赛狐对象必须以 EN 产品 item_code 为准的规则。

不要凭聊天记忆或旧 Excel 直接写赛狐。先调用脚本/API 取当前事实。

## 硬约束

- **先 EN，后赛狐。** 赛狐组合 SKU 必须使用 EN 已保存成功并回读确认的 `TJ#...-NNN`；不要用临时代码或预测值。
- 调 EN REST 创建 Product Bundle 时**只传 `items`**（真实存在的底层 item_code + 正整数 qty），不要传临时 `new_item_code`/`new_item_code_name`，不要先 POST 空单再 PUT 补子表。
- 不要 PUT 修改已有套件的组成或编号；组成变化必须新建。空套件、错位编号不能靠重试 PUT 修复。
- 查重以完整 `(item_code, qty)` 为准，不要跳过或自定义编号。
- 编码和名称末尾 `-001/-002/-003` 是正确规则，必须保留。
- 创建组合 SKU 前，**必须先用 `pageList.json` 检测全部底层 SKU 存在**；缺失时停下，先走属性/底层商品创建流程。
- 创建前必须**查重**：组合 SKU 已存在时不重复创建，只回读并校验 `childSkus`、分类、`isGroup`。
- 组合 SKU 的 `isGroup=1`，必须传 `childSkus`，每项包含 `childId`、`sku`、`num`。`childId` 从 `pageList.json` 的底层商品 `id` 获取。
- 分类 `套件#` 已存在（2026-08-11 快照 `fullCid=428697-`）；除非分类确实缺失且用户授权，否则不自动建分类。
- 修改组合 SKU 分类时，`edit.json` 必须带上 `childSkus`，否则 API 返回 `40014 子SKU不能为空`。
- 写操作默认 dry-run；`--apply` 只在用户确认范围后使用。
- 已发货订单的包裹明细不能用 `updateMatch.json` 改配对；赛狐返回 `已发货状态，不能修改商品配对`。在线商品配对仍可用 `matchByMsku.json` 覆盖。
- 如果赛狐缺的是属性簇/属性值，API 没有写端点；生成属性导入 Excel，用户导入确认后才能继续创建 SKU。

## 标准流程

### 1. 定义组合输入

EN 侧的输入必须是**已经保存成功并回读确认**的 Product Bundle。从 EN `Product Bundle` 或用户给的商品组成得到：


- 组合 SKU，例如 `TJ#KS0525x2_KS0526x1_KS0527x1-001`
- 组合名称，例如 `套件#组合式户外沙发-...-001`
- 底层 SKU + 数量，例如 `KS0525-QQFSB-80x80x65-DEEPGREY:1`

EN 侧必须满足：

- `Product Bundle.name == new_item_code == Item.item_code`
- `new_item_code_name == Item.item_name`
- 子表含真实存在的完整底层 SKU 和正整数数量
- 编号与名称均保留末尾 `-001/-002/-003`

REST 创建 Product Bundle 的请求体只有 `items`，例如：

```json
{
  "items": [
    {"item_code": "KS0525-QQFSB-80x80x65-DEEPGREY", "qty": 2},
    {"item_code": "KS0526-QQFSB-80x80x65-DEEPGREY", "qty": 1},
    {"item_code": "KS0527-QQFSB-80x80x65-DEEPGREY", "qty": 1}
  ]
}
```

保存后回读 EN Product Bundle 和上层 Item，确认编号、名称、子表 parent 和组成一致，才允许在赛狐创建组合 SKU。

### 2. 检测底层商品

```bash
cd SELLFOX_API
uv run --project .. python sellfox_combo_ops.py check-bottoms \
  --sku KS0525-QQFSB-80x80x65-DEEPGREY \
  --sku KS0526-QQFSB-80x80x65-DEEPGREY \
  --sku KS0527-QQFSB-80x80x65-DEEPGREY
```

底层 SKU 缺失时，先查该 SPU 是否缺属性：

1. 读 `missing_products` 的赛狐创建规则。
2. 缺属性簇/属性值 → 生成属性管理导入 Excel，交用户导入并确认。
3. 属性就绪后再创建缺失的普通 SKU；普通 SKU 用 `multi-attr` 或 `missing-products` 流程，不走组合 SKU。

### 3. 组合 SKU 查重

```bash
cd SELLFOX_API
uv run --project .. python sellfox_combo_ops.py check-combo --sku "TJ#KS0525x2_KS0526x1_KS0527x1-001"
```

已存在时校验：

- `isGroup == "1"`
- `childSkus` 与目标组成一致
- `fullName` / 分类符合预期
- 若分类不是 `套件#`，执行第 5 步移分类

### 4. 创建组合 SKU

```bash
cd SELLFOX_API
uv run --project .. python sellfox_combo_ops.py create \
  --sku "TJ#KS0525x2_KS0526x1_KS0527x1-001" \
  --name "套件#组合式户外沙发-...-001" \
  --child "KS0525-QQFSB-80x80x65-DEEPGREY:2" \
  --child "KS0526-QQFSB-80x80x65-DEEPGREY:1" \
  --child "KS0527-QQFSB-80x80x65-DEEPGREY:1" \
  --full-cid "428697-"
```

先 dry-run，用户确认后加 `--apply`。脚本会先查重、再检测底层、再创建、再回读。

### 5. 设置分类（如需）

```bash
cd SELLFOX_API
uv run --project .. python sellfox_combo_ops.py set-category \
  --sku "TJ#KS0525x2_KS0526x1_KS0527x1-001" \
  --full-cid "428697-" \
  --apply
```

### 6. 回读校验

每次写入后必须重新 `pageList.json` 回读：

- `sku` 与目标一致
- `isGroup=1`
- `fullCid` 正确
- `childSkus` 数量、SKU、数量一致

### 7. 配对处理

在线商品配对（可覆盖旧错误配对）：

```json
POST /api/order/api/product/matchByMsku.json
{
  "matchList": [
    {
      "msku": "KS0527-Modular Patio Sofa Sets-Darkgray",
      "sku": "TJ#KS0525x2_KS0526x1_KS0527x1-001",
      "shopId": 596841
    }
  ]
}
```

订单包裹配对（仅未发货可改）：

```json
POST /api/packageShip/updateMatch.json
{
  "packageNo": "P2BBA9T735228",
  "orderItemId": "166584092132041",
  "commoditySku": "TJ#KS0525x2_KS0526x1_KS0527x1-001",
  "usedAll": "true"
}
```

已发货包裹返回错误时，不要绕过；报告给用户，请用户在赛狐后台判断能否人工修正。

## API 速查

| 操作 | Endpoint | 关键字段 |
| --- | --- | --- |
| 查底层/组合 SKU | `/api/commodity/pageList.json` | `skus`, `pageNo`, `pageSize` |
| 查分类 | `/api/category/getList.json` | 递归 `childVo` |
| 建分类 | `/api/category/addCategory.json` | `name`, `fullCid` |
| 创建组合 SKU | `/api/commodity/create.json` | `sku`, `name`, `isGroup=1`, `childSkus` |
| 修改 SKU 分类 | `/api/commodity/edit.json` | `id`, `sku`, `name`, `fullCid`, `isGroup`, `childSkus` |
| 在线商品配对 | `/api/order/api/product/matchByMsku.json` | `matchList[].msku/sku/shopId` |
| 订单包裹配对 | `/api/packageShip/updateMatch.json` | `packageNo`, `orderItemId`, `commoditySku`, `usedAll` |

## 权限与代理

- 代理 Key 存根 `.env` 的 `SELLFOX_PROXY_API_KEY`，账号 `sellfox-main`。
- 新开通赛狐权限后若仍返回 `40021 访问的接口暂无权限`，代理内存里的上游 token 是旧的：
  - 登录测试服务器：`ssh -i D:/Work/Aliyun/ssh/aliyun_fzh_erpnext_20240726.pem frappe@8.133.254.66`
  - 重启：`sudo docker restart sellfox-api-proxy`
  - 重启不改变 Key，只清掉旧 token 缓存。
- `create.json` 可写不代表分类/配对接口可写；每个写接口都要先验证权限。

## 完成关口

0. EN Product Bundle 已保存并回读确认；未使用临时编号，未用 PUT 补子表。
1. 底层 SKU 全部存在，或缺失项已按属性 Excel 流程处理。
2. 组合 SKU 不重复创建；创建后回读 `childSkus` 与目标一致。
3. 分类 `套件#` 不重复创建；组合 SKU 的 `fullCid` 已确认。
4. 在线商品配对回读已指向组合 SKU。
5. 已发货订单包裹若拒绝修改，如实报告，不伪造成功。

## 参考

- [组合 SKU 创建与配对方案](../../docs/solutions/conventions/sellfox-combo-sku-create-pairing-workflow.md)
- [赛狐 API Skill](../sellfox-api/SKILL.md)
- [missing-products Skill](../missing-products/SKILL.md)
- [multi-attr Skill](../multi-attr/SKILL.md)
- [赛狐创建属性与 SKU 复盘](../../missing_products/docs/lessons/2026-08-11-tongtu-en-sellfox-mainline-completion.md)
