"""Shared fixtures for new-api offboarding unit tests.

重要：sys.modules 注入必须在 conftest 导入期执行（收集 test 模块时就会 import
目标模块，早于任何 fixture）。offboarding-check.py 是连字符文件名，无法用普通
`import offboarding_check` 导入，需经 importlib 加载后注册到 sys.modules。
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# 把目标模块目录加入 sys.path
for name in (str(ROOT / "new-api-deployment"), str(ROOT / "new-api-dingtalk-oidc")):
    if name not in sys.path:
        sys.path.insert(0, name)

# stub 容器专属依赖（共享 uv 环境未安装）
if "dingtalk_stream" not in sys.modules:
    ds = types.ModuleType("dingtalk_stream")

    class AckMessage:
        STATUS_OK = "ok"
        STATUS_LATER = "later"

    class EventMessage:
        pass

    class EventHandler:
        pass

    class Credential:
        def __init__(self, *a, **k):
            pass

    class DingTalkStreamClient:
        def __init__(self, *a, **k):
            pass

        def register_all_event_handler(self, h):
            pass

        def start_forever(self):
            pass

    ds.AckMessage = AckMessage
    ds.EventMessage = EventMessage
    ds.EventHandler = EventHandler
    ds.Credential = Credential
    ds.DingTalkStreamClient = DingTalkStreamClient
    sys.modules["dingtalk_stream"] = ds

if "pymysql" not in sys.modules:
    pm = types.ModuleType("pymysql")
    pm.Connection = type("Connection", (), {})
    pm.connect = lambda *a, **k: (_ for _ in ()).throw(NotImplementedError("stub pymysql"))
    sys.modules["pymysql"] = pm

# 注册连字符文件名模块：offboarding-check.py → 模块名 offboarding_check
if "offboarding_check" not in sys.modules:
    _spec = importlib.util.spec_from_file_location(
        "offboarding_check",
        ROOT / "new-api-deployment" / "offboarding-check.py",
    )
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    sys.modules["offboarding_check"] = _mod
