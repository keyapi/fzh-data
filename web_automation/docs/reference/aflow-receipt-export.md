---
okf: v0.1
type: Reference
title: 钉钉 aflow「销售收款确认单」单据与附件导出
description: aflow 数据管理控制台的选择器、导出流程（异步任务→操作记录→下载）、产物结构、附件路径与踩坑。MCP 探路记录，尚未沉淀为脚本。
tags: [dingtalk, aflow, oa审批, 销售收款确认单, 导出, 附件, 选择器, 探路]
timestamp: 2026-09-10
status: scripted-and-verified
---

# aflow「销售收款确认单」导出探路

**状态：已沉淀并端到端跑通**（`dingtalk.aflow.receipt.export`，
`legacy-compatible/dingtalk_aflow_receipt.py`，2026-09-10 实测 `status=READY`）。
本文件是耐久产物；`.playwright-mcp/` 里的截图/DOM dump 是临时的。

## 入口与登录

- 目标页：`https://aflow.dingtalk.com/dingtalk/web/query/dashboard?dinghash=aflowSetting#/aflowSetting/dataManage?tabKey=default`
  页面标题 = **OA审批管理后台**。
- **直接打开 aflow 会撞登录墙**：跳到 `error.vm?error=您的登录已过期，请退出后重新登录`，该页**没有任何登录控件**。
- 正确入口是 **先走 `oa.dingtalk.com`**：
  1. `https://oa.dingtalk.com/index.htm`
  2. 302 到 `https://login.dingtalk.com/oauth2/challenge.htm?...&client_id=dingoaltcsv4vlgoefhpec&scope=openid+corpid&org_type=management`
  3. 默认 **扫码登录** tab（`tablist` 里 `账号登录` / `扫码登录`）
  4. 扫码后出现**组织选择页** `.app-page-curr`（"选择你管理的组织"），点组织名（本环境：**方州汇国际** / 新华三路由器测试）
  5. 落到 `oa.dingtalk.com/index.htm#/welcome`
- 登录后 **SSO 覆盖 aflow**：再打开 aflow URL 即正常渲染。
- **一键头像登录（"点击头像授权登录"）不可用**：登录页轮询 `http://127.0.0.1:8441|8442|8443/check_state`，而本机钉钉客户端只监听 **`127.0.0.1:8440`** → 三个请求全部 `ERR_CONNECTION_REFUSED`，头像点击后停在"登录中"然后静默回落。要用一键登录需把钉钉客户端升到与登录页匹配的版本。
  - 但**头像能显示出来**（页面确实拿到了账号 张克勇），说明本地客户端通道部分可用；最终成功仍走的是扫码。

> 选择器定位坑：登录页是 SPA，DOM 里**同时存在几十个隐藏面板**，且隐藏面板的子元素 `getBoundingClientRect()` 仍然非零，"可见性"自检会误判。
> 唯一可靠的活面板是 **`.app-qr-login-page`**（类含 `app-page-curr`）。改版后要按这个思路重新定位。

### 一键头像授权可以脚本化（2026-09-10 实测跑通）

脚本里已实现（`try_avatar_login` + `pick_org`）：

1. 勾选 `.app-qr-login-page .base-comp-check-box-rememberme-box`（第 0 个 = 自动登录）
2. 点 `.app-qr-login-page .module-qrcode-user-avatar`
3. 组织选择页出现后，点 `.app-page-curr :text-is("<组织名>")`

**唯一脚本够不到的一步**：Chrome 会弹原生权限气泡
「`login.dingtalk.com` 想要**访问此设备上的其它应用和服务**」——
这是浏览器自己的 UI，不在网页 DOM 里，Playwright 点不到，**必须人工点【允许】**。
好消息是它**按 profile 记住**，只需点一次；点过之后本机钉钉客户端通道打开，头像才会出现。

实测：`web_automation/dingtalk-profile` 建好并点过一次允许后，
脚本第二次运行**全程零人工**（`已勾选自动登录并点击头像` → `已选择组织：方州汇国际` → 直接导出）。

## 表单筛选（数据管理 → 数据查看）

| 控件 | 选择器 | 说明 |
|---|---|---|
| 表单名称（级联，必填） | `.ant-select-selection-search-input` nth=0 | **二级级联**：先选 `已启用`/`已停用`/`无权限`，再选表单 |
| └ 一级 | `.ant-cascader-menu-item:has-text("已启用")` | 三个状态之一 |
| └ 二级 | `.ant-cascader-menu :text-is("销售收款确认单")` | **必须精确匹配**：列表里有「其他收入收款确认单」「新平台收款确认单」「European Sales Receipt Confirm」等近似名（共 68 项） |
| 发起时间（必填） | `input[placeholder="开始日期"]` nth=0 / `input[placeholder="结束日期"]` nth=0 | **`readOnly`，不能 fill**；外层 `div.dtd-picker.dtd-picker-range` |
| └ 翻月 | `.dtd-picker-header-next-btn` / `-prev-btn`；`-super-next-btn` / `-super-prev-btn` 翻年 | 面板一次显示两个月 |
| └ 选日 | `[title="YYYY-MM-DD"]` | 点开始日后面板自动前移一个月 |
| 查询 | `button.dtd-btn-primary:has-text("查询")` | 查询失败/空结果时**不要**继续导出 |

- 同一页有**两对** `开始日期/结束日期`：**发起时间**是第 0 对，**完成时间**是第 1 对 → 必须用 `nth` 消歧。
- 页面加载后会弹**两个弹窗**，必须先关：`智能OA试用已过期`（点 `button.dtd-modal-close`）和 `新增搜索功能`（点 `button.upgrade-guide-button:not(.button-primary)`，即「稍后升级」）。

## 导出 Excel（异步任务）

1. `button:has-text("导出全部")` —— **点按钮本体 = 立即触发导出，没有下拉菜单**。
2. 弹窗：**「数据正在导出… 导出进度可在「操作记录」中查看」** → `关闭` / `查看进度`。
3. 「查看进度」跳到 `#/aflowSetting/dataManage?tab=export&tabKey=record`。
4. **操作记录 → 导出记录**，列为：`导出文件名称 | 导出方式 | 操作人 | 导出时间 | 导出表单 | 进度 | 操作`。
   - `导出方式` 取值：`管理后台导出`（Excel）/ `附件下载`（附件）/ `前台导出`
   - 别人导的显示「无权限下载」
5. 行内 `下载`（span，无 href，JS 处理）→ 触发下载。**列表按导出时间倒序，最上行 = 最新**。
   - 选择器：`text=下载 >> nth=0`（`tr:has-text(...)` 那句会被 strict 模式/解析拒绝，实测不行）。
6. 文件名固定为 **`销售收款确认单-<YYYYMMDDHHMMSS>.xlsx`**。

### 下载落到哪（重要）

Playwright MCP 的下载写在 **MCP server 进程的 cwd** 下的 `.playwright-mcp/`，
**不是**你的 worktree、也不是浏览器默认下载目录。本次落在
`D:\Work\赛狐\Cursor\.claude\worktrees\recursing-wozniak-35c919\.playwright-mcp\销售收款确认单-20260910152730.xlsx`。
→ 沉淀脚本时必须用 `download.save_as()` **显式指定目标路径**，不能依赖 MCP 的落点。

## 导出产物结构（实测，与历史件一致）

- **2 个 sheet**，名字是**模板 id**（本环境 `202606291156000004` / `202606291156000005`）——**不可当作稳定标识**。
- **表头是 2 行**：
  - **第 1 行**（23 个非空）= 审批元数据 + 明细表的**合并组标题**：
    `序号, 数据id, 审批编号, 标题, 审批状态, 审批结果, 发起时间, 完成时间, 耗时(时:分:秒), 发起人工号, 发起人UserID, 发起人姓名, 发起人部门, 历史审批人姓名, 审批记录, 当前处理人姓名, ...收藏, 账期明细, 图片, 评论附件汇总, 所有附件汇总`
  - **第 2 行**（83 个非空）= 明细子字段：`选择平台, 账期日期, 亚马逊注册账户, AMZCTRD账户, AMZVer账户, AMZJohna账户, ...`（合并区 `Q1:CU1`）
  - 单列是纵向合并（`C1:C2`、`E1:E2`…）
- **数据从第 3 行开始**，共 **105 列**。
- ⚠️ **「第 2 行是空行」是错的**。只检查前 16 列会得出这个结论；第 2 行在 17 列往后全是子表头。
  裸 `pd.read_excel` 会把第 1 行当表头并错位——需 `header=0, skiprows=[1]`（或 openpyxl 显式取第 3 行起）。
- **同一单据会因「收款账户明细表」重复成多行** → **单据数必须按唯一 `数据id` 计**：
  本次窗口 **405 行 / 265 个单据**。

### 与 API 路径的对应关系（已交叉验证）

- 导出里的 **`数据id` == 钉钉 `processInstanceId`**：
  本次 265 个 `数据id` 与 `dingtalk_oa_approval` 的 `instance_ids.json`（441 个，窗口从 2026-06-01 起）
  **265/265 完全重合**；差集只在 API 侧（176 个，因窗口更宽）。
- 导出是**原始**数据：含 `已撤销`（本次 37 行），`keep_approval` 过滤仍归下游 `dingtalk/parse.py`。

## 附件路径

### 批量：hover，不是 click

`导出全部` 按钮上 **hover**（不是点击）会浮出下拉菜单，**只有一个选项**：

- **`仅导出审批单附件`** → `.dtd-dropdown-menu-item:has-text("仅导出审批单附件")`
- 旁边 popover 文案「将审批单数据汇总导出到一张 Excel 中」描述的是**默认动作**，不是这个选项。

点击后弹窗：**「附件正在下载至【云盘-团队文件】… 下载进度可在【操作记录】中查看」**
→ **产物进钉盘（云盘-团队文件），不是本地 zip**（与官方帮助文档一致的第二跳）。
该任务在「导出记录」里以 **`导出方式 = 附件下载`** 出现，完成后才有操作列。

> 本次实测：任务**能完成**。在「导出记录」里先是 `96%`（**列表不自动刷新，且用 `goto` 同一个 URL 不算重载**——
> SPA 只变 hash 不会重新请求；必须 `page.reload()` 或切 tab），真重载后显示 **已完成**。
>
> **但 `附件下载` 行的 `下载` 拿不到本地文件**：点了没有任何下载事件，控制台报
> `ERR_TOO_MANY_REDIRECTS @ https://aflow.dingtalk.com/` + React error #31。
> 与弹窗文案一致——**产物在钉盘【云盘-团队文件】，不走浏览器下载**。
> 要落地必须**再去驱动钉盘**，本次**未打通**。

**钉盘探测结果（2026-09-10）**

- `pan.dingtalk.com` **不解析**（`ERR_NAME_NOT_RESOLVED`）。
- 钉盘/团队文件网页版入口是 **`https://alidocs.dingtalk.com/`**（"钉钉文档"），
  左侧导航有 `首页 / 我的文档 / 团队文件 / 知识库`；右上角能显示组织 `方州汇国际` 与头像，说明会话有效。
- 但**点 `团队文件` 不切换视图**：试过 `text=团队文件 >> nth=0`、
  `.nav-title-text:text-is("团队文件")`、`div.nav-item-box:has-text("团队文件")`（最后一个直接 no match），
  页面都停在 `#/i/desktop` 的"最近"。**未能进入团队文件**，故没看到这次批量下载产出的文件夹。
- 官方帮助中心的说法是：**`【操作记录】→【批量下载】→【去下载】`** 跳到云盘团队文件。
  但 **aflow 的操作记录没有「批量下载」子 tab**（只有 `导出记录 / 历史导出记录 / 批量打印记录 / 删除记录`）。

**⚠️ 「回 oa.dingtalk.com 老控制台」这条路不存在（已证伪）**

在 `oa.dingtalk.com` 首页搜索「OA审批」→ 点应用，落到的 URL 是：

```
https://oa.dingtalk.com/dingtalk/web/query/dashboard?dinghash=aflowSetting#/aflowSetting?lang=zh_CN&nation=CN&code=<orgCode>
```

**同一个 SPA**（`/dingtalk/web/query/dashboard`），左侧同样是
`表单管理/数据管理/应用管理/集成开放/OA自定义/电子签章/系统管理/跨组织管理/版本管理`。
即 **`oa.dingtalk.com` 和 `aflow.dingtalk.com` 是同一套控制台的两个域名**，**没有独立的"老控制台"**，
帮助文档描述的界面在这套新控制台里**没有对应入口**。

补充：直接深链到 oa 域名下的操作记录页**打不开列表**（需要 `code=` 参数；
不带参数时页面停在未初始化的空壳，`a.export-file-download` 数量为 0）。

**结论**：aflow 批量附件这条路**取不回本地**。附件走下面「API + 深链」。

### 单条：Excel 里的深链

导出 Excel 的 `账期明细 / 图片 / 评论附件汇总 / 所有附件汇总` 四列是**超链接**（显示为「去下载」/「N个附件」），
本次共 **1074 条**，指向按单据的附件预览页：

```
https://aflow.dingtalk.com/dingtalk/pc/pages/dynamic/formservice.htm?corpid=<corpId>
  #/previewAttachments?corpId=<corpId>
    &processCode=PROC-FB234439-0642-451E-A514-20FBEF4A4241
    &processInstanceId=<数据id>
    &componentId=<见下>&relatedId=&rowNumber=&subComponentId=
```

| 列 | componentId |
|---|---|
| 账期明细 | `DDAttachment-K2K7DF54~DDAttachment` |
| 图片 | `DDPhotoField-K2K7DF55~DDPhotoField` |
| 评论附件汇总 | `operation` |
| 所有附件汇总 | （不带 componentId） |

用 openpyxl `cell.hyperlink.target` 读；pandas 读不到超链接。

### aflow 页面**没有**「批量下载附件」

勾选行后工具栏只变成 `导出已选 / 批量打印 / 删除已选`；
行内「更多」只有 `转交 / 撤销 / 删除`；
操作记录只有 `导出记录 / 历史导出记录 / 批量打印记录 / 删除记录`。
官方帮助文档描述的「批量下载附件」在 `oa.dingtalk.com` 老控制台，本次未验证。

## 与 API 路径的分工（不是二选一）

| | API（`dingtalk/dingtalk_oa_approval`） | aflow 页面 |
|---|---|---|
| 入口 | `processCode` + 时间窗 | 浏览器，以**在职管理员**身份 |
| 附件 | 全量，含图片控件，带 manifest/断点续传 | 批量进**钉盘**；或按单据走 `previewAttachments` 深链 |
| 盲区 | **离职发起人 `userNotExist`** | 能覆盖离职发起人 |
| 单调 | `API_ONLY`，快 | `BROWSER_ONLY`，慢、`contract: ui` 易碎 |

**离职缺口实测**：API manifest 里对该 6 人（李雨欣/丁艳蕾/李娜/汪震/吴浩然/李婷婷）共 **199 条 `userNotExist`**，
而这 62 行**都在 aflow 导出里** —— 这正是 aflow 路径的存在理由。

## 踩坑速查

1. **`导出全部` 点击 = 立即导出**；附件选项要 **hover**。误点会多排一个导出任务。
2. 日期控件 `readOnly`，必须走日历面板，不能 `fill()`。
3. 操作记录列表**不自动刷新**，进度要切 tab 才更新。
   **`goto` 同一个 URL（只差 hash）不是重载** —— SPA 不会重新请求，必须 `page.reload()`；否则会一直看到旧的进度值（本次就被 96% 骗了很久）。
4. 导出文件名带时间戳，**导出记录按时间倒序** → 用「最上行」锚定本次任务（同通途订单详情的老教训）。
5. 页面初始两个弹窗必须先关，否则点击被遮。
6. MCP 下载落点是 **MCP server 的 cwd**，不是你的工作目录。
7. 表头是 **2 行**，别只看前 16 列就断定第 2 行是空的。
8. **aflow 按账号记住上次选的表单/日期区间**。再次进入数据管理时，`表单名称` 已显示
   `已启用 / 销售收款确认单`、日期区间也还在 → 脚本必须**幂等**：已符合就跳过，
   否则"显示已选值的 `span.ant-select-selection-item`"会**拦截点击**，报
   `element ... intercepts pointer events` 并一路超时。
9. 点 antd 级联要**点容器** `.ant-select.ant-cascader`，**不要**点内层
   `.ant-select-selection-search-input`（已选值时被上面的 span 挡住）。

## 验证记录（2026-09-10）

- 窗口 `出发时间 2026-07-04 ~ 2026-09-09`，查询返回 **405 行 / 265 单据**；
  `发起时间` 实测 `2026-07-06 10:05:07` ~ `2026-09-09 12:25:30`，**全部落在窗口内** → 筛选生效。
- 落地：`D:\Work\王忠于\成本核算\Amazon&新平台成本 20260704-20260909 销售收款确认单-20260910152730.xlsx`（237,155 B）。
- 与 API `instance_ids.json` 交叉验证 **265/265 重合**。
