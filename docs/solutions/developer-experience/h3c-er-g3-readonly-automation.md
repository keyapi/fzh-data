---
okf: v0.1
type: Reference
title: H3C ER G3 后台只读自动化登录（过期证书 / RSA / 验证码 / 不打印密码）
date: 2026-11-17
category: developer-experience
module: us_openai_api_proxy
problem_type: developer_experience
component: tooling
severity: low
applies_when:
  - "要用浏览器自动化只读核对 H3C / ER 系列路由器配置"
  - "自动化登录被证书错误挡住、或被 RSA 加密密码/验证码卡住"
  - "需要用到 .env 里的密码但不想把它打印到对话/日志"
tags: [browser-automation, playwright, h3c, login, captcha, rsa, credentials]
related_components: [us_openai_api_proxy, web_automation, openwrt]
---

# H3C ER G3 后台只读自动化登录（过期证书 / RSA / 验证码 / 不打印密码）

## Context

核对办公室 H3C（ER3208G3-P-E，Release 0136P01）配置时需要浏览器自动化。它的 Web 后台有四个门槛，
逐个试错会浪费很多轮：

1. **HTTPS 证书是 2011 年过期的自签证书**（CN=`LEDE`）→ Chrome 直接拦成"隐私设置错误"。
2. **密码是前端 RSA 加密**（页面加载 `jsencrypt.js`，提交时 `encrypt.encrypt(auth)`）。
   用 `form.submit()` 绕过 JS 直接 POST → 服务端 500。
3. **验证码**（`#canvas_draw` + `#vertify_code`）平时隐藏，失败后才出现；验证码明文由服务端下发。
4. 凭据在 `.env`，但**不能把密码打印到对话或日志**。

## Guidance

### 1. 证书：在主页面点一次"继续"即可

不要每次 newContext。在**主页面**上：

```js
try { await page.goto('https://<router>/cgi-bin/luci'); } catch (e) {}
await page.click('#details-button');
await page.click('#proceed-link');   // 该 context 记住例外，后续正常工具都能用
```

这样不需要 `ignoreHTTPSErrors` 的新 context，也就不用**反复新开窗口**。

### 2. 密码：点按钮，别 `form.submit()`

```js
await page.fill('#luci_username', user);
await page.fill('#focus_password', pass);
await page.click('#login');          // 页面 JS 负责 RSA 加密
```

`#login` 在 `window.onload` 后才可用；若仍是 disabled，再 `removeAttribute('disabled')`。

### 3. 验证码：服务端明文，不用 OCR

- 正常情况验证码**不显示**（`canvas_draw` display:none），提交走"无验证码"分支即可。
- 一旦触发验证码而提交里没有它，服务端固定返回 `验证码错误。`——所以出现一次失败后要按下面走。
- 明文来源：`POST /cgi-bin/luci/admin/rest`，body `getVertifyCode=right`，返回 JSON 的 `vertifycode`。
- 拿不到时强制显示验证码区，让提交走验证码分支：

```js
const cap = JSON.parse(await page.evaluate(async () =>
  (await (await fetch('/cgi-bin/luci/admin/rest',{method:'POST',
    headers:{'Content-Type':'application/x-www-form-urlencoded'},
    body:'getVertifyCode=right'})).text())).vertifycode);
await page.evaluate(() => {
  document.querySelector('.vercode').style.display='inline';
  document.getElementById('canvas_draw').style.display='block';
});
await page.fill('#vertify_code', cap);   // 必须在填完账号密码之后再填
await page.click('#login');
```

> 验证码是**客户端绘制**的（`draw()` 把服务端下发的字符串画到 canvas），所以明文可取，不必上 ddddocr。
> 仓库里通途那套 `ddddocr` 方案用于真正的图片验证码（`web_automation/cdp-based/get_captcha.py`），此处用不上。

### 4. 凭据不外泄：本机一次性接口 + Playwright 的 `request`

自动化脚本（`browser_run_code_unsafe`）的沙箱**没有 Node API**（无 `require`/`process`/动态 import），
读不了 `.env`；而页面里的 `fetch('http://127.0.0.1:...')` 会被 PNA/混合内容拦掉。

可行组合：

1. 起一个只监听 `127.0.0.1` 的极小 HTTP 服务，读 `.env` 后返回 `user\npass`（跑完立即停）；
2. 在浏览器自动化里用 **Playwright 的 `page.request.get(...)`**（Node 侧发请求，无 CORS/PNA）：

```js
const creds = await (await page.request.get('http://127.0.0.1:8765/')).text();
const [u, p] = creds.split('\n');
```

这样密码只在两端之间流动，**不进对话、不落盘**。用完 `TaskStop` 停掉服务。

### 5. 只读核对：直接用 hash 路由

登录后是 hash SPA，不必逐级点菜单，直接改 `location.hash` 后等渲染、读 `innerText`：

```
网络设置/外网配置   #admin/networknew/wansetting/wansetting
修改多WAN策略       #admin/networknew/wansetting/wanpolicy
LAN/VLAN配置        #admin/networknew/lansetting/lansetting
静态DHCP            #admin/networknew/lansetting/dhcp
MiniAP 配置模板     #admin/miniAP/miniAPconfigmanage/configtemplate
在线AP列表          #admin/miniAP/onlineAPmanage/onlineAPlist
静态路由            #admin/advancedsetting/staticrouting
策略路由            #admin/advancedsetting/policybaserouting
静态DNS             #admin/advancedsetting/ApplicationService/staticDNS
本地域名服务        #admin/advancedsetting/ApplicationService/localdomain
配置备份/导出       #admin/systemTools/configManage/backup
```

配置导出：点「导出当前配置」→ 浏览器下载 `Configuration_H3C_<model>_<时间戳>.rar`。
该文件含管理员等敏感信息，**归档到 gitignore 的 `secrets/`，不要提交**。

## Why This Matters

- 证书 + RSA + 验证码三层叠加，任何一层用错都会得到误导性错误（400/500/验证码错误），
  很容易误判成"密码不对"。
- 把密码打印到对话是最常见的偷懒做法，但它会留在会话记录/日志里；本机一次性接口只在进程间传递。

## When to Apply

- 需要核对/备份 H3C ER 系列（或同源 LuCI 定制固件）配置；
- 自动化登录被证书/加密/验证码挡住时。

## Related

- [us_openai_api_proxy/AGENT_HANDOFF.md](../../../us_openai_api_proxy/AGENT_HANDOFF.md)
- [web_automation/AGENT_HANDOFF.md](../../../web_automation/AGENT_HANDOFF.md) —— 验证码 OCR（ddddocr）与 `dispatch.py` 状态机
- [../architecture-patterns/office-dual-wan-direct-ssid.md](../architecture-patterns/office-dual-wan-direct-ssid.md) —— 本工具读到的配置结论
- [shallow-clone-update-index-date-drift.md](shallow-clone-update-index-date-drift.md) —— 同属 worktree 下的脚本/索引坑
