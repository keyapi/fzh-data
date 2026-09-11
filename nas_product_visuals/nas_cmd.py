# -*- coding: utf-8 -*-
"""NAS 单条命令执行工具。

用法: uv run python nas_product_visuals/nas_cmd.py "<命令>"

主机/端口/账号/密码一律从 .env 读（见 `nas_env.py`），本文件不留任何明文凭据。
"""
from __future__ import annotations

import sys

import paramiko

from nas_env import nas_ssh


def main() -> None:
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        raise SystemExit('用法: uv run python nas_product_visuals/nas_cmd.py "<命令>"')

    cfg = nas_ssh()
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(
        cfg.host,
        port=cfg.port,
        username=cfg.user,
        password=cfg.password,
        timeout=15,
        allow_agent=False,
        look_for_keys=False,
    )
    try:
        _, stdout, stderr = ssh.exec_command(sys.argv[1], get_pty=True)
        sys.stdout.write(stdout.read().decode("utf-8", errors="replace"))
        sys.stderr.write(stderr.read().decode("utf-8", errors="replace"))
    finally:
        ssh.close()


if __name__ == "__main__":
    main()
