---
okf: v0.1
type: Reference
title: 网点参数台演示
tags: [ops-assistant, demo]
---

# 网点参数台

银行内部竞赛用的网页演示。数据是假的。右侧助手会调用真实模型，但改数和交单要等页面上点允许。

## 本地运行

需要 Python 3.10 以上。没有第三方包。

```bash
cp .env.example .env
# 编辑 .env，填入模型网关地址和 Key
python server.py
```

浏览器打开 http://127.0.0.1:8765/ 。

密钥只留在运行这台机器的 `.env` 里，不会发到浏览器。

## 给评审看的顺序

1. 右上角保持「林晓 · 柜面主管」。点「演示 · 改测试限额」。测试限额变为 20 万，生产仍是 50 万，并提交一张变更单。这一段不调用模型。
2. 点「演示 · 越权被拒绝」。同步生产、导出客户清单都会被拒绝，审计里有记录。
3. 换成「陈默 · 综合柜员」。生产限额那一行和变更单菜单消失。
4. 换回主管。在底部输入框自己说一句话，例如「把测试限额改成 15 万，并提交工单」。助手先框出当前数字，再给出提案。点允许后才改。
5. 若当前已经是你说的那个数，它不改数，也不提交变更单，只在审计记「未改动」。

涉及改数、导出或越权时，对话里会出现「安全护栏」：岗位白名单、生产写保护、客户信息不出域、无差额不立项、人工确认。

## 部署到一台 Linux

在仓库根目录执行。`.env` 只放在服务器上。

```bash
sudo useradd --system --home /opt/branch-param-desk --shell /usr/sbin/nologin desk
sudo mkdir -p /opt/branch-param-desk
sudo cp server.py index.html /opt/branch-param-desk/
sudo cp -r kb /opt/branch-param-desk/
sudo cp .env.example /opt/branch-param-desk/.env
sudoedit /opt/branch-param-desk/.env
sudo chown -R desk:desk /opt/branch-param-desk
sudo cp deploy/branch-param-desk.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now branch-param-desk
```

要让别人从浏览器打开，把 `.env` 里的 `HOST` 改成 `0.0.0.0`，并用安全组或防火墙只放行需要的来源地址。默认只监听本机。

## 不要提交的东西

`.env`、私钥、客户数据。`.gitignore` 已忽略 `.env`。
