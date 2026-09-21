"""Playwright 浏览器启动的统一出口。

为什么有这层：本机 bundled chromium 的**有头**模式起不来
（`spawn UNKNOWN`；chromium-1228 另报沙箱 `拒绝访问 0x5`），而系统已装的 Chrome/Edge
有头模式正常。各脚本内联 `launch_persistent_context(headless=False)` 时，既没地方统一改，
也留不下开关。于是把「用哪个浏览器 / 有头无头」提到环境变量：

    WEB_AUTOMATION_BROWSER_CHANNEL   如 chrome / msedge / chromium
                                     → 走 playwright 的 channel（本机已装的浏览器）
    WEB_AUTOMATION_HEADLESS          1/true/yes → 强制无头；0/false/no → 强制有头

**两个变量都不设时，行为与不经过本模块完全一致**（bundled chromium + 脚本自己传的 headless），
所以未迁移的脚本与已迁移的脚本可以共存。

用法：

    from browser_launch import launch_persistent

    with sync_playwright() as p:
        context = launch_persistent(
            p, PROFILE_DIR, headless=False,
            accept_downloads=True,
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled"],
        )
"""

from __future__ import annotations

import os

ENV_CHANNEL = "WEB_AUTOMATION_BROWSER_CHANNEL"
ENV_HEADLESS = "WEB_AUTOMATION_HEADLESS"

_TRUTHY = {"1", "true", "yes", "y", "on"}
_FALSY = {"0", "false", "no", "n", "off"}


def browser_channel() -> str | None:
    """环境变量指定的浏览器 channel；未设返回 None（= 用 playwright 自带的 chromium）。"""
    value = (os.getenv(ENV_CHANNEL) or "").strip()
    return value or None


def headless_override() -> bool | None:
    """环境变量指定的 headless 覆盖值；未设或值不认识返回 None（= 用脚本自己传的值）。"""
    value = (os.getenv(ENV_HEADLESS) or "").strip().lower()
    if value in _TRUTHY:
        return True
    if value in _FALSY:
        return False
    return None


def resolve_kwargs(*, headless: bool, **kwargs) -> dict:
    """把环境变量覆盖套到 launch 参数上。纯函数，便于单测。"""
    override = headless_override()
    resolved = dict(kwargs)
    resolved["headless"] = headless if override is None else override
    channel = browser_channel()
    if channel:
        resolved["channel"] = channel
    return resolved


def launch_persistent(p, user_data_dir, *, headless: bool = False, **kwargs):
    """`p.chromium.launch_persistent_context` 的统一入口（套用环境变量覆盖）。

    参数与 playwright 原方法一致；这里只多了环境变量覆盖与一行启动日志，
    方便排障时确认「这次到底用了哪个浏览器、有头还是无头」。
    """
    resolved = resolve_kwargs(headless=headless, **kwargs)
    print(
        f"[browser] channel={resolved.get('channel') or 'bundled'} "
        f"headless={resolved['headless']} profile={user_data_dir}"
    )
    return p.chromium.launch_persistent_context(user_data_dir=str(user_data_dir), **resolved)


def launch(p, *, headless: bool = False, **kwargs):
    """`p.chromium.launch` 的统一入口（非 persistent 场景）。"""
    resolved = resolve_kwargs(headless=headless, **kwargs)
    print(f"[browser] channel={resolved.get('channel') or 'bundled'} headless={resolved['headless']}")
    return p.chromium.launch(**resolved)
