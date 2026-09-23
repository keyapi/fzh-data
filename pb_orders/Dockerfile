# PB 订单处理服务镜像。
#
# 与仓库其它服务共用构建上下文（仓库根），因为 PB 只额外需要
# sellfox_shipping.sku_label 与 tongtool_order_cost.gsheets 两个共享模块。
# 构建上下文由 pb_orders/Dockerfile.dockerignore 裁剪，不影响其它服务的构建。
#
#   docker build -f pb_orders/Dockerfile -t pb-orders:local .
# 国内/受限网络可用：--build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

FROM python:3.11-slim

ARG PIP_INDEX_URL=https://pypi.org/simple

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app:/app/pb_orders \
    PB_ORDERS_RUNTIME_DIR=/runtime \
    PB_ORDERS_DATA_DIR=/data

COPY pb_orders/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" -r /tmp/requirements.txt

# 只拷运行需要的源码；data/ 与 runtime/ 由 compose 挂载，不进镜像
# sellfox_shipping 只用到 sku_label（中英混排）与 auth_oidc（会话签名，认证层复用）
COPY pb_orders/ /app/pb_orders/
COPY sellfox_shipping/ /app/sellfox_shipping/
COPY tongtool_order_cost/ /app/tongtool_order_cost/

RUN useradd --create-home --uid 10001 pb \
 && mkdir -p /runtime /data \
 && chown -R pb:pb /runtime /data /app
USER pb

WORKDIR /app/pb_orders
EXPOSE 8412

HEALTHCHECK --interval=30s --timeout=8s --start-period=25s --retries=3 \
  CMD ["python", "-m", "web.healthcheck", "web"]

CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8412", "--log-level", "info"]
