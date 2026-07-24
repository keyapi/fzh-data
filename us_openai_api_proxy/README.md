# US OpenAI API Proxy

> 在 US Ubuntu 服务器上部署 CLIProxyAPI，通过 Tailscale 虚拟网络供北京办公室员工使用 ChatGPT API。

## 做了什么

部署开源项目 [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI)，将 ChatGPT 网页订阅账号转为标准 OpenAI API 兼容接口。通过 [Tailscale](https://tailscale.com) 组建中美虚拟局域网，北京员工通过 Tailscale 虚拟 IP 或 LAN 网关直接调用 API。

## 为什么这样做

- **ChatGPT 订阅无法分享 API**：网页版订阅需要代理转为 API 才能给团队用
- **Tailscale P2P 直连免中继**：北京↔US P2P 打洞成功，延迟 ~260ms，DERP relay 兜底
- **LAN 网关降低接入成本**：同事无需装 Tailscale，改 Codex++ URL 即可

## 当前状态

| 项目 | 状态 |
|------|------|
| 部署位置 | ⚠️ 已放弃 Windows Server，待迁移至 Ubuntu 24.04 (1C2G) |
| 网络 | Tailscale P2P/DERP ~260ms |
| 软件 | CLIProxyAPI v7.2.16 |
| 账号 | 免费账号 (待升级付费) |

## 架构

```
北京 ──Tailscale──→ US Ubuntu ──→ ChatGPT API
  │                   └─ CLIProxyAPI (systemd)
  └─ LAN 网关 :3000 ──→ 同事 PC
```

## 快速开始

见 [AGENT_HANDOFF.md](./AGENT_HANDOFF.md)（Agent 接手）或 [docs/architecture.md](./docs/architecture.md)（架构详解）。

## 目录

```
us_openai_api_proxy/
├── README.md              ← 你在这里
├── AGENT_HANDOFF.md       ← Agent 接手参考
├── .env.example           ← 环境变量模板
├── .env                   ← 实际配置 (gitignore)
├── .gitignore
├── tools/
│   └── lite_lan_proxy.py  ← LAN 网关轻量反代
└── docs/                  ← OKF v0.1 bundle
    ├── index.md
    ├── log.md
    ├── architecture.md
    ├── lan-gateway.md
    ├── lessons/
    │   └── lessons-learned.md
    └── reference/
        └── tools-index.md
```
