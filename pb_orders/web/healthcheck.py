#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""容器健康检查：`python -m web.healthcheck web|worker`。

区分两件事：
- web：HTTP 进程是否还在响应（503 也算活着，那只是 Redis 没连上）；
- worker：Redis 是否可达、队列能否读到，worker 才能真正干活。
"""

from __future__ import annotations

import sys
import urllib.error
import urllib.request


def check_web(url: str = "http://127.0.0.1:8412/healthz") -> int:
    try:
        urllib.request.urlopen(url, timeout=4)
        return 0
    except urllib.error.HTTPError:
        return 0  # 有 HTTP 响应就说明 Web 进程活着
    except Exception:  # noqa: BLE001
        return 1


def check_worker() -> int:
    try:
        from redis import Redis
        from rq import Queue

        from web.config import get_settings

        settings = get_settings()
        conn = Redis.from_url(settings.redis_url, socket_connect_timeout=4)
        conn.ping()
        Queue(settings.queue_name, connection=conn).count
        return 0
    except Exception:  # noqa: BLE001
        return 1


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else "web"
    return check_web() if target == "web" else check_worker()


if __name__ == "__main__":
    sys.exit(main())
