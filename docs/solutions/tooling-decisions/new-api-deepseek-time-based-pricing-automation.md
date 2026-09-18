---
title: DeepSeek 峰谷分时定价：new-api 静态 ModelRatio 的 cron 定时切换方案
date: 2026-08-31
category: tooling-decisions
module: new-api-deployment
problem_type: tooling_decision
component: tooling
severity: medium
applies_when:
  - new-api（或 one-api 系）对模型按单一静态 ModelRatio 计费，而上游提供方采用峰谷/分时价
  - 需要按北京时间边界自动切换高峰/空闲两档定价的 Docker + MySQL 部署
  - 已确认 new-api 的 options 表未做 Redis 缓存，可直接写库
  - 需要核对网关计费与上游官方账单
symptoms:
  - 用户 7×24 按高峰价计费，含深夜、周末等闲时段
  - new-api 配额与 DeepSeek 官方账单在闲时段对不上
root_cause: missing_tooling
resolution_type: tooling_addition
related_components: [database]
tags: [new-api, deepseek, time-based-pricing, billing, cron, mysql, automation, model-ratio]
---

# DeepSeek 峰谷分时定价：new-api 静态 ModelRatio 的 cron 定时切换方案

## Context

公司运营一套 new-api LLM 网关（QuantumNous/new-api fork），部署在 `api.vilavi.cn`，上海阿里云服务器上 Docker + MySQL + Redis 运行。DeepSeek 自 2026-08-17 起实施峰谷分时计价：高峰时段为北京时间周一至周五 9:00-12:00 与 14:00-18:00（2 倍价），其余为闲时（半价）。官方价目表见 <https://api-docs.deepseek.com/zh-cn/quick_start/pricing/>。

new-api 的 `options` 表里 `ModelRatio`/`CompletionRatio`/`CacheRatio` 是按模型存一份静态 JSON，计费引擎在请求时只读这一个静态值，配置里没有任何"按时间切换"的原语；社区对分时计价的功能请求也尚不成熟/不可靠。结果：公司全天按高峰价计费——即使深夜、周末这些闲时段也按最高档收费，后台无从配置自动切换。

## Guidance

用「cron 准点触发 + 幂等 Python 脚本直写 MySQL options 表」作为务实兜底方案。脚本部署在服务器 `/opt/new-api/deepseek_time_pricing.py`，仓库内路径 `new-api-deployment/deepseek_time_pricing.py`。

核心机制：

1. **北京时间不依赖服务器时区**：用 `zoneinfo.ZoneInfo("Asia/Shanghai")` 取时间，而不是裸 `datetime.now()`（`deepseek_time_pricing.py:61,127`）。

2. **高峰判定**（`deepseek_time_pricing.py:87-92`）：

   ```python
   def is_peak_hour(now: datetime) -> bool:
       """北京时间 周一至周五 9:00-12:00 / 14:00-18:00 为高峰，其余为空闲。"""
       if now.weekday() >= 5:  # 周六日
           return False
       h = now.hour
       return (9 <= h < 12) or (14 <= h < 18)
   ```

3. **内置官方价目表**（`deepseek_time_pricing.py:40-53`）：`deepseek-v4-flash` 与 `deepseek-v4-flash-vision-exp` 同价，`deepseek-v4-pro` 单独，各含 peak/off 两档（元/1M tokens）。

4. **价格换算公式**（`deepseek_time_pricing.py:95-104`，与既有 `sync_pricing.py` 一致）：

   ```python
   model_ratio      = round(price["input"] * QUOTA_PER_UNIT / (1_000_000 * USD_RATE), 6)
   completion_ratio = round(price["output"] / price["input"], 6)
   cache_ratio      = round(price["cache"] / price["input"], 6)
   ```

   其中 `QUOTA_PER_UNIT = 500000`（$1 = 500,000 额度）、`USD_RATE = 7.3`（`deepseek_time_pricing.py:34-35`）。例：flash 高峰 input ¥3/M → ModelRatio = 3×500000/(1e6×7.3) ≈ 0.205479。

5. **直写 MySQL options 表**（`deepseek_time_pricing.py:55-84`）：通过 `docker exec -i new-api-mysql mysql -uroot ... new_api -N -B` 执行 `SELECT value FROM options WHERE \`key\`=...` 与 `UPDATE options SET value=...`。本会话实测 options 在 Redis 无缓存（Redis 里只有 perf/subscription/token 类 key），因此写库立即生效、无需重启。

6. **幂等**（`deepseek_time_pricing.py:107-115`）：读当前值，仅当差异大于 1e-9 才写；只 patch DeepSeek 三个模型，绝不触碰 gpt-5.x 等其他模型。同一时段连跑多次零副作用。

7. **cron 部署**（脚本 docstring `deepseek_time_pricing.py:12-19`）：

   ```
   0 9  * * 1-5  python3 /opt/new-api/deepseek_time_pricing.py >> /var/log/deepseek_time_pricing.log 2>&1
   0 12 * * 1-5  python3 /opt/new-api/deepseek_time_pricing.py >> /var/log/deepseek_time_pricing.log 2>&1
   0 14 * * 1-5  python3 /opt/new-api/deepseek_time_pricing.py >> /var/log/deepseek_time_pricing.log 2>&1
   0 18 * * 1-5  python3 /opt/new-api/deepseek_time_pricing.py >> /var/log/deepseek_time_pricing.log 2>&1
   0 0  * * 0,6  python3 /opt/new-api/deepseek_time_pricing.py >> /var/log/deepseek_time_pricing.log 2>&1
   ```

   周一至周五 9:00 切高峰、12:00 切闲时、14:00 切高峰、18:00 切闲时；周末 00:00 做一次保险。另外追加了 `*/30 * * * *` 低频兜底 cron：因为 cron 不会补跑漏掉的触发（例如服务器恰在边界时刻关机/重启），30 分钟兜底把"陈旧价格"的最坏持续时间从一次漏切（最长约 15 小时，如周五 18:00 切闲时失败）压缩到 30 分钟。

8. **测试入口**：`--simulate peak|off` 强制指定时段跑两个分支（`deepseek_time_pricing.py:119-129`）；实测连跑两次收敛、第二次零写入，证明幂等。

部署前务必先验证"options 不缓存"这个前提（查 Redis key 分布），否则直写库可能被缓存掩盖。

## Why This Matters

- **计费正确性**：修复前闲时（夜间、周末，占一周大多数小时）也按高峰价计费，属于系统性多收。分时价差 2 倍（闲时价格仅为高峰一半），影响直接落到用户账单。
- **直写 DB 为何可行**：new-api 的 options 在 Redis 无缓存，写库即时生效；若想当然假设有缓存，就会误判需要额外的失效手段。这是"先验证再假设"的典型。
- **幂等是安全网**：cron 可能被手动重跑、服务器重启后补跑、或与边界触发重叠，幂等保证重复执行无副作用，让"低频兜底 cron"可以放心叠加。
- **兜底 cron 的必要性**：cron 不补跑错过的触发点，30 分钟轮询把最坏陈旧价窗口从 ~15 小时压到 30 分钟，且低频不引入计费抖动。

## When to Apply

- new-api（或分支）对上游模型按单一静态 ModelRatio 计费，而上游提供方（DeepSeek 等）采用峰谷/分时价。
- 部署形态是 Docker + MySQL，可直接经 `docker exec` 写库，且已确认 options 未进 Redis 缓存。
- 需要精确对齐北京时间边界的场景（用 `zoneinfo` 而非服务器本地时区）。
- 对"换价那一刻的瞬时不精确"可容忍，接受脚本按内置官方价目表常量切换（而非实时拉取官方价格）。

## Examples

**Cron 日志实际切换记录**（`/var/log/deepseek_time_pricing.log`）：
- 08-28 18:00 → 切到闲时价
- 08-31 09:00 → 切到高峰价
- 周末全天保持在闲时价

**账务交叉验证（周六）**：DeepSeek 官方账单 CSV 与 new-api 内部日志对账——周六所有调用都落在闲时档（pro 的 input_cache_hit 0.15/M 等）；官方周六费用 = 5.8895（pro）+ 2.7906（flash）= 8.68 元；new-api 侧额度消耗 594,541，594,541 / 68,493 ≈ 8.68 元，**完全一致**。周五官方 CSV 同时出现高峰与闲时两档价格，佐证 18:00 切换点生效。

**幂等验证**：`--simulate peak` 与 `--simulate off` 各跑一遍两个分支都正确；同一时段连跑两次，第二次输出"无变更"。

**切换前/后效果**：
- Before：全天按高峰价计费（flash input ¥3/M），闲时用户被多收 2 倍。
- After：周一至周五 9-12/14-18 按高峰价（flash input ¥3/M），其余时间与周末按闲时价（flash input ¥1.5/M）。

## Related

- 脚本本体：`new-api-deployment/deepseek_time_pricing.py`（仓库内 + 部署到 /opt/new-api/）
- 参考脚本（换算公式来源，但只 PRINT 不写库）：`new-api-deployment/sync_pricing.py`
- 部署模式参考（docker exec mysql + cron，含订阅计划绑定）：`new-api-deployment/auto-bind-subscription.py`
- 同场次的订阅配置变更：新建订阅计划 `Daily-30RMB`（total_amount=2054790、quota_reset_period=daily），并将某用户当前订阅通过 UPDATE `user_subscriptions`（plan_id、amount_total、amount_used=0）切换过去。
- 相关方案文档（同模块、同"外部 cron 脚本直写库"模式）：[dingtalk-sso-new-api-oidc-bridge.md](../integration-issues/dingtalk-sso-new-api-oidc-bridge.md)
- 相关集成问题（new-api 网关 + CLIProxyAPI 上游限流上下文）：[chatgpt-edu-cliproxyapi-429-rate-limit.md](../integration-issues/chatgpt-edu-cliproxyapi-429-rate-limit.md)
