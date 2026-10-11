---
okf: v0.1
type: Reference
title: 网点参数台演示
tags: [ops-assistant, demo]
---

# 网点参数台

银行内部竞赛用的网页演示。数据是假的。右侧助手会调用真实模型，但改数和交单要等页面上点允许。

## 模型配置

使用 OpenAI 兼容接口，只需要这两项：

- `OPENAI_API_BASE_URL`：以 `/v1` 结尾，例如 `https://api.openai.com/v1`
- `OPENAI_API_KEY`：该地址对应的密钥

可选 `OPENAI_MODEL`，默认 `deepseek-v4-flash`。密钥只放在运行机器的 `.env`，不进仓库，也不发到浏览器。

## 本地运行

需要 Python 3.10 以上。没有第三方包。

```bash
cp .env.example .env
# 编辑 .env，填入上面的地址和 Key
python server.py
```

浏览器打开 http://127.0.0.1:8765/ 。

## 给评审看的顺序

1. 右上角保持「林晓 · 柜面主管」。点「演示 · 改测试限额」。测试限额变为 20 万，生产仍是 50 万，并提交一张变更单。这一段不调用模型。
2. 点「演示 · 越权被拒绝」。同步生产、导出客户清单都会被拒绝，审计里有记录。
3. 换成「陈默 · 综合柜员」。生产限额那一行和变更单菜单消失。
4. 换回主管。在底部输入框自己说一句话，例如「把测试限额改成 15 万，并提交工单」。助手先框出当前数字，再给出提案。点允许后才改。
5. 若当前已经是你说的那个数，它不改数，也不提交变更单，只在审计记「未改动」。
6. 「页面助手试试」用 page-agent 自己在页面上找控件。限额表下面有一个后加的「值班备注」，旧助手没有这个工具，点这一颗会去填它。每一步仍要先点允许。模型请求由本机 `/v1` 转发，密钥不到浏览器。

涉及改数、导出或越权时，对话里会出现「安全护栏」：岗位白名单、生产写保护、客户信息不出域、无差额不立项、人工确认。

为什么要先查再改、护栏为什么不看整句话，见 [branch-param-desk-read-then-guard.md](../docs/solutions/architecture-patterns/branch-param-desk-read-then-guard.md)。

## 部署到一台 Linux

在本模块目录执行。`.env` 只放在服务器上。本仓库若没写本目录 `.env`，会再读上一级已有的 Open WebUI 环境文件，方便本机开发。

```bash
sudo useradd --system --home /opt/web-ai-assistant --shell /usr/sbin/nologin desk
sudo mkdir -p /opt/web-ai-assistant
sudo cp server.py index.html /opt/web-ai-assistant/
sudo cp -r kb /opt/web-ai-assistant/
sudo cp .env.example /opt/web-ai-assistant/.env
sudoedit /opt/web-ai-assistant/.env
sudo chown -R desk:desk /opt/web-ai-assistant
sudo cp deploy/web-ai-assistant.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now web-ai-assistant
```

要让别人从浏览器打开，把 `.env` 里的 `HOST` 改成 `0.0.0.0`，并用安全组或防火墙只放行需要的来源地址。默认只监听本机。

## 不要提交的东西

`.env`、私钥、客户数据。`.gitignore` 已忽略 `.env`。
