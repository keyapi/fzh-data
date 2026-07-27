# Portal PoC — FZH AI 统一接入 C′

同域 nginx 门户：`/chat` → Open WebUI 壳，`/ops` → 板 PoC stub（candidates 只读）。钉钉 OIDC 可选。

| 角色 | 入口 |
|------|------|
| 人 | 本文 |
| Agent | [AGENT_HANDOFF.md](AGENT_HANDOFF.md) |
| OKF | [docs/index.md](docs/index.md) |
| 验收报告 | [docs/specs/2026-07-24-portal-e2e.md](docs/specs/2026-07-24-portal-e2e.md) |

## 一键启动

```powershell
# 1) 壳（若未起）
cd ai_access_poc/open_webui
docker compose up -d

# 2) Portal
cd ../portal
powershell -ExecutionPolicy Bypass -File scripts/start_portal.ps1
# 浏览器 http://127.0.0.1:8088/
```

Bash：`bash scripts/start_portal.sh`

## 路由

| 路径 | 后端 |
|------|------|
| `/` | 门户落地页 |
| `/chat/` | Open WebUI（`open_webui_public` 网上的 `open-webui:8080`） |
| `/ops/` | `ops-stub`（读 `board/out` candidates / sellers） |
| `/oidc/` | 钉钉 OIDC 桥（`docker compose --profile dingtalk`） |
| `/health` | 门户健康检查 |

## 钉钉 SSO（可选）

1. 填 `.env`：`DINGTALK_CLIENT_ID` / `DINGTALK_CLIENT_SECRET` / `ALLOWED_CORP_ID`
2. `DINGTALK_ENABLED=1`
3. `docker compose --profile dingtalk up -d --build`
4. Discovery：`http://127.0.0.1:8088/oidc/.well-known/openid-configuration`

无密钥时保持 dry-run：访问 `/oidc/` 返回 503 JSON 说明如何启用。

## 运营审

**DEFERRED** — 本 Portal PoC 不阻塞于运营签字。见 `board/docs/specs/ops-review-brief.md`。

## E2E

```powershell
uv run python scripts/e2e_verify.py
```

## 明确不做

全量 CI、赛狐写 API、把 IvyeaOps AGPL 整仓 vendoring 进 fzh-data、生产 HTTPS 上线。
