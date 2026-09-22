---
okf: v0.1
type: Reference
title: 公开代码仓与私有公司知识分层——兼顾 Agent 检索、同事使用与防泄露
date: 2026-09-22
category: architecture-patterns
module: repository-governance
problem_type: architecture_pattern
component: documentation
severity: high
applies_when:
  - "公开仓库既要供 Agent 和同事使用，又包含公司基础设施、运维或业务细节"
  - "评估是否用 Vault、SOPS、Git submodule 或私有仓库存放内部知识"
  - "准备迁移已经进入公开 Git 历史的敏感文档"
tags: [public-repo, private-knowledge, secrets, agent-context, github, sops, vault]
related_components: [documentation, tooling, authentication]
---

# 公开代码仓与私有公司知识分层——兼顾 Agent 检索、同事使用与防泄露

## Context

本仓库公开后仍承担三种职责：

1. 存代码、通用解决方案与可公开复用的经验；
2. 给非技术同事提供「clone 后交给 Agent」的低门槛入口；
3. 给新对话和其他 Agent 留下可检索、可追溯的项目上下文。

`.gitignore` 已能拦住 `.env`、运行产物和部分凭证文件，但它拦不住写进普通 Markdown 的
服务器角色、真实网络拓扑、内部地址、运维路径、客户/员工标识和私有 API 行为。
GitHub secret scanning 主要识别凭证模式，也不能判断一段基础设施说明是否属于公司内部资料。

因此问题不是「要不要把所有东西放进 Vault」，而是先把三类信息分开：
**可公开知识、内部知识、真正的秘密**。

## Guidance

### 推荐架构：三层，而不是一个万能保险箱

| 层 | 放什么 | 推荐载体 | Agent 怎么读 |
|---|---|---|---|
| **公开层** | 代码、脱敏架构模式、通用踩坑、模板、公开 API 文档、对外 onboarding | 当前公开 GitHub 仓库 | 默认直接搜索 |
| **内部知识层** | 真实主机/服务角色、网络拓扑、运维 runbook、内部 API 契约、事故记录、公司和客户相关上下文 | **独立私有 Git 仓库，内容仍是 Markdown** | 授权用户运行一次 bootstrap 后，从固定本地目录读取 |
| **秘密层** | 密码、API key、token、证书私钥、cookie、服务账号凭证 | 1Password / Infisical 等 secret manager；过渡期可用已忽略的 `.env` | 只在执行命令时注入，不进入提示词和文档 |

核心判断：**私有知识仓不是 secret manager，secret manager 也不是知识库。**
内部文档需要全文搜索、链接、diff、PR 审阅和历史追踪，这正是私有 Git 仓库擅长的；
凭证需要最小权限、撤销、轮换和访问审计，这才是密码库/Vault 类产品擅长的。

### 私有知识仓采用普通 clone，不采用 Git submodule

推荐由一个脚本完成：

```bash
uv run python scripts/bootstrap_private_knowledge.py
```

目标体验：

1. 检查用户是否已登录并有私有仓权限；
2. 首次 clone，后续只做安全的 fetch/pull；
3. 放入公开仓已忽略的固定目录，例如 `.private/fzh-company-knowledge/`；
4. 打印 `READY / NO_ACCESS / NOT_CONFIGURED`，不因无权限阻断公开项目的普通使用；
5. 不复制明文凭证，不自动扩大任何系统权限。

公开仓 `AGENTS.md` 只保存发现规则：

- 私有目录存在时，基础设施、运维、客户或内部 API 问题必须先读其 `index.md`；
- 目录不存在时继续处理公开范围，但明确说明「私有上下文不可用」，不得猜测；
- 新知识按分类写入对应仓库，凭证永远不写入任一文档仓。

不采用 submodule 的原因不是它做不到，而是其日常行为不适合当前用户群：
初次 clone 默认得到空目录，需要 `--recurse-submodules` 或额外的 `init/update`；更新可能进入
 detached HEAD；公开仓还会暴露私有仓地址和固定 commit 指针。普通 clone + bootstrap 可以把这些
细节隐藏在一个可诊断的命令后面，也不会让无权限同事的公开仓 checkout 处于半完成状态。

### 为什么不把内部 Markdown 全部用 SOPS 加密后留在公开仓

SOPS 很适合 Git 中的**结构化秘密配置**：YAML、JSON、ENV、INI 等文件可保留键名、加密值，
并由 age、云 KMS 或 PGP 管理解密身份。它适合少量必须随配置版本化的密文。

但把长篇 Markdown 整体加密会损失本需求最重视的能力：

- GitHub 和普通 Agent 无法全文搜索；
- 链接、索引、diff 和在线审阅退化；
- 每位非技术同事都要先安装工具、领取密钥并正确解密；
- Agent 读取前必须获得解密能力，反而扩大秘密暴露面；
- 人员离职后即使移除新密钥，也无法让已经解密并复制过的内容失忆。

所以 SOPS 可作为**秘密层的补充**，不能替代私有知识仓。

### Vault / 1Password / Infisical 的定位

| 方案 | 适合 | 当前判断 |
|---|---|---|
| **1Password** | 人员共享凭证、CLI secret reference、运行时注入、服务账号与审计 | 团队需要共享凭证时的低运维优先选项；Windows 不应依赖仅支持 Mac/Linux 的挂载式 `.env`，应使用 CLI 注入或模板 |
| **Infisical** | 开发/CI 的环境分层、机器身份、CLI 注入、审计；可云托管或自建 | 若更偏工程化、希望自建或统一 CI secret，可作为 1Password 的替代 |
| **HashiCorp Vault** | 动态数据库/云凭证、短租约、自动轮换、证书签发、复杂策略和合规审计 | 当前过重；只有出现动态凭证、PKI 或明确合规需求时再引入 |
| **SOPS + age/KMS** | 少量 GitOps 配置必须以密文随 Git 版本化 | 补充工具，不作为人员知识库或主要共享密码库 |

短期可以继续用已忽略的本地 `.env`，但一旦出现「多人手工互传同一凭证」「离职后难撤权」
或「CI 需要生产凭证」，就应升级到 1Password 或 Infisical。不要为了保存 Markdown 先部署 Vault。

### 信息分类边界

| 示例 | 去哪里 |
|---|---|
| 通用的 FastAPI 307/303 重定向教训 | 公开仓 |
| 脱敏后的代理、队列、数据管道架构模式 | 公开仓 |
| 真实服务器地址、Tailnet 地址、SSH 跳转关系、端口和服务角色 | 私有知识仓 |
| 真实客户名、员工名、内部组织关系、事故时间线 | 私有知识仓；业务明细仍不得提交 |
| 内部 API 的真实端点、字段限制和生产操作 runbook | 私有知识仓；可公开的通用模式另写脱敏版 |
| API key、密码、OAuth token、cookie、私钥 | secret manager / 本地忽略文件 |
| 订单、PDF、CSV、数据库备份、浏览器 profile | 本地或受控业务存储，不进入 Git |

### 防止再次误入公开仓

仓库拆分只降低风险，不能代替门禁。公开仓应同时保留：

1. `scripts/check_secrets.py`：扫描凭证和高风险文件；
2. GitHub secret scanning + push protection：在 push 前拦已知 token 模式；
3. 新增 `scripts/check_sensitive_docs.py`：只扫描**公开仓新增/修改文本**，检查：
   - 公网 IPv4、Tailscale/私网地址；
   - 公司内部域名、SSH 命令、服务器别名和固定端口拓扑；
   - 客户/员工标识与受限业务词；
   - 指向私有 runbook 的内容是否误写成了正文；
4. 明确的 allowlist：测试保留地址、公开官网域名、示例值可逐项豁免，禁止整类关闭；
5. PR 模板增加分类确认：`公开 / 内部 / 秘密 / 业务数据`；
6. Agent 写文档前先分类，无法确定时默认写私有仓，而不是公开仓。

GitHub push protection 只解决「凭证像不像 secret」，自定义文档 lint 才解决「这段话该不该公开」。

### 已经公开过的内容怎么迁移

分两阶段，不直接重写历史：

1. **立即处置**
   - 凭证视为已经泄露：先撤销/轮换，再删文件；只删 Git 内容不算完成；
   - 把内部文档复制到私有仓，公开仓改成脱敏摘要或泛化后的模式文档；
   - 后续链接从真实 runbook 改为「授权用户从私有知识索引查找」。
2. **风险评估后决定是否清历史**
   - 普通内部拓扑通常先从当前分支移除，并按「曾公开」处理；
   - 仍有效的高风险凭证必须轮换，历史清理不能代替轮换；
   - 只有法律、隐私或重大安全风险要求时才用 `git filter-repo` 等重写历史。

历史重写会改所有 commit ID、影响现有 PR/clone/fork，需要强制推送并要求所有协作者重新同步，
属于高影响操作，必须单独评估并由用户明确批准。

## Why This Matters

- 单靠 `.gitignore` 只能保护已知路径，不能保护随手写进 Markdown 的公司细节；
- 单靠 secret scanning 只能识别凭证模式，识别不了「真实拓扑本身不该公开」；
- 把所有内容塞进 Vault 会让文档无法自然搜索、链接和审阅，破坏当前 Agent 工作流；
- 私有 Markdown 仓保留现有写作习惯，bootstrap 把权限和 clone 复杂度压缩成一次操作；
- 三层分离后，无权限同事仍能使用公开项目，授权同事和 Agent 才能获得内部上下文。

## When to Apply

- 新增或更新基础设施、网络、运维、内部 API、客户/员工相关文档之前；
- 给新同事或新 Agent 配置项目环境时；
- 准备共享 `.env`、生产凭证或 CI 变量时；
- 公开仓发现疑似内部资料，需要决定迁移还是脱敏时；
- 评估 Vault、SOPS、密码管理器或 submodule 时。

## Examples

### Agent 记录一次网络故障

- 公开仓：写「直连失败会退回中继；先检查云安全组 UDP 入站」这一通用诊断模式；
- 私有仓：写真实设备、地址、节点、端口、服务单元和现场命令；
- secret manager：保存登录凭证和私钥；
- 本地业务目录：保存抓包、日志原件和含身份信息的附件。

### 非技术同事首次使用

```bash
git clone <public-repo>
cd <public-repo>
uv sync
uv run python scripts/bootstrap_private_knowledge.py
```

有权限时脚本准备内部知识；无权限时公开功能照常可用，并给出清晰状态，不要求用户理解 submodule。

## Related Issues

- 本仓库已有的出口/网络类文档是最典型的迁移对象：它们同时含「通用诊断价值」与「真实拓扑敏感性」，迁移时应拆成公开模式文档与私有 runbook
- [../developer-experience/windows-worktree-claude-md-symlink.md](../developer-experience/windows-worktree-claude-md-symlink.md) —— Windows 与 worktree 下不要依赖脆弱的手工软链步骤
- [../tooling-decisions/ce-okf-conversation-wrapup-skill.md](../tooling-decisions/ce-okf-conversation-wrapup-skill.md) —— 文档级联和提交前凭证扫描流程

## 来源

- GitHub：仓库可见性与私有仓库的访问边界  
  <https://docs.github.com/en/repositories/creating-and-managing-repositories/about-repositories>
- GitHub：Secret scanning 会扫描整个 Git 历史中的已知凭证模式  
  <https://docs.github.com/en/code-security/concepts/secret-security/secret-scanning>
- GitHub：Push protection 在 push 到仓库前阻断受支持的秘密  
  <https://docs.github.com/en/code-security/concepts/secret-security/command-line-push-protection>
- GitHub：泄露后的正确顺序包含撤销凭证；清理仓库不是撤销的替代品  
  <https://docs.github.com/en/enterprise-cloud@latest/code-security/secret-scanning/working-with-secret-scanning-and-push-protection/remediating-a-leaked-secret>
- Git：Submodule clone/update、递归选项与 detached HEAD 行为  
  <https://git-scm.com/book/en/v2/Git-Tools-Submodules>
- SOPS：支持 age/KMS/PGP 的 Git 友好型加密文件工具  
  <https://github.com/getsops/sops>
- 1Password：本地 `.env` 挂载的行为与平台限制  
  <https://developer.1password.com/docs/environments/local-env-file>
- 1Password：Events API 与审计事件  
  <https://developer.1password.com/docs/events-api/introduction>
- HashiCorp：GitOps 中由 Vault 动态提供秘密而不写入 Git  
  <https://developer.hashicorp.com/well-architected-framework/define-and-automate-processes/process-automation/gitops>
- HashiCorp：Vault 的动态秘密、最小权限与审计日志能力  
  <https://developer.hashicorp.com/validated-patterns/vault/vault-agent-approle>
- Infisical：人员/机器身份、限时授权与访问审计概览  
  <https://infisical.com/videos/secrets-management-infisical>
