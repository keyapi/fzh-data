---
okf: v0.1
type: Reference
title: 把 FAC / 赛狐 / NAS 三个 MCP 接上 ChatGPT —— 一次串起来的方法与四个教训
date: 2026-09-21
category: workflow-issues
module: nas_mcp
problem_type: workflow_issue
component: development_workflow
severity: medium
applies_when:
  - "要给一个内网/自建系统接 MCP 客户端（ChatGPT / Claude / Cursor）"
  - "拿不准某个 SaaS 或自建系统有没有官方 MCP、该不该自建"
  - "要在办公网内判断自家服务是否公网可达"
  - "复用别人的封装（尤其 0.x 版 SDK）读写文件"
tags: [mcp, chatgpt, nas, sellfox, erpnext, verification, third-party-eval, lessons]
---

# 把 FAC / 赛狐 / NAS 三个 MCP 接上 ChatGPT —— 方法与四个教训

## 一句话

本次把三套系统的 MCP 一次性推到了「ChatGPT 可用」：**ERPNext(FAC)** 走 OAuth、
**赛狐**有官方托管 MCP、**群晖 NAS** 自建只读服务并已上线。过程中踩了四个坑，
**其中两个是我的方法问题，不是技术难题** —— 记在这里，下次接第四个系统时别再交学费。

---

## 本次产出了什么（4 个 PR，均未合并）

| PR | 内容 | 状态 |
|---|---|---|
| [#243](https://github.com/keyapi/fzh-data/pull/243) | 新建 `chatgpt/` 子项目 —— ChatGPT 连接器接 MCP 的要求与 FAC 路径 | 未合 |
| [#246](https://github.com/keyapi/fzh-data/pull/246) | 新建 `sellfox_mcp/` —— 赛狐**官方托管 MCP** 探测脚本 + 操作参考 | 未合 |
| [#247](https://github.com/keyapi/fzh-data/pull/247) | NAS 接 ChatGPT 可行性调研（[本文档同目录](../../research/2026-09-21-nas-mcp-chatgpt-feasibility.md)） | 未合 |
| [#248](https://github.com/keyapi/fzh-data/pull/248) | 新建 [`nas_mcp/`](../../../nas_mcp/) —— NAS 只读 MCP 服务，**已部署上线** | 未合 |

> ⚠️ **4 个 PR 全未合并**，所以 `main` 上还看不到这三个子项目。
> 子项目分散在不同分支，交叉引用只能用 PR 链接 —— 别用本地路径，会断。

---

## 教训一：单次探针不可信 —— 尤其在**办公网内**测自家公网可达性

**我干了什么**：在办公室测 `https://nas.vilavi.cn/` 得 **HTTP 200**，一度以为 NAS 公网可达。

**真相**：办公室的 DNS（OpenWrt dnsmasq + 新华三 192.168.10.1）把该域名**覆盖解析到内网
`192.168.100.242`** —— 我测的是**内网路径**。curl 的 `remote_ip` 显示连的是 `192.168.100.242:443`。

**怎么纠正的**：换**两处独立外部主机**复测（上海 VPS + 美国 VPS），结论一致：

```
nas.vilavi.cn:443    两处都失败
nas.vilavi.cn:11024  两处都 200
api.vilavi.cn:443    两处都 200（对照）
```

**可复用的做法**：

1. 判断「公网可达」时，看 `curl -w '%{remote_ip}'`，**不要只看状态码**
2. 内网优先找**子网覆盖解析**的痕迹（`nslookup` 的应答服务器是谁）
3. **必须换外部视角复测** —— 你们有两台境外/异地 VPS 可用（`ssh sh-erpnext-test` / `ssh us-ubuntu-proxy-pub`）

> 这条与项目既有的「结论前多方核实」一脉相承；本次是又一个实例，且**差点写进文档当结论**。

---

## 教训二：评估第三方方案时，**先盘功能面再决定自建**（用户直接批评）

**我干了什么**：评了 3 个开源群晖 MCP 方案，写了对比表，然后**选了自建**。理由成立（VPS 没 Node、
仓库是 Python、有现成的 `NAS_API`）。

**问题在哪**：我把它们**只当作「对比对象」，没抄它们的工具清单**。结果自建的东西功能面远小于
现成方案，变成「用户要一个功能我加一个」——用户原话：**「不能等着我说一个功能你才实现一个功能」**。

**差距有多大**（事后盘 mrquj 的工具表才看到）：

| 能力 | 现成方案有 | 我第一版有 |
|---|---|---|
| 列目录 / 文件信息 / 读文本 | ✅ | ✅ |
| **读图片（模型能看图）** | ✅ | ❌ **最初还主动禁掉了** |
| **搜索**（按名/扩展名/大小/时间） | ✅ `search_files` | ❌ |
| **缩略图** | ✅ | ❌ |
| **文件夹递归大小** | ✅ `get_folder_size` | ❌ |
| **文件校验和（不下载）** | ✅ `get_file_checksum` | ❌ |
| **分享链接** | ✅ `create_sharing_link` | ❌ |
| **压缩包内容列表 / 解压** | ✅ | ❌ |

**该改的做法（下次接新系统照做）**：

1. **先盘点候选方案的工具清单** —— 直接把它们的 README 工具表抄成一张 checklist，**不管最后用不用**
2. **再盘底层 API 的上限**（本次：`synology_api` 暴露 49 个方法 / 19 个 DSM API 族）
3. 两份对照 → 列出「该有什么」，**一次性补齐**，而不是等用户点菜
4. 只在与「安全边界」相关时才做减法（如不暴露删除），**不要拿「保守」当借口砍掉核心能力**

> 本次的反面样本：`nas_read_text` 我做成「只允许文本 + 256 KiB」，
> 等于**主动砍掉了产品图场景的全部价值** —— 而这恰恰是用户接 NAS 的主要目的。

---

## 教训三：上游封装会**吞异常** —— 「出错」会被伪装成「空」

**现象**：ChatGPT 报某个目录「0 项，文件夹是空的」，但同一账号直连 DSM 实测**有 355 项**。

**两个上游 bug**：

1. `NAS_API.get_file_list` 在失败时 `return []` —— 把 `Session timeout`（会话过期）
   **伪装成「文件夹是空的」**。使用者会以为数据丢了。
2. `FileStation.get_file(mode='download')` 是**往磁盘写文件并返回 `None`** 的，
   所以 `NAS_API.download_file()` **永远返回 None**（还会偷偷在磁盘建文件）。

**改法**：本模块自带**严格数据层** —— 出错抛 `NasError`，**绝不转成空结果**；
会话失效（`session`/`timeout`/code 106/107）**自动重登重试一次**。

**可复用的做法**：

- 用别人的封装前，**先读它的失败路径**：出错时返回什么？是抛异常，还是吞掉给个默认值？
- **「空」和「错」必须是两种结果**，绝不能合并
- 加一条**回归测试**钉住它：本次新增「不存在的目录必须抛错，不得返回空」（这条测试当场又抓出
  一个 `json.dumps(异常对象)` 的次生 bug）

---

## 教训四（做对的）：**鉴权先验最小闭环，零生产影响**

要回答「ChatGPT 能不能用静态令牌连我们」，我没去部署生产服务，而是：

1. 在本机起一个 ~140 行的最小 MCP 服务（`initialize` / `tools/list` / 一个 echo 工具）
2. 用**本机自己的 Tailscale Funnel**（原本无任何 serve 配置）暴露成公网 443
3. 在 ChatGPT 建「访问令牌 → 持有者(Bearer)」连接器

**服务端日志拿到决定性证据**：

```
User-Agent = openai-mcp/1.0.0 (Agent Builder)
Authorization = Bearer probe-f…
序列：server/discover → initialize → notifications/initialized → tools/list → tools/call
```

→ **ChatGPT 确实发 `Authorization` 头，全流程成功**。这个结论**赛狐与 NAS 共用**，一次验证两处受益。

**顺带发现**：Funnel 一开**数分钟内**就被互联网扫描器命中（leakix l9scan / ForestEngine / ClaudeBot）
—— **Funnel ≠ 私密通道**，安全上不比端口转发更好。

---

## 相关

- **子项目**：[`nas_mcp/`](../../../nas_mcp/)（本分支）｜ `chatgpt/` → [PR #243](https://github.com/keyapi/fzh-data/pull/243)｜ `sellfox_mcp/` → [PR #246](https://github.com/keyapi/fzh-data/pull/246)
- **调研**：NAS 接 ChatGPT [可行性](../../research/2026-09-21-nas-mcp-chatgpt-feasibility.md)
- **既有相关**：[搜索结果先看文档再动手](search-first-before-implementing.md)｜
  [未验证的外部 API 断言要标注](../documentation-gaps/unverified-external-api-claims-in-docs.md)
