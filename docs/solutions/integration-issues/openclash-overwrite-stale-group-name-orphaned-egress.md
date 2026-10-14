---
okf: v0.1
type: Reference
title: OpenClash 覆写脚本写死策略组名，让自建应急出口长期「活着但没接线」
description: 办公室 OpenClash 的 openclash_custom_overwrite.sh 里 inject_emergency() 写死了上一代订阅（SSRDog）的组名 Auto，现役订阅叫『自动选择』，find 返回 nil 即静默跳过 —— 应急出口 Emergency 在运行配置里零入向引用，链路是活的却收不到任何流量。附「数入向引用」的定界法、副本干跑→重载→端到端换出口的验证顺序，以及为什么不能顺手把它塞进自动组。
date: 2026-10-14
category: integration-issues
module: us_openai_api_proxy
problem_type: integration_issue
component: tooling
severity: medium
applies_when:
  - "改动或排查 OpenClash 自定义覆写脚本（/etc/openclash/custom/openclash_custom_overwrite.sh）时"
  - "订阅/供应商更新后，怀疑某个策略组或节点『看起来在配置里，其实没生效』时"
  - "给下发式配置写幂等注入逻辑，要分清『脚本跑过了』与『注入结果真的生效了』时"
  - "想确认自建应急出口（节点 SH-Tailscale-US / 策略组 Emergency）到底有没有流量路径能走到它时"
symptoms:
  - "策略组 Emergency 在运行配置里入向引用为零 —— 没有路由规则指向它，也没有别的组把它列为成员"
  - "应急链路两段都正常（SOCKS5 可通、出口是美国 Vultr、Tailscale peer 为 direct），但没有任何流量能走到它"
  - "inject_emergency() 运行无异常、无告警、日志照常打印成功，功能却从未生效（静默 no-op）"
tags: [openclash, openwrt, subscription-drift, proxy-group, silent-failure, idempotent-script, egress, fallback]
related_components: [us_openai_api_proxy, openwrt]
---

# OpenClash 覆写脚本写死策略组名，让自建应急出口长期「活着但没接线」

## Context

北京办公室的 OpenWrt 路由跑 OpenClash（mihomo / Meta 内核），出海节点由订阅商下发。除主订阅外，还有一条**自建应急出口**，链路见 [办公室出口拓扑与应急链路](../architecture-patterns/office-egress-fallback-chain.md)：

```
办公室 → OpenClash 节点 SH-Tailscale-US (socks5)
        → 上海服务器 Tailscale IP:1080（systemd 跑的 ssh -N -D 动态转发 → SOCKS5）
        → 美国 Vultr → 出海
```

它在 OpenClash 里是一个 `type: select` 的**策略组 `Emergency`**，成员 `SH-Tailscale-US` + `DIRECT` —— 设计上**只许人工切换、永不被自动选中**。

OpenClash 每次重启、每次订阅更新都会**重新生成配置**，并把 `/etc/openclash/custom/openclash_custom_overwrite.sh`（自定义覆写脚本）重跑一遍，把自建的策略组「打补丁」进新生成的 config。`Emergency` 就是靠这个脚本注入并挂线的。

> ℹ️ 该脚本跑在路由器上，**本仓库不跟踪它**；下面的代码片段摘自现场脚本，属运维现场证据，不在本仓库内可复现。

**触发问题**：2026-10-13，运维看着自定义规则问了一句 —— 「我们这条应急线，到底有没有在用？我看它几乎没被提到。」这个直觉正好命中了本篇要处理的裂缝。

> **这不是一条新原则，而是一次事故正文。** 这条坑的**原则**此前已经写在模块自己的经验里：
> [`us_openai_api_proxy/docs/lessons/lessons-learned.md`](../../../us_openai_api_proxy/docs/lessons/lessons-learned.md)
> **Lesson 9「代理策略组名称不是稳定接口」** 就是本篇的根因，**Lesson 11「自定义覆写必须可重复执行」** 就是本篇的修法。
> 缺的从来不是知识，而是**可复现的事故、以及「怎么发现它其实早就悄悄失效了」的检测手段** —— 补的就是这一段。

## Guidance

### 1. 先定界：「活着」和「接上了」是两回事

不要读 UI，直接枚举**运行中配置**的 `proxy-groups`，统计每个组名被**入向引用**了多少次（被路由规则指向 + 被其它组列为成员）：

```ruby
yml  = YAML.load_file('/etc/openclash/<订阅名>.yaml')   # 内核实际加载的那份
refs = Hash.new(0)
(yml['proxy-groups'] || []).each do |g|
  refs[g['name']] += 1                                     # 自身名字记一次基线
  (g['proxies'] || []).each { |m| refs[m] += 1 }           # 被别的组当成员
end
(yml['rules'] || []).each do |r|
  refs[r.to_s.split(',').last.to_s.strip] += 1             # 被路由规则指向
end
puts refs['Emergency']    # => 1，即只剩基线，入向引用为 0
```

实测结果：`Emergency` 的入向引用是 **零** —— 没有任何 `rules` 指向它，也没有任何其它组把它列为成员。

但这条线**本身是活的**：端到端实测 `SH-Tailscale-US` 的 SOCKS 出口返回美国 Vultr 的 `149.28.67.226`，`tailscale status` 里对端是 `direct` 而非中继。两段链路都正常，**只是没有任何流量能走到它**。定性为一句话：

> **alive but unwired —— 活着，但没接线。**

### 2. 根因：写死了上一代订阅的组名

同一个覆写脚本里，`inject_emergency()` 的收尾是：

```ruby
# 确保 Emergency 在 Auto fallback 末尾（SSRDog 优先，Emergency 兜底）
auto = cfg['proxy-groups'].find { |g| g['name'] == 'Auto' };
if auto && auto['proxies']
  auto['proxies'].delete('Emergency');
  auto['proxies'].push('Emergency');
end
```

它找的是一个**字面叫 `Auto`** 的组 —— 那是**上一代订阅（SSRDog）**的命名。现役订阅里同一个位置叫 `自动选择`。于是 `Array#find` 返回 `nil`，`if` 分支被整段跳过，**不抛异常、不报错、不告警**，脚本末尾的成功日志照常打印。结果是：**在现役订阅的命名下（配置里压根没有叫 `Auto` 的组），这段「把应急线挂成兜底」的意图每次重跑都会被跳过** —— 而日志上完全看不出区别。（注：模块 `docs/log.md` 2026-07 记过一次「增加可重复注入的应急 fallback、修正 fallback 优先级」，说明这套机制在更早的命名下曾经对上过；**组名漂移之后，它就只剩一句成功日志了**。）

第二块拼图在同一个文件的 `add_country_groups()` 里 —— 真正承载 AI 流量的组 `AI 出口`，成员是一段**硬编码字面量**：

```ruby
ai_members = ['自动选择','日本','美国','香港','新加坡','台湾','故障转移'];
```

这里**从头到尾没提过 `Emergency`**。两处「本应把应急线接上」的代码，一处因组名漂移而空转，一处因成员表写死而遗漏 —— **同一类病因，两个不同位置**。

### 3. 修法：改幂等注入脚本，不改运行中的 config

在 `add_country_groups()` 的成员字面量末尾**追加** `'Emergency'`：

```ruby
ai_members = ['自动选择','日本','美国','香港','新加坡','台湾','故障转移','Emergency'];
```

**关键是改脚本、而不是直接改 live config**：OpenClash 每次重启 / 订阅更新都会重新生成 config 并重跑覆写脚本，**手改运行中的 YAML 会被静默回滚** —— 那会重演同一种「看似修好、实则没修」的失败模式。动手前先备份（`*.bak-<用途>-<timestamp>`）。

### 4. 验证顺序（建议照抄）

1. **先在副本上干跑** —— 把 live config 复制到临时文件，对着副本跑覆写脚本，检查产出的组员表尾部是否真的挂上了 `Emergency`。**对生产零风险**。
2. **重载 OpenClash**（`/etc/init.d/openclash restart`），确认内核回来了，并通过**内核的 REST API 读回真实组员表** —— 不要只信脚本那行成功日志。
3. **端到端**：把选择组切到 `Emergency`，用一条**确实走该路径**的服务证明出口真的变了，再切回来复验：

```bash
curl -s https://chatgpt.com/cdn-cgi/trace
# ip=149.28.67.226
# loc=US
```

出现 `ip=149.28.67.226` / `loc=US`，才说明流量**真的**从美国 Vultr 出去了 —— 而不是只看到选择组的 UI 变了。

### 5. 刻意不做的事，以及为什么

这些「没做」本身就是本篇要留存的判断：

| 没做 | 原因 |
|---|---|
| **不**把应急线加进自动 `url-test` 组（`自动选择`） | 那个组是**全办公室**的日常出口。url-test 按延迟探测，**可能选中应急线**，随后**全办公室流量都挤上一条窄带、限速的跨境 SSH 隧道**。仓库里已记录过一次正是如此的历史事故（「应急出口被持续占用，主线路恢复后没切回来」）。 |
| **不**顺手去修那处失效的 `Auto` 查找 | 同理 —— 「修好」它等于把应急线塞进日常自动组，触发的正是上一条的危害。 |
| **不**碰 `故障转移`（fallback）组 | 它的成员表开头是订阅下发的**信息型伪节点**（`剩余流量：… GB` / `距离下次重置剩余：… 天` / `套餐到期：…`），这些**不是真代理**，所以该组当前处于**空转**。修它是另一件事，别混进来。 |

由此浮出的**设计原则**：应急通道应当**只可人工选择、不可自动选中**。它的价值来自「别的全挂了时由人来点它」，它的代价是「又贵又慢、且极易被遗忘」—— 自动选中会直接吃掉这份价值。

### 6. 可迁移的教训

1. **对「下发式配置」而言，一切硬编码的名字都是一份没有版本化的外部契约。** 订阅、模板、脚手架生成的 config 里，任何写死的组名 / 节点名 / 端口，都会在下游改名时**静默漂移**。
2. **`find` 后跳过（或任何吞掉 `nil` 的空操作保护）是最危险的失败模式**：脚本报成功、运维看不到报错、能力悄悄消失。宁可在**锚点缺失时大声失败 / 告警**，也别静默空转。
3. **注入脚本的幂等判据要校验「结果」而非「执行」**：不是「我的代码路径跑过了吗」，而是「被注入的对象现在**存在且被引用**了吗」。
4. **判断「这东西到底接上线没有」，从 config 查比从 UI 查更便宜**：枚举组、数入向引用即可。一个**孤儿组在控制台里渲染得完全正常**，只是永远收不到流量。
5. **修完脚本，还要复核 live 产物**（`/etc/openclash/` 下的 change 记录、经内核 REST API 读到的组员表），而不是相信脚本那行日志就代表改动落地。

## Why This Matters

- **静默的能力丢失比崩溃更贵。** 这条应急线是「主订阅全挂时唯一能救场」的那条。它掉线没有告警、没有报错、UI 上一切正常 —— 真正的暴露时机将是**某天主订阅真的挂了、有人去点 `Emergency`、却发现点什么都没反应**。故障被推迟到了最不能承受它的时刻。
- **名字漂移是系统性的，不是一次性的。** 只要覆写脚本还硬编码外部名字，下次订阅改结构（改组名 / 改节点名 / 改端口）就会再演一次。`Auto` → `自动选择` 只是这一类的其中一例。
- **改错方向的代价是全办公室级的。** 本案的诱惑是「顺手把 `Emergency` 也塞进自动组让它『更有用』」。真那么做，一次延迟探测就能把全办公室流量压上跨境窄带隧道，且因为人工切换的历史惯性，很可能**恢复后忘了切回来** —— 这正是仓库里已有的那条旧事故。
- **幂等脚本的价值正在于「每次重生成都成立」。** 手改 live config 会在下一次订阅更新时被静默抹掉，看似修好、实则没修 —— 与最初的 bug 是同一种失败模式。

## When to Apply

- 集成任何**下发式配置**的供应商（订阅 / 模板 / 脚手架 / 自动生成的 YAML、JSON）时，凡是在自定义脚本里**写死了对方的名字**（组名、节点名、端口、字段路径）。
- 排查「某条链路 / 某个开关**看起来配了、实际没用上**」—— 先数入向引用，别只读 UI。
- 维护 `openclash_custom_overwrite.sh` 这类**每次重生成都要重跑**的覆写脚本时（改脚本，不改 live）。
- 回答任何**出口 / 应急线**问题之前 —— 连同 [办公室出口拓扑与应急链路](../architecture-patterns/office-egress-fallback-chain.md) 一起读。
- 设计任何「代价高、只在兜底时用」的通道（应急出口、降级缓存、逃生开关）时，先想清楚它该**人工触发**还是**自动选中**。

## Examples

**Before —— 应急线被孤立：**

```ruby
# inject_emergency()：找 'Auto'，但现役订阅早已把它叫 '自动选择' → find 返回 nil，整段静默跳过
auto = cfg['proxy-groups'].find { |g| g['name'] == 'Auto' };
if auto && auto['proxies']
  auto['proxies'].delete('Emergency');
  auto['proxies'].push('Emergency');
end

# add_country_groups()：成员表写死，压根没有 Emergency
ai_members = ['自动选择','日本','美国','香港','新加坡','台湾','故障转移'];
```

⇒ `refs['Emergency'] == 0`：无规则指向、无组收编 —— 链路虽活，却收不到任何流量。

**After —— 应急线接进 `AI 出口`，且仍保持人工切换：**

```ruby
ai_members = ['自动选择','日本','美国','香港','新加坡','台湾','故障转移','Emergency'];
```

**验证（顺序不可颠倒）：**

```bash
# 1) 副本干跑，先看组员表有没有真的落到末尾 —— 零风险
cp /etc/openclash/<订阅名>.yaml /tmp/dryrun.yaml
# ...对 /tmp/dryrun.yaml 跑覆写脚本，检查 'AI 出口' 的 proxies 尾部是否为 'Emergency'

# 2) 重载 + 从内核 REST API 读回真实组员表（别只信脚本日志）
/etc/init.d/openclash restart

# 3) 端到端：切到 Emergency，证明出口换了，再切回
curl -s https://chatgpt.com/cdn-cgi/trace   # 期望 ip=149.28.67.226 / loc=US
```

## Related

- [办公室出口拓扑与应急链路（OpenClash ↔ 上海跳板 ↔ 美国 Vultr）](../architecture-patterns/office-egress-fallback-chain.md) —— 应急链路两端（OpenClash 的 `SH-Tailscale-US` socks5 节点 ↔ 上海 systemd 的 `ssh -D` SOCKS5）、出口 IP 判据，以及「应急出口被持续占用、主线路恢复后没切回来」的历史事故；本篇是它在「自定义覆写脚本」一侧的延伸。
- [`us_openai_api_proxy/docs/lessons/lessons-learned.md`](../../../us_openai_api_proxy/docs/lessons/lessons-learned.md) —— **Lesson 9「代理策略组名称不是稳定接口」= 本篇根因；Lesson 11「自定义覆写必须可重复执行」= 本篇修法**。本篇是这两条抽象原则的第一份可复现事故正文，不要反向当成新发现。
- [扫描类脚本防「静默丢数」——反转匹配方向](../best-practices/scanner-silent-data-loss-guard.md) —— **同型失效模式**：匹配/查找为空时脚本照常跑完、照常报成功，只是什么都没做。该文的对策（fail-loud、数量对账）可直接类比：注入后应断言目标组真的挂上了成员。
- `us_openai_api_proxy/docs/log.md` —— 应急出口历次变更的时序记账；本次修复应在此追加一条。
