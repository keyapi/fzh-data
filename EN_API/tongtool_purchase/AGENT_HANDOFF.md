# 销售出库单 → 通途采购单（已实现，测试环境）

> 2026-09-16 实现并部署到测试服务器 `sh-erpnext-test`（site `erpnext.vilavi.cn`）。
> 需求全文见同目录 `需求记录-销售出库创建通途采购单.md`。

---

## 一、交付物

| 文件 | 位置（服务器） | 本仓库镜像 |
|---|---|---|
| 业务逻辑 | `apps/delivery_plan/delivery_plan/utils/tongtool_purchase.py` | `EN_API/tongtool_purchase/tongtool_purchase.py` |
| whitelist 入口 | `apps/delivery_plan/delivery_plan/api/tongtool_purchase_api.py` | `EN_API/tongtool_purchase/tongtool_purchase_api.py` |
| 前端按钮 | `apps/delivery_plan/delivery_plan/public/js/delivery_note.js` | 片段见 `delivery_note_button.js` |
| 采购配置 | **不新增单据**：4 个 Custom Field 加在 `Tongtool Settings` 上 | — |

回写字段（Delivery Note 自定义字段）：`custom_tongtool_purchase_order`（通途单号）、
`custom_tongtool_po_created_on`（创建时间）。

改动前的 JS 备份：`public/js/delivery_note.js.bak_20260916_094305`。

---

## 二、采购配置（上线前必须填）

**不新增单据** —— 配置放在 `tongtool_integration` 的 `Tongtool Settings` 上，
路径 `/app/tongtool-settings`。加了 4 个 Custom Field + 1 个 Section Break：

> ⚠️ 版面位置：这 5 个字段用 `custom_purchase_section`（Section Break「通途采购配置」）
> 挂在表单**末尾**（`insert_after = start_refresh_sale_button`）。
> **不要**把它们插到 `api_base_url` 之类的位置——那段是两栏布局的右栏，
> 插进去会把 `test_connection_button` 挤走、整块错位（2026-09-16 踩过，已修正）。

| 字段 | 类型 | 内容 |
|---|---|---|
| `custom_purchase_section` | Section Break | 分组标题「通途采购配置」，必须在最前 |
| `custom_purchase_currency` | Data | 币种，默认 `USD` |
| `custom_purchase_users` | Small Text | 采购员，每行 `名称=通途purchaseUserId` |
| `custom_purchase_warehouses` | Small Text | 仓库，每行 `名称=通途warehouseIdKey` |
| `custom_purchase_suppliers` | Small Text | **已弃用（仅兜底）** —— 供应商改为从通途实时拉取，见下 |

> **供应商不写死在配置里**（2026-09-16 业务方要求：供应商不固定）。
> `get_purchase_options` 会调通途 `supplierQuery` **实时拉取全部供应商**（当前 320 家），
> 结果按客户端 TTL 缓存。配置里的这个字段只在通途拉取失败时当兜底。
> 操作员在弹窗里从完整列表选。
>
> 供应商能实时拉、采购员不能：员工类接口全部 524 无权限，所以采购员仍需人工维护 ID。

格式说明：每行一条 `名称=通途ID`；空行和 `#` 开头的注释行会被忽略。
名称是显示用的 label（弹窗里就是这个），右边才是传给通途的 ID。

当前已填内容：

```
custom_purchase_currency   = USD

custom_purchase_users      = 袁新春=201611040003130857      ✅
                             彭建=202409230008048933        ✅

custom_purchase_warehouses = 美东-CENTRADE=6464013595201610250000002538          ✅
                             波兰-FZHPoland-covers=6464013595202111220000516093  ✅
                             美中-FZH-DANEEY=6464013595202309080001023362        ✅

custom_purchase_suppliers  = （已弃用，供应商实时拉取）
```

> **采购员 ID 怎么来的**：通途员工类接口全部 524 无权限，公开 API 查不到。
> 最后是让人在通途里把一个货品的「采购员」从下拉里选成目标人，
> 再用 `goodsQuery` 读该货品的 `purchaserId` 拿到的。这个字段跟"采购员下拉"是两套东西
> —— 下拉选人写进去的才是对的 ID。**名字和网页上的 `_UID_` 传进去都会报 527。**

---

## 三、业务规则（已实现）

**按钮**：销售出库单已提交（docstatus=1）时显示，挂在「工具」下。
只有 `CENTRADE` / `DANEEY` / `波兰公司` 可点，**其余客户按钮置灰**。

**客户 → 客户组**（决定取哪个客户物料号）：
`CENTRADE`/`DANEEY` → 美国公司；`波兰公司` → 欧洲公司。

**明细行处理**：

| 行 | 规则 |
|---|---|
| **成品** | Item 上有客户物料号 → 取该客户组的**基码** |
| **皮壳**（`item_code` 以 `PK#` 开头） | 去掉 `PK#` 找对应成品 → 再取成品的客户物料号（同样取基码） |
| 海绵 | **暂不处理**（业务方要求后期再加） |
| 内胆/扣子/套件#/配件 | 跳过 |

两条关键细节：

- **取基码**：同一客户组下可能同时有基码和 `-Cover` / `-Foam` 码，代码只取不带这些后缀的那条。
- **只认目标客户组**：该组没登记就判为"未匹配"，**不退回别的客户组**，避免采购错货。

**创建采购单参数**：

| 通途字段 | 取值 |
|---|---|
| `purchaseUserId` | 配置表「采购员」 |
| `warehouseIdKey` | 配置表「仓库」 |
| `supplierId` | 配置表「供应商」 |
| `currency` | 配置表 currency（默认 USD） |
| `externalNumber` | **DN 的 `logistic_number`（物流单号）** |
| `shippingFee` | **DN 的 `logistic_cost`（总运费）** |
| `goodsDetail[].quantity` | DN 明细行 qty |

创建成功后把通途采购单号回写到 `custom_tongtool_purchase_order`。

---

## 四、三个接口

`delivery_plan.api.tongtool_purchase_api`：

| 方法 | 作用 | 写数据 |
|---|---|---|
| `get_purchase_options()` | 返回配置表的采购员/仓库/币种 + **通途实时拉取的供应商** + 支持客户列表 | 否 |
| `preview_purchase_order(delivery_note)` | 解析明细 → 通途货品，返回匹配行 + **合并合计** + **未匹配行** | 否 |
| `create_purchase_order(...)` | 调 `purchaseOrderCreate` 并回写单号（**按货品累加数量后**再发） | **是** |
| `reset_purchase_order(delivery_note)` | 清空单号，**仅当通途那边已作废（status=4）** | **是** |

### reset_purchase_order（清空单号）

业务规则：**只有通途已作废的采购单才允许清空单号**，避免误清还在执行的采购单。

- 通途采购单状态：`0` 等待到货 / `1` 部分到货等待剩余 / `2` 部分到货不等待剩余 / `3` 全部到货 / **`4` 作废**
- 查不到该单号 → 拒绝（宁可让人先去通途确认）
- 未作废 → 拒绝，并把当前状态码回显给用户
- 前端：「创建通途采购单」按钮在有单号时会先确认，再调这个接口；成功才继续走创建流程

### 数量按货品合并

同一 `goodsDetailId` 的多行会合并成一行、数量累加后再发给通途。
销售出库常把同一物料拆成多行（同款不同批次/调拨来源），不合并会在通途建出一堆重复行。
预览弹窗里会额外显示「实际将采购（按货品合计）」表。

未匹配行（皮壳找不到成品、客户组没登记、通途查不到 SKU）会**显式列在弹窗里**，不静默丢弃。

---

## 五、已知约束

- 通途**同商户所有 App 共享 5 次/分钟**限流；客户端用 `time.sleep()` 退避，
  526 重试 15+30s，**单次实测卡 46 秒**。货品映射有缓存（热 0.00s），冷缓存首次会慢。
- 未授权的接口按网络异常重试 3 次，**可能卡十几分钟**（踩过：`userInfo/query` 401）。
- 通途**没有更新采购单外部流水号的接口**，所以 `externalNumber` 只能创建时定，
  事后改不了。业务方已确认取"点击当时的物流单号"。

---

## 六、怎么改怎么部署

```bash
# 服务器
cd /home/frappe/frappe-bench
sudo -n -u frappe /usr/local/bin/bench --site erpnext.vilavi.cn clear-cache   # 只改 JS
sudo -n -u frappe /usr/local/bin/bench restart                                # 改了 .py
```

- 改 JS → `clear-cache` + 浏览器硬刷新即可（`sites/assets/delivery_plan` 软链直指 app 的 `public/`）。
- 改已导入的 `.py` → **必须 restart**，否则 worker 里还是旧代码。
- 新增 DocType → 需 `bench migrate`（本次实现**没有**新增 DocType，配置是 4 个 Custom Field）。

---

## 七、验证状态（2026-09-16）

| 项 | 结果 |
|---|---|
| `get_purchase_options` | ✅ HTTP 200，3 仓库真实 ID + 2 采购员 + 供应商占位 |
| `preview_purchase_order`（DN-26-00040，CENTRADE） | ✅ 成品 `KS0001-DM-194-YELLOW` → `CENKZ1325-Yellow-194`（**正确避开 `-Cover`**） |
| 同上，皮壳行 | ✅ `PK#KS0001-HLR-194-TAN` → 取自成品 → `CENKZ15339432-Ivory-200`（**从 2 个 `-Cover` 码中正确取基码**） |
| 未匹配行 | ✅ 为空 |
| TODO 守卫 | ✅ 用占位值调 create 被明确拦下，不会误建单 |
| JS 语法 | ✅ `node --check` 通过；assets 软链已生效 |
| **按钮的浏览器实际渲染/点击** | ❌ **未验证**（Chrome 扩展未连接）。需人在页面上点一次 |
| **真实创建采购单** | ❌ **未验证**，需先把配置表里的 TODO 填成真实 ID |

### 联调测试数据（都在测试站，非生产）

- Item `KS0001-DM-194-YELLOW`、`KS0001-HLR-194-TAN` 补了「美国公司」客户物料号
  （含 `-Cover` 码，用于验证取基码）
- 验证用单：**DN-26-00040**（CENTRADE，已提交，含 1 行皮壳 + 3 行成品）

---

## 八、下一步

1. **业务方**：从通途后台取 袁新春 / 彭建 的 `purchaseUserId` 和供应商 `supplierId`，
   填进 `/app/tongtool-settings` 的「采购员」「供应商」两个多行字段（`名称=ID`）。
2. **人工**：在测试站打开 DN-26-00040，点一次「创建通途采购单」，确认按钮渲染、弹窗、
   预览、错误提示都正常。
3. 上述 OK 后再做一次真实创建，回通途界面核对采购单号/供应商/仓库/数量/单价。
4. 生产部署：生产 SSH 可达（`ssh 阿里云-FZH-ERPNext-frappe`，见 `EN_API/docs/reference/en-server-access.md`），可直接登录同步 app 源码，不必等运维代劳。
