FROM python:3.12-slim

WORKDIR /app

# 只有一个三方依赖；其余全部标准库 + 仓库自带的 NAS_API
COPY nas_mcp/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 复用仓库里已验证的 DSM 客户端
COPY NAS_API/ ./NAS_API/
COPY nas_mcp/ ./nas_mcp/

# 默认只绑回环：由宿主 nginx 反代进来（与 sellfox-api-proxy 同一模式）
ENV NAS_MCP_BIND=127.0.0.1 \
    NAS_MCP_PORT=8402 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1

EXPOSE 8402

# 凭证一律走运行时环境变量注入，**不写进镜像**
CMD ["python", "-m", "nas_mcp.server"]
