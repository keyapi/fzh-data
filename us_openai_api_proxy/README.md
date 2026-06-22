# US OpenAI API Proxy

> 在 US Vultr Windows 虚拟机上部署 CLIProxyAPI，通过 Tailscale 虚拟网络供北京办公室员工使用 ChatGPT API。

## 做了什么

在一台 US Vultr Windows Server 2022 虚拟机上部署开源项目 [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI)，将 ChatGPT 网页订阅账号转为标准 OpenAI API 兼容接口。通过 [Tailscale](https://tailscale.com) 组建中美虚拟局域网，北京员工通过 Tailscale 虚拟 IP 直接调用 API，不需要公网暴露端口。

## 为什么这样做

- **向日葵国际版跨境收费**：免费账号不允许跨境访问 US 电脑
- **ChatGPT 订阅无法分享 API**：网页版订阅需要代理转为 API 才能给团队用
- **Tailscale P2P 直连免中继**：实测北京↔US P2P 打洞成功，延迟 ~260ms，不需要额外部署中转服务器

## 架构

```
北京电脑 (Tailscale) ──P2P 直连──→ US Vultr VM (Tailscale)
                                       └─ CLIProxyAPI :8317
                                       └─ ChatGPT OAuth
```

- CLIProxyAPI 仅监听 Tailscale 虚拟 IP（100.x.x.x），公网不可达
- 无需额外中转服务器（HK 阿里云不参与）
- P2P 打洞成功则不依赖 Tailscale DERP 中继

## 快速开始

见 [AGENT_HANDOFF.md](./AGENT_HANDOFF.md)（Agent 接手）或 [docs/architecture.md](./docs/architecture.md)（架构详解）。

## 目录

```
us_openai_api_proxy/
├── README.md              ← 你在这里
├── AGENT_HANDOFF.md       ← Agent 接手参考
├── .env.example           ← 环境变量模板
├── .gitignore
└── docs/                  ← OKF v0.1 bundle
    ├── index.md
    ├── log.md
    ├── architecture.md
    ├── lessons/
    │   └── lessons-learned.md
    └── reference/
        └── tools-index.md
```
