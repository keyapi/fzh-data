"""CLI：中文请求 → 本仓库模块路由。

退出码（沿用 dispatch.py 的通用约定，便于调用方对两个工具用同一套分支）：
  0  命中了模块
  1  用法错误或缺凭证
  2  API / 传输错误
  3  需人工介入（低置信度或 none）

注意：本工具**不**复用 dispatch.py 的状态词表（READY/NEED_LOGIN/...）。那是「执行环境
状态」，本工具的「低置信度」是「认知不确定」，混用会让两个词都失准；且 AGENTS.md 规定
通途/赛狐/浏览器任务的唯一权威是 dispatch.py，本工具只给模块名、不替它派发状态。
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path

from . import env as env_mod
from .catalog import load_catalog
from .router import GATE_OK, API_KEY_NAME, RouteResult, resolve_api_key, route
from .typesafe import DEFAULT_TIMEOUT, HttpError

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_API_ERROR = 2
EXIT_NEED_ACTION = 3

_LABEL_WIDTH = 10

_MISSING_INPUT_HINT = "请补充：平台(赛狐/EN/通途)？数据源文件？动作(生成导入文件 / 写回)？"


def _reconfigure_streams() -> None:
    """中文输出在 Windows cp936 下会被静默搞坏，显式切 UTF-8。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def _display_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(char) in "WF" else 1 for char in text)


def _line(label: str, value: str) -> str:
    padding = " " * max(1, _LABEL_WIDTH - _display_width(label))
    return f"{label}{padding}{value}"


def _candidates_text(result: RouteResult, top: int | None) -> str:
    ordered = sorted(result.probabilities.items(), key=lambda item: (-item[1], item[0]))
    # 概率挤在某个选项上时，剩下的都是 0.00，列出来只是噪音
    informative = [(name, value) for name, value in ordered if value >= 0.005] or ordered[:1]
    if top is not None:
        informative = informative[:top]
    return " | ".join(f"{name} {value:.2f}" for name, value in informative)


def _next_step(result: RouteResult) -> str:
    if result.run:
        return result.run
    if result.web_task:
        return f"uv run python web_automation/scripts/dispatch.py {result.web_task} --check"
    if result.directory:
        # .agents/skills/ 下的条目只有 SKILL.md，没有 AGENT_HANDOFF.md
        if result.directory.startswith(".agents/skills/"):
            return f"读 {result.directory}SKILL.md"
        return f"cd {result.directory}（详见 {result.directory}AGENT_HANDOFF.md）"
    return f"外部 skill：{result.skill}"


def _render_hit(result: RouteResult) -> None:
    print(_line("模块", str(result.skill)))
    print(_line("目录", str(result.directory) if result.directory else "（外部 skill，无仓库目录）"))
    print(_line("置信度", f"{result.confidence:.2f}  (阈值 {result.min_confidence:.2f})"))
    if result.verb:
        print(_line("动作", result.verb))
    if result.model:
        print(_line("模型", result.model))
    print(_line("候选", _candidates_text(result, 3)))
    print(_line("下一步", _next_step(result)))


def _render_unresolved(result: RouteResult, *, show_all: bool) -> None:
    print(_line("结果", "无法判定，需人工/澄清"))
    if result.reason:
        print(_line("原因", result.reason))
    if result.skill and result.skill != "none":
        print(_line("最佳猜测", f"{result.skill} ({result.confidence:.2f})"))
        if result.directory:
            print(_line("目录", result.directory))
    if result.ambiguity is not None:
        print(_line("歧义度", f"{result.ambiguity:.2f}"))
    if result.model:
        print(_line("模型", result.model))
    print(_line("候选", _candidates_text(result, None if show_all else 3)))
    print(_line("建议", _MISSING_INPUT_HINT))


def _env_hint(env_file: Path | None) -> str:
    if env_file is not None:
        looked = str(env_file)
    else:
        found = env_mod.candidates()
        looked = "、".join(str(path) for path in found) if found else "（未找到任何 .env）"
    return f"检查 {API_KEY_NAME}；已查找的 .env：{looked}；可用 --env-file 指定"


def _render_missing_key(env_file: Path | None) -> None:
    print(_line("结果", "缺少凭证"))
    print(_line("原因", f"未找到 {API_KEY_NAME}"))
    print(_line("提示", _env_hint(env_file)))


def _render_error(exc: HttpError, env_file: Path | None) -> None:
    print(_line("结果", "调用失败"))
    print(_line("原因", f"HTTP {exc.status}：{exc.body.strip()[:300]}"))
    print(_line("提示", _env_hint(env_file)))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m intent_router.cli",
        description="中文意图 → 本仓库模块路由（TypeSafe Jev / System One）",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_route = subparsers.add_parser("route", help="把一句中文请求路由到某个模块")
    p_route.add_argument("request", help="中文请求原文")
    p_route.add_argument(
        "--min-confidence", type=float, default=0.5, help="低于此置信度即判定为需人工介入（默认 0.5）"
    )
    p_route.add_argument("--model", default=None, help="覆盖 catalog 里的 model（默认 jev-latest）")
    p_route.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="单次请求超时秒数")
    p_route.add_argument("--json", action="store_true", help="输出完整结果的 JSON")
    p_route.add_argument("--show-candidates", action="store_true", help="打印完整候选概率分布")
    p_route.add_argument("--env-file", type=Path, default=None, help="显式指定 .env，替代上溯查找")
    p_route.add_argument("--verbose", action="store_true", help="把已加载的 .env 打到 stderr")

    p_catalog = subparsers.add_parser("catalog", help="列出 catalog 里的模块选项，供人工核对")
    p_catalog.add_argument("--json", action="store_true", help="输出 JSON")
    return parser


def _cmd_catalog(args: argparse.Namespace) -> int:
    catalog = load_catalog()
    if args.json:
        print(json.dumps([option["skill"] for option in catalog.options], ensure_ascii=False, indent=2))
        return EXIT_OK
    print(f"catalog v{catalog.version} · model {catalog.model} · {len(catalog.options)} 个模块")
    for option in catalog.options:
        directory = option.get("dir") or "（外部 skill）"
        print(f"  {option['skill']:<34} {directory:<28} {option.get('summary', '')}")
    print("  none                                （由 build_payload 追加，不在 catalog 里）")
    return EXIT_OK


def _cmd_route(args: argparse.Namespace) -> int:
    if args.verbose:
        loaded = env_mod.load_env()
        shown = "、".join(str(path) for path in loaded) if loaded else "（无）"
        print(f"已加载的 .env：{shown}", file=sys.stderr)

    catalog = load_catalog()
    # 局部变量不叫 api_key：AGENTS.md 第 9 条那套凭证 grep 会把「api_key 后接等号再接长
    # 标识符」的赋值误报成明文凭证（本文件实测过一次），而该扫描要求零输出
    key = resolve_api_key(args.env_file)
    if not key:
        _render_missing_key(args.env_file)
        return EXIT_USAGE

    try:
        result = route(
            args.request,
            catalog=catalog,
            api_key=key,
            min_confidence=args.min_confidence,
            model=args.model,
            timeout=args.timeout,
        )
    except HttpError as exc:
        if args.json:
            print(json.dumps({"gate": "api_error", "status": exc.status, "body": exc.body}, ensure_ascii=False, indent=2))
        else:
            _render_error(exc, args.env_file)
        return EXIT_API_ERROR

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    elif result.gate == GATE_OK:
        _render_hit(result)
    else:
        _render_unresolved(result, show_all=args.show_candidates)

    return EXIT_OK if result.gate == GATE_OK else EXIT_NEED_ACTION


def main(argv: list[str] | None = None) -> int:
    _reconfigure_streams()
    args = _build_parser().parse_args(argv)
    if args.command == "catalog":
        return _cmd_catalog(args)
    return _cmd_route(args)


if __name__ == "__main__":
    raise SystemExit(main())
