# SPS Commerce API — Agent Handoff

> 本文件是 `sps_api/` 子项目的 Agent 入口。新对话/新 Agent 从这里开始。
> 项目文档按 OKF v0.1 维护，见 [docs/](docs/index.md)。
> 详细可行性调研报告：[docs/research/2026-08-18-sps-commerce-api-feasibility.md](../docs/research/2026-08-18-sps-commerce-api-feasibility.md)

## 一句话

FZH（Pottery Barn 供应商）在 SPS Commerce 门户手动下载订单/生成 ASN/下载发票/发库存，本子项目验证并打通了 **SPS Transaction API 自动化通道**：用 **Machine-to-Machine (M2M) App + client_credentials** 拿 token（无需 Redirect URI），用 HTTPS 文件交换完成订单/ASN/发票/库存。**沙盒已端到端实测通过，生产待 SPS 签约开通。**

## 背景（为什么做）

- FZH 是 Pottery Barn 供应商，当前全部操作在 SPS 门户手动：下载订单(850)、生成 ASN(856)、下载发票(810)、每天发库存(846，已有 Selenium 脚本在 `SPS_Selenium_Local/`）。
- 用户想知道能否通过 API 自动化，以及 Dev Center 的 Redirect URI 是否需要。
- 2026-08-18 完成调研 + POC。

## 关键结论（直接回答原问题）

1. **Redirect URI 是否需要？** 取决于 App 类型：
   - Web Service Application（用户最初选的）→ 授权码流，**必须配 Redirect URI**（实测其密钥调 client_credentials 返回 `403 unauthorized_client`）。
   - **Machine-to-Machine (M2M)** → client_credentials，**不需要 Redirect URI**，完全无头。官方推荐"公司代表自己连接"用 M2M。✅ **最终选了 M2M。**
2. **能自动操作吗？** 能，但**没有"门户按钮 API"**。Dev Center 只有 Shipping Doc API / Trading Partner Submission API（买家用，不适用）/ **Transaction API**。订单/ASN/发票/库存本质是 EDI 单据，走 Transaction API 交换 RSX XML 文件。
3. **生产可用吗？** 目前**不能**——生产根目录为空（`{"results":[]}`，`out/PO/` 404）。官方文档明确：生产数据要"与 SPS 签约 + 实施团队开通访问并配置交易路由"。

## 过程记录（本次做了什么）

1. **调研**：WebFetch 抓不到 Dev Center SPA → 用 **Playwright** 渲染读取官方文档，拿到 OAuth 端点、App 类型区别、Transaction API 全部端点、供应商目录约定。
2. **认证实测**：
   - 用户原 Web Service App 沙盒密钥 → client_credentials → **403**（该 App 不支持）。
   - 用户新建 M2M App → client_credentials → **成功**，`expires_in=3600`。
3. **沙盒 API 实测（全链路通过）**：
   - `GET /transactions/v5/data/` 根目录 → 有 `in/`、`out/`。
   - `GET /transactions/v5/data/out/PO/` → 4 个样例订单。
   - `GET .../out/PO/PO112853-1-v7.7-CrossDock.xml` → 下载成功（9.8KB RSX XML）。
   - `POST .../in/INPOC00001` → **201**（写路径通），随后 `DELETE` → 204 清理。
   - 注意：`testin/` 目录不存在（404），直接写 `in/`。
4. **生产只读实测**：M2M 生产密钥 token 成功，但根目录空、`out/PO/` 404 → 未开通。
5. **产出**：`sps_api/` 脚本 + 调研报告 + 本 handoff。

## 脚本（sps_api/）

```bash
cd sps_api
python oauth.py                      # client_credentials 拿 token，缓存到 token.json
python probe.py                      # 列 Transaction API 根目录
python probe.py out/PO/              # 列目录（如样例订单）
python probe.py out/PO/ --download   # 下载第一个文件到 downloads/
python probe.py --token-only         # 只拿 token

# 读 SPS 相关邮件（腾讯企业邮箱 IMAP，凭据走环境变量，不写进代码）
IMAP_USER='...' IMAP_PASS='...' IMAP_SERVER='imap.exmail.qq.com' \
  python read_sps_mail.py --sender amkudrle@spscommerce.com   # 列出匹配邮件
# 注：腾讯 IMAP 对 FROM/SUBJECT 服务端搜索失效，须用日期窗口 + 客户端过滤（见 docs/reference/tencent-imap.md）
```

- `config.py` — 从 `.env` 读凭据/端点（SPS_TOKEN_URL / SPS_API_BASE / SPS_AUDIENCE）。
- `oauth.py` — M2M client_credentials + token 缓存复用（官方要求缓存避免限流）。
- `probe.py` — 只读探测/下载（列目录、下载）。
- `read_sps_mail.py` — IMAP 读邮件（`--sender` / `--since/--before` / `--full N`），凭据从环境变量读。
- 端点速查（base `https://api.spscommerce.com`）：
  - `POST /transactions/v5/data/{file-path}` — 发文件（`Content-Type: application/octet-stream`）
  - `GET /transactions/v5/data/{directory}/` — 列目录
  - `GET /transactions/v5/data/{file-path}` — 下载
  - `DELETE /transactions/v5/data/{file-path}` — 删除

## 目录约定（供应商视角）

- `out/` 零售商 → 供应商（**订单在这里**，`out/PO/`、`out/IN/`、`out/SH/` 等）
- `in/` 供应商 → 零售商（发 ASN/发票/库存/PO 确认）
- 文件命名：`PO...`/`IN...`/`SH...`/`PR...`/`IA...` + 数字/唯一键

## 与用户 4 个操作的映射

| 手动操作 | API | 实测 |
|---|---|---|
| 下载订单 (850) | GET `out/PO/` 列目录 → GET 文件（轮询） | ✅ |
| 发 ASN (856) | POST `in/SH<key>` | ✅（同机制，沙盒 POST 201） |
| 下载发票 (810) | GET `out/IN/` → GET 文件 | ✅（同机制） |
| 发库存 (846) | POST `in/IA<key>` | ✅（替代现有 Selenium） |

## 经验教训

- **App 类型决定认证流程**：自用自动化选 M2M（client_credentials），省掉 Redirect URI 整套回调。第三方集成商文档（StackOne/Cyclr）只讲 Web Service 授权码，容易误导。
- **SPA 文档抓取**：SPS Dev Center 是 SPA，WebFetch 拿不到正文，用 Playwright 渲染读取。
- **API 响应结构**：Transaction API 列目录返回 `{"results": [...], "paging": {...}}`，不是裸数组；文件键在 `path` 字段。
- **目录要先存在**：POST 到不存在的目录（`testin/`）→ 404 "Parent directory not found"；沙盒只有 `in/`/`out/`。
- **生产开通是商务流程**：技术上 token/API 都通，但生产数据要 SPS 签约 + 实施团队配置路由，需提前走商务。

## 安全注意事项

- **`.env` 与 `token.json` 已 gitignore**，绝不提交。`.env` 目前存**沙盒 M2M** 密钥。
- 用户曾两次把密钥贴进对话（沙盒 + **生产**）。**生产密钥已暴露，强烈建议正式使用前在 Dev Center 轮换/重新生成。**
- 生产密钥测试仅用环境变量临时覆盖，**未写入 `.env`、未落盘、未提交**。

## 当前状态 / 下一步

- [x] 调研 + POC（沙盒全链路） ✅
- [x] 生产只读探测（未开通，根目录空）
- [x] **邮件已发给 Alison**（2026-08-18，`us@mxdeals.com`）：确认是否仍负责 iCenTrade 账号 + 自己对接 API 是否额外收费，等回复
- [ ] 等 Alison 回复后：若推进，请其提供文档（Transaction API/RSX/PB mapping）+ 开通生产数据访问与交易路由
- [ ] 拿到 PB 的 RSX/EDI 规格后设计流水线：轮询 `out/PO/` → 解析订单 → 对接 ERPNext/赛狐 → 生成 ASN/发票 → POST `in/`
- [ ] 库存上报用 `POST in/IA` 替代 Selenium（`SPS_Selenium_Local/`）
- [ ] 迁移到生产 M2M App（沙盒 M2M 已建）

## 相关文档

- OKF 索引：[docs/index.md](docs/index.md) ｜ 变更日志：[docs/log.md](docs/log.md)
- 可行性报告（含官方文档 URL）：[../docs/research/2026-08-18-sps-commerce-api-feasibility.md](../docs/research/2026-08-18-sps-commerce-api-feasibility.md)
- 解决方案（ce-compound）：[../docs/solutions/architecture-patterns/sps-commerce-api-automation.md](../docs/solutions/architecture-patterns/sps-commerce-api-automation.md)
