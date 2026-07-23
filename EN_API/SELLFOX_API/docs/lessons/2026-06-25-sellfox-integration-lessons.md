---
okf: v0.1
type: Lesson
title: 赛狐 API 接入踩坑记录 — 2026-06-24/25
description: 赛狐 OpenAPI 接入全过程记录：认证探索、IP 白名单、Playwright 自动化、Apifox 密码保护、错误修正
tags: [amazon, advertising, sellfox, saihu, API, integration, lessons, pitfalls]
timestamp: 2026-06-25
---

# 赛狐 API 接入踩坑记录

> 何时读: 接入赛狐 API 遇到问题时、需要了解认证流程时、回顾架构决策时。
> 最后更新: 2026-07-02 | 共 16 条教训

## Lesson 1: IP 白名单是硬门槛

**问题**: 从代理 IP (185.220.239.51, 日本出口节点) 无法调用赛狐 API 任何非 token 端点。所有端点返回空响应或被拒绝。

**根因**: 赛狐 API 的 IP 白名单是服务端强制校验。白名单中有 123.117.236.65（北京办公室）和 82.156.238.248（VPS），但当前代理 IP 不在其中。

**Token 端点的例外**: `/api/oauth/v2/token.json` 不受 IP 白名单限制——这是唯一可从任何 IP 访问的端点。这让我们能在不切换 IP 的情况下验证凭证有效性。

**教训**: 
- 第一时间确认自己 IP，不要假设在正确的网络环境中
- IP 白名单是赛狐 API 的第一道防线，几乎所有业务端点都被保护
- 后续需要从白名单 IP 运行测试，或部署代理/VPN 隧道

## Lesson 2: 认证方式不是猜测出来的，需要文档

**问题**: 尝试了 6+ 种认证方式（Basic Auth、Bearer token、HMAC-SHA256 多种变体、API Key header、Query params）全部返回 401。

**根因**: 赛狐使用的是 OAuth 2.0 `client_credentials` grant，但文档在 Apifox 密码保护后面。没有文档的情况下不可能猜出正确的端点路径 `/api/oauth/v2/token.json` 和参数组合。

**教训**:
- 永远不要在没有文档的情况下猜测 API 认证方式——浪费大量时间
- 优先使用 WebFetch/浏览器自动化获取文档，而非暴力尝试
- OAuth token 端点往往有非标准路径（不是 `/oauth/token`）

## Lesson 3: Playwright 浏览器自动化是突破密码保护的关键

**问题**: Apifox 共享项目 `https://sellfoxapi.apifox.cn/` 需要密码才能访问。WebFetch 无法通过密码门（需要交互式点击"访问文档"按钮）。

**解决**: 使用 Playwright MCP 的 `browser_run_code_unsafe` 功能：
```javascript
await page.fill('input[type="password"]', '<SELLFOX_API_DOC_KEY>');
await page.click('button:has-text("访问文档")');
```

**效果**: 成功获取"获取 Access Token"文档内容，确认了认证端点、参数和返回格式。

**教训**:
- 对于需要交互式登录的文档页面，浏览器自动化（Playwright/Claude in Chrome）是唯一可行的自动访问方式
- Apifox 共享项目的密码保护是 cookie/session 级别的，通过浏览器提交后该页面可用
- 但每次导航到新页面需要重新认证，所以只能读当前页面

## Lesson 4: Apifox LLMs.txt 只含部分文档

**问题**: 通过 Playwright 获取了 `/llms.txt`（77KB），以为包含了完整 API 文档。但解析后发现只有 14 个"开发指南"文档链接，没有商品/广告/订单等 API 参考文档。

**根因**: Apifox 的 LLMs.txt 由项目拥有者手动配置哪些页面被包含。赛狐的 LLMs.txt 只配置了开发指南部分，API 参考文档（商品、广告、FBA 等 16 个模块）未包含在内。

**教训**:
- LLMs.txt 的内容取决于项目配置，不一定是完整文档
- API 参考文档需要通过侧栏导航交互式展开——这些内容可能从 Apifox 后端 API 动态加载

## Lesson 5: Apifox React 侧栏无法通过 URL 参数展开

**问题**: 尝试通过 URL 参数（`?nav=01GJPY2G1RSAM6SGKMWST7DRZ8`）导航到 API 文档，但页面始终显示"开发指南"内容。侧栏中的"广告"等模块点击后也无法通过 JS 展开。

**根因**: Apifox 的 React 前端使用客户端路由和状态管理。侧栏子项是通过点击事件触发的懒加载，不是通过 URL 参数控制的。导航参数（`nav=...`）改变了导航高亮但未触发侧栏展开和数据加载。

**教训**:
- 现代 React SPA 的导航状态不一定反映在 URL 中
- Python requests/curl 只能获取静态 HTML，无法执行 JS
- 必须使用浏览器自动化来模拟真实点击交互

## Lesson 6: "赛狐不足换领星"是错误假设

**问题**: 在早期方案中提出"如果赛狐 API 不足，可以接入领星 API 作为补充"。

**用户纠正**: 很少有公司同时使用两个竞品 ERP。方案不应是"赛狐不够就加领星"，而应该是"赛狐 API 不足就考虑直接 SP-API"。

**教训**:
- 不要以"技术可行性"替代"商业可行性"来提出建议
- 同时使用两个竞品 ERP 从采购、学习和运维角度都不现实
- 备选方案应该是架构层面的降级路径，而非功能层面的加法

## Lesson 7: Sellfox MCP 需要亲自验证，不能盲信 Agent 报告

**问题**: 早期研究 Agent 报告 "Sellfox MCP 已存在于 himcp.ai，70+ 工具，质量不错"。据此将其列为推荐方案。

**用户纠正**: GitHub 仓库 https://github.com/shuolol/sellfox-mcp 只有 2 星（用户加了 1 星后）。

**亲自验证结果**:
- 2 stars, 7 commits, 单人项目 (shuolol)，与赛狐无官方关系
- 代码架构良好（TypeScript + MCP SDK + Zod + SQLite），但早期阶段
- 65% 工具是广告相关（覆盖完整），但这只是包装了赛狐 OpenAPI
- **结论**: 不建议作为核心生产依赖，可作为 Claude 查询赛狐数据的便捷通道

**教训**:
- Agent 报告可能过度乐观——关键决策需要亲自验证
- GitHub stars/commits/contributors 是项目成熟度的硬指标
- 第三方开源项目即使代码质量好，bus factor=1 也是重大风险

## Lesson 8: 多账号安全是整个架构的第一约束

**问题**: 最初方案直接假设"我们的服务器直接调用 Amazon Ads API"是安全的。完全忽略了多账号防关联这个致命约束。

**调研后修正**: 
- 同一浏览器登录多个 Amazon 账号：风险 **9/10**（137+ 指纹信号）
- 同一服务器调用 SP-API 多账号：风险 **2/10**（Amazon 官方支持）
- 但 Ads API 关联策略比 SP-API 更严格：风险 **3-4/10**
- ERP（赛狐/领星）中介：风险 **1-2/10**（SPN 认证 + 行业验证）

**最终方案**: 赛狐 OpenAPI 作为主要数据源（SPN 认证 + 零关联事故），直接 SP-API 作为备选。

**教训**:
- 多账号安全是所有架构决策的第一优先级——高于功能、性能、成本
- 浏览器和 API 的安全模型完全不同，不能混淆
- "授权阶段"和"调用阶段"需要分开评估风险

## Lesson 9: SP-API 私人 vs 公共开发者模型是关键区分

**问题**: 早期调研混淆了"私人开发者可以管理自己组织的多账号"和"可以管理其他公司的账号"。

**正确理解**:
- **私人开发者**: 仅自己的组织，上限 10 个自主授权，不需要 OAuth，不需要 SPN
- **公共开发者**: 任何卖家通过 OAuth 授权，上限 25（未上架）/无限（上架后），推荐 SPN
- **SPN 认证**: 需要四大支柱审核（合规记录/专业能力/服务质量/验证案例），不是必须但解锁完整广告 API

**对用户的意义**: 自己公司的多个法律实体（同一控制下）可以用私人开发者 + 自主授权（上限 10 个）。服务外部卖家才需要公共开发者 + SPN。

**教训**:
- Amazon 的开发者体系有明确层级——不要混淆私人/公共/SPN 的权限边界
- "管理多个账号"在不同语境下有完全不同的合规含义

## Lesson 10: 文档和凭证管理需要标准化

**问题**: 赛狐 API 凭证分散在对话中，没有统一管理。

**解决**: 创建了标准化的凭证存储:
- `advertise/.env` — 环境变量格式，Python 脚本直接读取
- `advertise/config_sellfox.json` — JSON 格式，方便其他工具/Agent 使用
- `advertise/AGENT_HANDOFF.md` — 凭证位置记录在入口文档中
- `.gitignore` 中已排除 `.env` 和敏感数据

**教训**:
- API 凭证应该在项目初期就标准化存储（.env + config.json 双格式）
- 入口文档（AGENT_HANDOFF.md）应明确记录凭证位置
- 避免在对话历史中遗失关键配置信息

## Lesson 11: `requests` 库在中文 Windows 上签名失败 — 用 `urllib`

**问题**: 使用 `requests.post(params=..., json=...)` 调用赛狐业务 API，签名算法本身正确（已验证 HMAC-SHA256 hexdigest），但服务器始终返回 `code=40011`（签名错误）。

**排查过程**: 
- 用文档中的 Python 示例验证签名算法 → 正确
- 用 `python -c "..."` 一次性脚本测试 → 成功
- 但保存为 `.py` 文件运行 → 失败
- 最终发现：`requests` 库在中文 Windows（GBK locale）下，URL 构建过程存在编码交互问题，导致最终发出的 URL 与服务端计算的签名字符串不一致

**解决**: 全部改用 Python 标准库 `urllib.request`，手动构建完整 URL + `.encode("utf-8")`。不再依赖 `requests` 的隐式编码。
```python
full_url = f"{DOMAIN}{url_path}?access_token={token}&client_id={APP_ID}&nonce={nonce}&timestamp={ts}&sign={sig}"
req = urllib.request.Request(full_url, data=json.dumps(body).encode("utf-8"),
                             headers={"Content-Type": "application/json"}, method="POST")
```

**教训**:
- `requests` 不是银弹——在非英语 locale 下可能出编码问题
- 签名类 API 对 URL 字节级一致性要求极高，任何编码差异都会导致签名不匹配
- 使用 stdlib `urllib` 不仅免去依赖，还能在 UTF-8 边界上获得完全控制
- 最小可复现脚本（`python -c "..."`）exposed 了问题范围：文件 vs 交互式执行

## Lesson 12: 下载文件是 `.xlsx` 不是 `.csv`，含中文列名

**问题**: API 文档暗示下载的是 CSV 格式，但实际下载的文件是 `.xlsx`（Excel 二进制格式）。用 `openpyxl` 打开才能读取，且列名全是中文（店铺、日期、广告活动、花费、曝光量、CPC 等）。

**解决**: 
- 文件扩展名保存为 `.xlsx`
- 使用 `openpyxl.load_workbook()` 读取，sheet 名为 `sheet`
- 列名映射已在 `advertise/__init__.py` 中定义（中文→英文）

**教训**:
- 不要假设 API 返回的文件格式——验证前几百字节的文件头
- XLSX 文件以 `PK\x03\x04` 开头（ZIP 格式），CSV 以文本开头

## Lesson 13: 轮询接口用 `taskIds`（数组），不是 `id`（单值）

**问题**: 使用 `{"id": task_id}` 调用 `/api/cpc/download/pageList.json` 返回空 rows。文档中参数名可能误导。

**根因**: API 期望的参数是 `taskIds`（字符串数组），不是 `id`（单值字符串）。

**正确用法**:
```python
signed_post("/api/cpc/download/pageList.json", {
    "taskIds": ["98829", "98830"],
    "pageNo": 1,
    "pageSize": 50,
})
```

**教训**:
- API 参数名和类型要与实际请求对比验证，不要只信文档
- 中文 API 文档可能使用复数形式命名（`taskIds`）

## Lesson 14: 报告状态用中文字符串，不是数字码

**问题**: 预期轮询返回 `status: 2`（完成）/ `status: 3`（失败）等数字状态码，实际返回的是 `reportState` 字段，值为中文字符串。

**实际值**:
- `"已生成"` = 完成（含 downloadUrl）
- `"生成中"` = 处理中
- `"失败"` = 失败

**代码处理**:
```python
state = row.get("reportState", "unknown")
if state == "已生成":
    url = row.get("downloadUrl", [])[0]
    download_file(url, outpath)
elif state == "失败":
    print(f"Task failed: {row}")
```

**教训**:
- 国内 ERP API 常用中文状态值——不要假设英文或数字枚举
- 直接打印 API 返回的原始 row 对象，快速了解实际数据结构

## Lesson 15: 下载 URL 含中文需百分号编码

**问题**: API 返回的 `downloadUrl` 包含中文字符（如 `/path/广告活动报告.xlsx`），直接用 `urllib.request.Request(url)` 报错 `UnicodeEncodeError: 'ascii' codec can't encode characters`。

**解决**: 对 URL 的 path 组件进行百分号编码，保留结构字符：
```python
parts = urllib.parse.urlparse(url)
encoded_path = urllib.parse.quote(parts.path, safe='/:@!$&()*+,;=')
safe_url = parts._replace(path=encoded_path).geturl()
```

**教训**:
- HTTP 标准要求 URL 中非 ASCII 字符必须百分号编码
- `safe` 参数需要保留 `/ ? & =` 等 URL 结构分隔符不变

## Lesson 16: 创建任务需要间隔延时防限流

**问题**: 连续创建 4 个下载任务，第 2 个开始返回 `code=40019`（请求过于频繁）。

**解决**: 每个任务创建之间加 `time.sleep(2)`。2 秒间隔在生产中稳定可用，4 个任务全部创建成功。

**教训**:
- 赛狐 API 有请求频率限制，文档中未明确写出具体的 QPS 阈值
- 批量操作时默认加延时是安全策略——异步任务不需要实时性

---

## 更新历史

| 日期 | 变更 |
|------|------|
| 2026-06-25 | 初始 10 条教训（认证、IP、Playwright、架构决策） |
| 2026-07-02 | 新增 6 条教训（编码、文件格式、参数、状态、URL、限流）— 基于 `fetch_ad_reports.py` 实战测试 |

## See also
- [赛狐 API 实践指南](../reference/2026-sellfox-api-guide.md)
- [多账号防关联安全](../reference/2026-security-multi-account.md)
- [SP-API 开发者模型](../reference/2026-sp-api-developer-model.md)
- [v0.1-v0.3 12条开发教训](lessons-learned.md)
- [AGENT_HANDOFF.md](../../AGENT_HANDOFF.md)
- [fetch_ad_reports.py](../../fetch_ad_reports.py) — 实战脚本（纯 stdlib，零依赖）
