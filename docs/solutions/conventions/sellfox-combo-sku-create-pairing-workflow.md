---
okf: v0.1
type: Reference
title: 赛狐组合商品/套件 SKU 创建与配对工作流
date: 2026-08-20
category: conventions
module: SELLFOX_API
problem_type: convention
component: development_workflow
severity: high
applies_when:
  - "EN Product Bundle 需要同步为赛狐组合商品"
  - "订单或在线商品的 MSKU 错误配到了组合的一部分"
  - "需要检测赛狐底层商品是否存在、查重并创建组合 SKU"
  - "需要把组合 SKU 放到套件# 分类并回读校验"
tags: [sellfox, combo, sku, bundle, pairing, tj, category, erpnext, product-bundle]
---

# 赛狐组合商品/套件 SKU 创建与配对工作流

## Context

> 边界：本文组合商品只镜像 EN Product Bundle / `TJ#` 套件。三角类 `PK# -> KS x1` 是通途并行期的销售库存代理，不创建 EN Product Bundle，也不得由 `sync-combos` 管理；见 [三角类皮壳共享库存代理](sellfox-cover-shared-inventory-transition.md)。

订单 `111-5169196-2273828` 的 MSKU `KS0527-Modular Patio Sofa Sets-Darkgray` 原本应卖一个由转角、靠背、脚踏组成的组合式户外沙发套件，但赛狐只把它配到了 `KS0526-QQFSB-80x80x65-DEEPGREY`（靠背单品）。

排查确认：

- EN 组合式户外沙发物料组下三个产品都存在：
  - `KS0525-QQFSB-80x80x65-DEEPGREY`（转角）
  - `KS0526-QQFSB-80x80x65-DEEPGREY`（靠背）
  - `KS0527-QQFSB-80x80x65-DEEPGREY`（脚踏）
- 赛狐底层商品也都存在，ID 分别为 `3702816`、`3702793`、`3702770`。
- EN 和赛狐当时都没有这个组合套件。

本次操作完成了一条可复用的链路：EN Product Bundle → 赛狐组合 SKU → `套件#` 分类 → 在线商品配对 → 订单包裹配对（已发货被拒）。

同事 Agent **不要手写 REST**。操作手册 → [combo-ops.md](../../../SELLFOX_API/docs/reference/combo-ops.md)；冻结对象 → [AGENT_HANDOFF.md](../../../SELLFOX_API/AGENT_HANDOFF.md)「EN 套件 / 赛狐组合商品（热区）」。

## Guidance

### 1. EN 侧先登记 Product Bundle

EN 的 `Product Bundle` 由 Jack 在 `work_order_task` app 中扩展：

- 保存时自动生成上层物料编码 `TJ#<前缀1>x<数量>_<前缀2>x<数量>-001`
- 自动创建 Item，物料组为 `套件#`，`stock_uom=套`，`is_stock_item=0`
- 自动生成赛狐「导入组合商品」Excel 模板

### EN REST 规则（2026-08-19 起强制）

创建 Product Bundle 时 REST **只传 `items`**，服务端负责编号、名称和上层 Item：

```text
POST /api/resource/Product Bundle
{"items": [{"item_code": "KS0525-QQFSB-80x80x65-DEEPGREY", "qty": 2}]}
```

禁止：传临时 `new_item_code` / `new_item_code_name`；先 POST 空单再 PUT 补子表；PUT 修改已有套件的组成或编号。创建后 `name = new_item_code = Item.item_code`，`new_item_code_name = Item.item_name`，编号和名称均保留 `-001/-002/-003`。

创建前可以先调用预览接口查重：

```text
POST /api/method/work_order_task.api.product_bundle.get_bundle_serial_preview
```

本次组合的预览结果：

```text
new_item_code: TJ#KS0525x2_KS0526x1_KS0527x1-001
new_item_name: 套件#组合式户外沙发-转角-QQ防水布-80x80x65cm-深灰色x2件_...-001
is_duplicate: false
serial: 001
```

创建 `Product Bundle` 后必须回读，确认子表为 2 转角 + 1 靠背 + 1 脚踏。

### 2. 赛狐底层商品检测

使用 `POST /api/commodity/pageList.json`：

```json
{
  "pageNo": "1",
  "pageSize": "50",
  "skus": [
    "KS0525-QQFSB-80x80x65-DEEPGREY",
    "KS0526-QQFSB-80x80x65-DEEPGREY",
    "KS0527-QQFSB-80x80x65-DEEPGREY"
  ]
}
```

必须拿到每个底层 SKU 的 `id`，创建组合 SKU 时作为 `childId`。缺少任意一个底层 SKU 时停止，先处理属性/普通 SKU 创建。

### 3. 组合 SKU 查重

同样用 `pageList.json` 查询组合 SKU。已存在时不重复创建，只校验：

- `isGroup == "1"`
- `childSkus` 的 `sku`、`num`
- `fullCid` / `fullName` 分类

### 4. 创建组合 SKU

`POST /api/commodity/create.json`：

```json
{
  "name": "套件#组合式户外沙发-转角-QQ防水布-80x80x65cm-深灰色x2件_...-001",
  "sku": "TJ#KS0525x2_KS0526x1_KS0527x1-001",
  "isGroup": "1",
  "fullCid": "428697-",
  "autoCalcWeight": "true",
  "childSkus": [
    {"childId": "3702816", "sku": "KS0525-QQFSB-80x80x65-DEEPGREY", "num": "2"},
    {"childId": "3702793", "sku": "KS0526-QQFSB-80x80x65-DEEPGREY", "num": "1"},
    {"childId": "3702770", "sku": "KS0527-QQFSB-80x80x65-DEEPGREY", "num": "1"}
  ]
}
```

本次创建成功，返回组合商品 ID `3901074`。

### 5. 分类 `套件#`

分类通过 `POST /api/category/addCategory.json` 创建：

```json
{"name": "套件#"}
```

本次创建结果：

```text
id: 428697
fullCid: 428697-
```

分类只创建一次。后续组合 SKU 直接引用 `428697-`。若分类已存在，不再重复创建。

把组合 SKU 从 `未分类` 移到 `套件#` 使用 `POST /api/commodity/edit.json`。组合 SKU 修改分类时**必须**带上 `childSkus`，否则返回：

```text
40014 子SKU不能为空
```

### 6. 在线商品配对

`POST /api/order/api/product/matchByMsku.json`：

```json
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

成功返回空数组 `[]`，表示无失败项。回读在线产品确认 `commoditySku` 已变成组合 SKU。

### 7. 订单包裹配对

`POST /api/packageShip/updateMatch.json`：

```json
{
  "packageNo": "P2BBA9T735228",
  "orderItemId": "166584092132041",
  "commoditySku": "TJ#KS0525x2_KS0526x1_KS0527x1-001",
  "usedAll": "true"
}
```

本次返回：

```text
code=-1 msg=已发货状态，不能修改商品配对
```

这是赛狐的业务限制，不是权限问题。已发货订单的包裹明细在 API 层不可改；在线商品配对已修复，后续新订单走正确配对。

## Why This Matters

- 组合商品必须在赛狐有独立 SKU，否则 MSKU 只能错误配到其中一个子商品，库存、成本、发货和利润归属都会错。
- 创建组合 SKU 必须依赖底层商品真实存在；直接用 SKU 字符串创建会导致后续 `childId` 关系缺失。
- 分类影响赛狐商品管理和导入模板的 `一级分类`；`套件#` 是对 EN 物料组体系的镜像。
- 已发货包裹不能改配对是赛狐硬限制；自动化脚本必须识别并如实报告，不能伪造成功。

## When to Apply

- EN 已建 `Product Bundle`，需要同步创建赛狐组合商品。
- 订单或在线商品的 MSKU 配到了组合的一部分，需要覆盖到完整组合 SKU。
- 同事或 AI 需要完整自动执行：检测底层 → 查重 → 创建 → 校验。
- 赛狐分类、在线配对或订单配对的权限/接口行为需要再次验证。

## Examples

本次 2026-08-11 实际对象快照：

| 对象 | 值 |
| --- | --- |
| EN Product Bundle | `TJ#KS0525x2_KS0526x1_KS0527x1-001` |
| EN 上层 Item | 同 SKU，物料组 `套件#`，单位 `套` |
| 赛狐组合 SKU | `TJ#KS0525x2_KS0526x1_KS0527x1-001`，ID `3901074` |
| 赛狐分类 | `套件#`，ID `428697`，fullCid `428697-` |
| 底层转角 | `KS0525-QQFSB-80x80x65-DEEPGREY`，ID `3702816` |
| 底层靠背 | `KS0526-QQFSB-80x80x65-DEEPGREY`，ID `3702793` |
| 底层脚踏 | `KS0527-QQFSB-80x80x65-DEEPGREY`，ID `3702770` |
| 在线商品 | `KS0527-Modular Patio Sofa Sets-Darkgray`，已配对到组合 SKU |
| 订单包裹 | `P2BBA9T735228`，已发货，API 拒绝改配对 |

## Proxy Permission Pitfall

新开通赛狐权限后如果仍返回 `40021 访问的接口暂无权限`，原因是 `sellfox-api-proxy` 内存缓存了旧的 OAuth access token。重启代理会清缓存且不改变 Key：

```bash
ssh -i D:/Work/Aliyun/ssh/aliyun_fzh_erpnext_20240726.pem frappe@8.133.254.66
sudo docker restart sellfox-api-proxy
```

重启后重新获取 token，新权限立即生效。代理只在赛狐返回 `40001` 时自动刷新 token，`40021` 不会触发。

## 生产修复记录（2026-08-19）

- EN `work_order_task` 已部署 `e2ee454`，生产执行了 `migrate`、`clear-cache`、`bench restart`。
- KS0443 历史事故数据已清理并重建 12 个 Product Bundle：`TJ#KS0443x{2,3,4,5}-{001,002,003}`，草绿/象牙白/骆驼色各 4 个数量档。
- 重建后 `name = new_item_code = Item.item_code`，`new_item_code_name = Item.item_name`，子表 parent 均正确，新上层 Item 的 `do_not_create_auto_machine_part=1`。
- 赛狐 24 个旧组合商品已由用户手动删除；12 个正式组合 SKU 已按本工作流 dry-run -> 用户确认 -> `--apply` 创建并回读，ID `3916249-3916257`、`3916259-3916261`。
- **`FXLSSF3030`**：历史非 `TJ#` 海绵套件（子表 3× HM1510 白色模块；上层 Item 已 `disabled=1`）。脚本 `skip_historical`。**2026-08-20 用户决定暂不重建**；不要改名或按新规则迁移，除非另行授权。
- **KS0003 / KS0395**：2026-08-20 用户确认无问题，不纳入清理待办。

## Verification Checklist

1. 底层 SKU 全部从 `pageList.json` 回读存在，并取得 `childId`。
2. 组合 SKU 不存在时才创建；已存在时**断言** `childSkus` 和分类，不一致则失败而不是跳过。
3. 创建后回读断言 `isGroup=1`、`fullCid=428697-`、`childSkus` 三项一致。
4. `sync-combos` 报告 `input_en == output_rows`，未匹配行留在 `unmatched`。
5. 在线商品回读 `commoditySku` 等于组合 SKU。
6. 订单包裹若已发货，如实报告 `已发货状态，不能修改商品配对`。
7. 属性缺失时先走 Excel 导入，用户确认后才创建 SKU。

## Related

- [赛狐组合 SKU 操作脚本](../../../SELLFOX_API/sellfox_combo_ops.py)
- [combo-ops CLI 参考](../../../SELLFOX_API/docs/reference/combo-ops.md)
- [SELLFOX_API AGENT_HANDOFF（操作入口）](../../../SELLFOX_API/AGENT_HANDOFF.md)
- [sellfox-combo-create Skill（触发词）](../../../.agents/skills/sellfox-combo-create/SKILL.md)
- [赛狐 API Skill](../../../.agents/skills/sellfox-api/SKILL.md)
- [通途有库存 SKU 三方主线补齐惯例](tongtu-en-sellfox-instock-sku-mainline.md)
- [赛狐创建属性与 SKU 复盘](../../../missing_products/docs/lessons/2026-08-11-tongtu-en-sellfox-mainline-completion.md)
- [EN 物料/变体创建惯例](erpnext-item-variant-creation-convention.md)
