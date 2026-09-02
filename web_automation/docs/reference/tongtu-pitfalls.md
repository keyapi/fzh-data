--- 
okf: v0.1
type: Reference
title: 通途踩坑记录 — 19 个踩坑汇总
description: 通途 ERP 浏览器自动化中遇到的 19 个踩坑，含现象、根因、解决方案
tags: [tongtu, pitfalls, playwright, extjs, cookie, encoding, sales-report]
timestamp: 2026-07-07
---

# 通途踩坑记录

## 坑 1：通途数据表格不加载（最关键！）

- **现象**：导出按钮点击后无反应，`expect_download` 超时 90s
- **根因**：通途页面 Bug——togglebutton 显示仓库"已选中"，但 ExtJS 数据表格未实际渲染。`exportExcelPage()` → `exportGoodsBalanceExcel()` → `Cannot read properties of undefined (reading ''table'')` → 静默失败
- **排查过程**：
  1. 改用 `page.evaluate("exportExcelPage()")` 直接调 JS → 报错暴露真因
  2. MCP 实测点击有效 → 排除 selector 问题
  3. 用户观察：先切走再切回，数据就加载了
- **修复**：`select_warehouse()` 中如果已选中，先切到其他仓库等 3s，再切回来等 8s

## 坑 2：Cookie 加密

- **现象**：SQLite 直接读 `chrome-profile/Default/Network/Cookies` → cookie 值为空
- **原因**：Chromium 用 Windows DPAPI 加密 cookie value
- **解决**：Playwright `launch_persistent_context` + `context.cookies()` 获取解密值

## 坑 3：Session cookie 无法持久化

- **现象**：注入所有 cookie 后，`JSESSIONID` 仍然缺失
- **原理**：JSESSIONID 无 expires（session cookie），浏览器关闭即清除
- **解决**：passport 记住密码 cookie (username + password hash) 触发自动登录，重新签发 JSESSIONID

## 坑 4：MCP 热加载限制

- **现象**：session 中激活 MCP 后工具不可用
- **解决**：必须**新建对话**。MCP 只在 session 启动时加载

## 坑 5：中文路径编码（Windows）

- **现象 1**：`subprocess.run()` 读 stdout 报 `UnicodeDecodeError: ''gbk''`
- **解决 1**：`subprocess.run(..., encoding="utf-8", errors="replace")`
- **现象 2**：Python print 中文/Unicode 直接崩溃（`UnicodeEncodeError: ''gbk'' codec can''t encode character`）
- **根因**：Windows 下 Python stdout 默认 GBK 编码，不能处理 Unicode 字符
- **解决 2**：每个脚本开头加 `sys.stdout.reconfigure(encoding=''utf-8'')`

## 坑 6：下载路径差异

- **Python 脚本**：`page.expect_download()` 精确控制保存位置 (`downloads/`)
- **MCP 模式**：文件自动保存到 `.playwright-mcp/`（仓库根目录），需 `mcp_to_output.py` 整理

## 坑 7：13 个同名"导出Excel"按钮

- 通途页面有 FBA、FBF、Shein、Temu 等 13 个平台各自的导出按钮
- 必须用 `a[onclick="exportExcelPage()"]` 精确定位库存清单的导出按钮

## 坑 8：git worktree 理解

- 主仓库在 `main` 分支
- 调试 worktree (`.claude/worktrees/`) 在独立分支
- 两个独立工作区，互不干扰，完成后 merge 回 main

## 坑 9：赛狐页面 20+ 隐藏 dialog（关键！）

- **现象**：`document.querySelector(''.el-dialog__wrapper'')` 拿到第一个（是隐藏的空壳）
- **原因**：赛狐所有弹窗预渲染在 DOM 中，只有 1 个 visible
- **解决**：**永远**用 `.filter(d => d.getBoundingClientRect().width > 0)` 过滤

## 坑 10：Element UI checkbox 不能用 evaluate click

- **现象**：`cb.click()` 在 evaluate 中不改变 Vue 组件状态
- **解决**：必须用 Playwright `page.locator().click()` 真实点击

## 坑 11：赛狐导入 Excel 的 sheet 名陷阱

- **现象**：`pd.to_excel()` 生成的文件导入卡在"正在导入"
- **根因**：赛狐模板 sheet 名必须是 `商品`（默认 `Sheet1` 不认）
- **解决**：`ExcelWriter(sheet_name=''商品'')` + 不复用模板文件

## 坑 12：el-dropdown-menu__item 对 Playwright 不可见

- **现象**：Playwright click 超时 (element not visible)
- **解决**：使用 `page.evaluate("item.click()")` 绕过可见性检查

## 坑 13：无 MCP 探索直接猜 URL 浪费大量精力

- **现象**：找"其他入库"入口时，在 Python Playwright 脚本中穷举了 20+ 个猜测 URL，反复试错耗时数十分钟
- **根因**：赛狐 SPA 侧边栏菜单只在点击"仓库"导航后动态展开，URL 无法直接访问
- **正确做法**：先用 MCP Playwright 浏览器浏览页面 → 截图 → evaluate 搜 DOM → 点菜单找 URL，确认后只用 Python 写脚本
- **教训级别**：10 分钟 MCP 探索可省 2+ 小时 Python 试错

## 坑 14：Playwright download.suggested_filename 中文乱码（Windows）

- **现象**：download.suggested_filename 返回乱码（如 ¿â´æ½á´æÇåµ¥ 而非 库存结存清单）
- **根因**：通途服务器 Content-Disposition 使用 GBK 编码中文文件名，Playwright 在 Windows 上按 UTF-8 解码 → mojibake
- **连锁影响**：保存到磁盘的文件名永久损坏，后续 glob() 找不到文件 → 合并步骤静默跳过
- **解决 1（下载时）**：不用 download.suggested_filename，改用 Python 本地时间构造安全文件名
- **解决 2（合并时）**：不用 glob() 匹配中文关键词，改用 iterdir() + 前缀/后缀匹配

## 坑 15：销售及库存报表页面无 #warehouseDisableDiv

- **现象**：复用 `tongtu_auto_export.py` 的登录检测 `#warehouseDisableDiv` → 始终返回 0
- **根因**：`#warehouseDisableDiv` 是库存结存页面专属元素，在其他通途页面上不存在
- **解决**：用 body 文本检测 `"编号：" in body_text`（所有已登录通途页面 body 均包含用户编号）
- **适用范围**：所有非库存结存的通途页面（统计报表、采购等）

## 坑 16：销售及库存报表仓库选择器不是 togglebutton

- **现象**：按库存页面的 ExtJS togglebutton 模式查找仓库 → 找不到
- **根因**：此页面的仓库选择是普通 `<table>` 行 + `<input type="checkbox">`，每行 `rowuuid` 属性，`selected="1"` 表示选中
- **解决**：
  - 页面默认"全部"已选中，无需额外操作
  - 如需单选：`page.locator("tr", has_text="CENTRADE").locator("input[type=''checkbox'']").check()`
- **关键区别**：库存页用 ExtJS togglebutton（`a.toggle_btn`/`a.toggle_btn_down`），报表页用 HTML checkbox 表格

## 坑 17：统计提交后下载轮询需排除已有记录

- **现象**：提交统计任务后立即检测到"点击下载统计结果"链接→实际下载的是旧记录
- **根因**：`a:has-text(''点击下载统计结果'')` 匹配到提交前已存在的历史下载记录
- **解决**：提交前用 `get_existing_download_hrefs()` 收集所有已有 href → 轮询时只匹配 `href not in existing_hrefs`
- **刷新策略**：轮询时在「数据查询」和「统计导出」tab 之间切换，触发页面重新加载记录列表

## 坑 18：过滤器 str.contains("仓库") 误杀含"仓库"字的仓库名

- **现象**：处理 xlsx 时用 `str.contains("仓库")` 过滤汇总行 → 丢失"皮壳仓库"、"多渠道仓库"等合法仓库的全部数据
- **根因**：`str.contains` 做子串匹配，"皮壳仓库"包含"仓库"二字被误判为汇总行
- **解决**：用精确匹配 `isin({"数量总计", "金额总计"})` 替代子串匹配
- **教训**：做字符过滤时永远优先精确匹配，子串匹配只在明确知道不会误杀时使用

## 坑 19：统计结果下载链接是直接 URL 而非 ExtJS onclick

- **现象**：按库存页面习惯找 `a[onclick="..."]` → 找不到
- **根因**：销售及库存报表的下载链接是普通 `<a href="https://erp102.tongtool.com/file/013595/statistical/.../xxx.zip">点击下载统计结果</a>`，不是 ExtJS onclick 触发
- **解决**：直接用 `page.locator("a:has-text(''点击下载统计结果'')").click()` + `page.expect_download()` 下载
- **注意**：下载链接的 zip 文件名不含乱码（服务器直接返回文件流），与库存清单的 GBK 编码问题不同
