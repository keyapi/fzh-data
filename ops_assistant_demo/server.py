#!/usr/bin/env python3
"""网点参数台演示页：假数据 + 真模型。模型只能调用本进程里的模拟工具。"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KB = (ROOT / "kb" / "notice-policy.md").read_text(encoding="utf-8")
ENV_CANDIDATES = [
    ROOT / ".env",
    ROOT.parent / "ai_access_poc" / "open_webui" / ".env",
    ROOT.parent / ".env",
]
MODEL = os.environ.get("OPENAI_MODEL", "deepseek-v4-flash")
BASE = os.environ.get("OPENAI_API_BASE_URL", "https://api.vilavi.cn/v1").rstrip("/")
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8765"))
TZ = timezone(timedelta(hours=8))

ACTOR = {"name": "林晓", "role": "网点值班员", "staffId": "E3301"}
ADMIN = {"name": "周宁", "role": "参数管理员", "staffId": "A1028"}
STATE = {
    "notices": {
        "drill": "本周演练按原计划进行，无需额外签到。",
        "prod": "生产环境对内通知由参数管理员维护，值班员不可改。",
    },
    "audit": [],
}


def now() -> str:
    return datetime.now(TZ).strftime("%H:%M:%S")


def deny_text() -> str:
    return (
        f"当前身份是{ACTOR['role']}{ACTOR['name']}（{ACTOR['staffId']}），"
        f"只能改测试环境。生产环境请联系{ADMIN['role']}{ADMIN['name']}（{ADMIN['staffId']}）。"
        "系统已拒绝，生产环境原文未改，本条已写入审计。"
    )


def audit(result: str, env: str, detail: str, via: str) -> None:
    STATE["audit"].insert(
        0,
        {
            "time": now(),
            "actor": ACTOR["name"],
            "role": ACTOR["role"],
            "env": "演练" if env == "drill" else "正式",
            "result": result,
            "detail": detail,
            "via": via,
        },
    )


def apply_change(env: str, text: str, reason: str, via: str) -> dict:
    if env != "drill":
        audit("已拒绝", "prod", reason or "试图修改生产环境", via)
        return {"ok": False, "code": "forbidden", "message": deny_text()}
    cleaned = (text or "").strip()
    if not cleaned:
        return {"ok": False, "code": "invalid", "message": "通知内容是空的，没有保存。"}
    STATE["notices"]["drill"] = cleaned
    audit("已执行", "drill", reason or cleaned, via)
    return {"ok": True, "text": cleaned}


_CN = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def cn_small(token: str) -> int | None:
    if token == "十":
        return 10
    if "十" in token:
        left, _, right = token.partition("十")
        if left and left not in _CN:
            return None
        if right and right not in _CN:
            return None
        tens = _CN[left] if left else 1
        ones = _CN[right] if right else 0
        return tens * 10 + ones
    if token in _CN:
        return _CN[token]
    return None


def explicit_amounts(text: str) -> list[int]:
    found: list[int] = []
    for match in re.finditer(r"(\d+)\s*万|([一二两三四五六七八九十]+)\s*万|(\d{5,})", text):
        if match.group(1):
            found.append(int(match.group(1)) * 10000)
        elif match.group(2):
            value = cn_small(match.group(2))
            if value:
                found.append(value * 10000)
        else:
            found.append(int(match.group(3)))
    return found


def wants_change(text: str) -> bool:
    if re.search(r"多少|是什么|当前限额|不要改|只问", text) and not re.search(r"改成|调整|调到|同步|导出|工单|提交", text):
        return False
    return bool(re.search(r"限额|调到|改成|万|工单|导出|客户清单|正式|同步", text))


def wants_export(text: str) -> bool:
    cleaned = re.sub(r"(不要|别|无需)[^，。]{0,8}导出", "", text)
    return bool(re.search(r"导出|客户清单|批量查询", cleaned))


def wants_prod_change(text: str) -> bool:
    cleaned = re.sub(r"(不要|别|无需|不用|不)[^，。]{0,12}(生产|正式)", "", text)
    return bool(re.search(r"(同步|改到|改成|调到).{0,8}(生产|正式)|(生产|正式).{0,8}(改|调|同步)", cleaned))


def policy_rails(role: str, asked: str, proposal: dict | None, noop: bool, denied_kind: str) -> list[dict]:
    touched = bool(proposal) or noop or bool(denied_kind) or wants_change(asked) or wants_export(asked) or wants_prod_change(asked)
    if not touched:
        return []
    who = "综合柜员陈默" if role == "reader" else "柜面主管林晓"
    rails = []
    if denied_kind == "reader":
        rails.append({"name": "岗位工具白名单", "result": "拦截", "detail": f"{who}不能改限额，也不能提交变更单。"})
    else:
        rails.append({"name": "岗位工具白名单", "result": "通过", "detail": f"{who}可以读取测试限额，并提案修改测试限额或变更单。"})
    if denied_kind == "prod" or wants_prod_change(asked):
        rails.append({"name": "生产写保护", "result": "拦截", "detail": "生产限额不在本岗位。需参数管理员在变更窗口双人复核。"})
    elif re.search(r"生产|正式", asked):
        rails.append({"name": "生产写保护", "result": "通过", "detail": "提到了生产，但没有申请修改生产限额。"})
    if denied_kind in ("export", "export_partial") or wants_export(asked):
        rails.append({"name": "客户信息不出域", "result": "拦截", "detail": "不导出客户清单，没有文件。"})
    if noop:
        rails.append({"name": "无差额不立项", "result": "拦截", "detail": "目标金额与当前测试限额相同，不改数，不提交变更单。"})
    elif proposal and proposal.get("kind") in ("limit", "both"):
        rails.append({"name": "无差额不立项", "result": "通过", "detail": "目标金额与当前值不同，可以立项。"})
    if proposal:
        rails.append({"name": "人工确认", "result": "等待", "detail": "写操作还没执行，等你在页面上点允许。"})
    else:
        rails.append({"name": "人工确认", "result": "通过", "detail": "没有待执行的写操作。"})
    return rails


def refuses_limit_change(text: str) -> bool:
    return bool(re.search(r"不要改限额|别改限额|不用改限额|不改限额|只(帮我)?提交|只交", text))


def vague_amount(text: str) -> bool:
    return not explicit_amounts(text) and bool(re.search(r"一点|一些|调高|调低", text))


def last_user_text(messages: list) -> str:
    for item in reversed(messages):
        if item.get("role") == "user":
            return str(item.get("content") or "")
    return ""


def public_state() -> dict:
    return {
        "actor": ACTOR,
        "admin": ADMIN,
        "notices": STATE["notices"],
        "audit": STATE["audit"][:12],
    }


def load_env_key() -> tuple[str, str]:
    base = os.environ.get("OPENAI_API_BASE_URL", BASE).rstrip("/")
    key = os.environ.get("OPENAI_API_KEY", "")
    if key and "replace" not in key:
        return base, key
    key = ""
    for path in ENV_CANDIDATES:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            name, value = name.strip(), value.strip()
            if name == "OPENAI_API_KEY" and value and "replace" not in value:
                key = value
            elif name == "OPENAI_API_BASE_URL" and value:
                base = value.rstrip("/")
        if key:
            break
    return base, key


def chat(base: str, key: str, messages: list, tools: list) -> dict:
    body = json.dumps(
        {
            "model": MODEL,
            "messages": messages,
            "tools": tools,
            "temperature": 0.2,
            "max_tokens": 700,
            # 多轮里若开着思考模式，历史 assistant 没有 reasoning_content 会 400。
            "thinking": {"type": "disabled"},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        base + "/chat/completions",
        data=body,
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=70) as resp:
        return json.loads(resp.read().decode("utf-8"))


READ = {
    "type": "function",
    "function": {
        "name": "read_test_limit",
        "description": "读取当前测试环境单笔对公转账限额，单位元。回答限额、或决定改不改之前，先调用这个。不要凭记忆猜。",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

PROPOSE = {
    "type": "function",
    "function": {
        "name": "propose_change",
        "description": "在已经读过当前限额之后，提案让人在页面上点允许。kind=limit 只改测试限额。kind=ticket 只填工单不改数。kind=both 先改测试限额再交单。kind=prod 改生产限额。kind=export 导出客户清单。后两种会被拒绝。金额和当前值相同就不要调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["limit", "ticket", "both", "prod", "export"]},
                "summary": {"type": "string"},
                "steps": {"type": "array", "items": {"type": "string"}},
                "amount": {"type": "integer", "description": "测试环境单笔限额，单位元。一句话里有两个金额时填最后那个。"},
                "reason": {"type": "string"},
                "title": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["kind", "summary", "steps"],
        },
    },
}

SYSTEM_OPERATOR = """你是网点参数台网页里的助手，当前身份是柜面主管林晓 E3301。数据是演示用的假数据，不产生资金划转。
测试环境给柜面试参数，不接真实客户。生产环境是真实客户在用的。不要把测试环境叫成演练环境。
当前限额不在提示词里。要知道数字，必须先调用 read_test_limit，看完工具结果再决定。
人没给出具体金额（例如「调高一点」）时，直接追问，不要调用 propose_change。
一句话里先后两个金额，只提案最后那个。
用户说不要改限额、只要工单时，kind=ticket，不要改数字。
读到的金额和用户要改的金额相同：不要调用 propose_change，直接说明没有差额，不改数，也不提交变更单。
金额不同、又要改又要交单：kind=both。只改测试限额：kind=limit。只交单：kind=ticket。
「不要同步生产」是说明，不是去改生产。只有用户要求改生产限额或把限额同步到生产，才用 kind=prod。
导出客户清单用 kind=export。同一句里如果还有测试限额修改，测试限额照常提案。
金额用元，二十万写成 200000。食堂、天气等无关问题直接说明不管。"""

SYSTEM_READER = """你是网点参数台网页里的助手，当前身份是综合柜员陈默 E3302。数据是演示用的假数据。
先调用 read_test_limit。这个岗位看不到生产限额，工具结果里也不会有。不要编造生产数字。
任何改限额、提交工单、同步生产、导出客户清单，都调用 propose_change，系统会拒绝。不要说没有工具。告诉用户岗位权限不够。"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        print("%s - %s" % (self.address_string(), fmt % args))

    def _send(self, code: int, payload: dict | bytes, content_type: str) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8") if isinstance(payload, dict) else payload
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/api/state":
            self._send(200, public_state(), "application/json; charset=utf-8")
            return
        if path == "/api/kb":
            self._send(200, {"text": KB}, "application/json; charset=utf-8")
            return
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        file = (ROOT / rel).resolve()
        if not str(file).startswith(str(ROOT)) or not file.is_file():
            self._send(404, {"error": "not found"}, "application/json; charset=utf-8")
            return
        kind = "text/html; charset=utf-8" if file.suffix == ".html" else "application/json; charset=utf-8"
        self._send(200, file.read_bytes(), kind)

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        length = int(self.headers.get("Content-Length", "0"))
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._send(400, {"error": "bad json"}, "application/json; charset=utf-8")
            return
        if path == "/api/change":
            result = apply_change(
                str(body.get("env") or ""),
                str(body.get("text") or ""),
                str(body.get("reason") or ""),
                str(body.get("via") or "页面"),
            )
            self._send(200 if result.get("ok") else 403, {**result, "state": public_state()}, "application/json; charset=utf-8")
            return
        if path != "/api/chat":
            self._send(404, {"error": "not found"}, "application/json; charset=utf-8")
            return
        self._chat(body)

    def _proposal_from(self, args: dict, asked: str) -> dict | None:
        kind = str(args.get("kind") or "")
        if kind not in ("limit", "ticket", "both", "prod", "export"):
            if wants_export(asked):
                kind = "export"
            elif wants_prod_change(asked):
                kind = "prod"
            elif re.search(r"工单|变更单", asked) and re.search(r"限额|改成|调到", asked) and not refuses_limit_change(asked):
                kind = "both"
            elif re.search(r"工单|变更单", asked):
                kind = "ticket"
            else:
                kind = "limit"
        if refuses_limit_change(asked) and kind in ("limit", "both"):
            kind = "ticket"
        amounts = explicit_amounts(asked)
        raw_amount = args.get("amount")
        amount = amounts[-1] if amounts else (int(raw_amount) if raw_amount else None)
        if kind in ("limit", "both") and not amount:
            return None
        if kind in ("limit", "both") and vague_amount(asked):
            return None
        reason = str(args.get("reason") or "按柜面主管指令调整测试环境单笔限额")
        yuan = f"{amount/10000:g} 万" if amount and amount % 10000 == 0 else (str(amount) if amount else "")
        both_summary = f"先把测试环境单笔限额改为 {yuan}，再提交变更单。生产限额不动。"
        return {
            "kind": kind,
            "submit": bool(re.search(r"提交", asked)) and not bool(re.search(r"不要提交|先别提交", asked)),
            "summary": str(args.get("summary") or (both_summary if kind == "both" else (f"把测试环境单笔对公转账限额调整为 {yuan}" if kind == "limit" else "填写变更单"))),
            "steps": [str(x) for x in (args.get("steps") or (
                ["框住测试限额并改为 " + yuan, "打开变更单，填写标题和说明", "提交工单后回到限额表"]
                if kind == "both"
                else ["打开测试环境限额", "填入新限额和原因", "你点允许后才保存"]
            ))][:5],
            "limit": {"amount": amount or 0, "reason": reason},
            "ticket": {
                "title": str(args.get("title") or (f"测试环境单笔限额调整为 {yuan}" if yuan else "参数变更")),
                "body": str(args.get("body") or reason),
            },
        }

    def _run_loop(self, base: str, key: str, messages: list, role: str, limits: dict, asked: str):
        tools = [READ, PROPOSE]
        reads: list[dict] = []
        text = ""
        proposal = None
        model_name = MODEL
        seen_read = False
        for _ in range(4):
            data = chat(base, key, messages, tools)
            model_name = data.get("model") or model_name
            message = ((data.get("choices") or [{}])[0].get("message") or {})
            text = message.get("content") or ""
            calls = message.get("tool_calls") or []
            if not calls:
                break
            assistant = {"role": "assistant", "tool_calls": calls}
            if text:
                assistant["content"] = text
            messages.append(assistant)
            writes = []
            read_this_round = False
            for call in calls:
                fn = call.get("function") or {}
                name = fn.get("name")
                call_id = call.get("id") or name or "tool"
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                if name == "read_test_limit":
                    read_this_round = True
                    seen_read = True
                    visible = {"drill": limits.get("drill")}
                    if role == "operator":
                        visible["prod"] = limits.get("prod")
                    reads.append(visible)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": json.dumps({"ok": True, "unit": "元", **visible}, ensure_ascii=False),
                    })
                elif name == "propose_change":
                    writes.append(args)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": json.dumps({"ok": False, "wait": "先看 read_test_limit 的结果，下一轮再提案。"}, ensure_ascii=False),
                    })
                else:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": json.dumps({"ok": False, "error": "未知工具"}, ensure_ascii=False),
                    })
            if writes and seen_read and not read_this_round:
                proposal = self._proposal_from(writes[-1], asked)
                break
            if writes and not seen_read:
                continue
        return text, proposal, reads, model_name

    def _chat(self, body: dict) -> None:
        base, key = load_env_key()
        if not key:
            self._send(503, {"error": "本机没有可用的模型 Token"}, "application/json; charset=utf-8")
            return
        role = body.get("role") if body.get("role") in ("operator", "reader") else "operator"
        limits = dict((body.get("state") or {}).get("limits") or {})
        if role == "reader":
            limits.pop("prod", None)
        system = SYSTEM_READER if role == "reader" else SYSTEM_OPERATOR
        messages: list = [{"role": "system", "content": system}]
        for item in (body.get("messages") or [])[-8:]:
            if item.get("role") in ("user", "assistant") and isinstance(item.get("content"), str):
                messages.append({"role": item["role"], "content": item["content"]})
        asked = last_user_text(messages)
        try:
            text, proposal, reads, model_name = self._run_loop(base, key, messages, role, limits, asked)
            current = limits.get("drill")
            export_hit = wants_export(asked) or (proposal or {}).get("kind") == "export"
            prod_hit = wants_prod_change(asked) or (proposal or {}).get("kind") == "prod"
            if proposal and proposal["kind"] in ("export", "prod"):
                proposal = None
            if proposal and proposal["kind"] in ("limit", "both") and vague_amount(asked):
                proposal = None
                text = "请说明要调到多少。当前测试限额没有改。"
            asked_amounts = explicit_amounts(asked)
            if (
                proposal is None
                and role != "reader"
                and not wants_export(asked)
                and not wants_prod_change(asked)
                and asked_amounts
                and current is not None
                and asked_amounts[-1] == int(current)
                and re.search(r"改成|调到|改为", asked)
            ):
                same = f"{int(current)/10000:g} 万" if int(current) % 10000 == 0 else str(current)
                self._send(200, {
                    "text": text or f"测试限额已经是 {same}，没有差额。不修改，也不提交变更单。已记入审计。",
                    "proposal": None,
                    "noop": True,
                    "reads": reads,
                    "rails": policy_rails(role, asked, None, True, ""),
                    "denied": None,
                    "model": model_name,
                    "state": public_state(),
                }, "application/json; charset=utf-8")
                return
            if (
                proposal
                and proposal["kind"] in ("limit", "both")
                and current is not None
                and int(current) == int(proposal["limit"]["amount"])
            ):
                same = f"{int(current)/10000:g} 万" if int(current) % 10000 == 0 else str(current)
                self._send(200, {
                    "text": f"测试限额已经是 {same}，没有差额。不修改，也不提交变更单。已记入审计。",
                    "proposal": None,
                    "noop": True,
                    "reads": reads,
                    "rails": policy_rails(role, asked, None, True, ""),
                    "denied": None,
                    "model": model_name,
                    "state": public_state(),
                }, "application/json; charset=utf-8")
                return
            denied = None
            denied_kind = ""
            if role == "reader" and (proposal or wants_change(asked)):
                audit("已拒绝", "drill", asked[:80] or "越权", "助手")
                denied = {"message": "综合柜员陈默（E3302）不能修改限额，也不能提交变更单。请联系柜面主管，或参数管理员周宁（A1028）。页面没有改动。"}
                proposal = None
                denied_kind = "reader"
            elif export_hit and proposal:
                audit("已拒绝", "export", asked[:80], "助手")
                denied = {"message": "客户清单不能导出，没有生成文件。测试限额这半句可以继续，请看下面的提案。"}
                denied_kind = "export_partial"
            elif export_hit or prod_hit:
                audit("已拒绝", "export" if export_hit else "prod", asked[:80] or "越权", "助手")
                denied = {"message": (
                    "客户清单属于客户信息，助手不能批量导出。如确需查询，请走数据管理员审批，双人复核。本次已拒绝，没有生成文件。"
                    if export_hit
                    else "生产环境单笔限额不在当前岗位权限内。请联系参数管理员周宁（A1028），在变更窗口双人复核后执行。生产限额未改，本条已写入审计。"
                )}
                proposal = None
                denied_kind = "export" if export_hit else "prod"
            self._send(200, {
                "text": text,
                "proposal": proposal,
                "noop": False,
                "reads": reads,
                "rails": policy_rails(role, asked, proposal, False, denied_kind),
                "denied": denied,
                "model": model_name,
                "state": public_state(),
            }, "application/json; charset=utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:180]
            self._send(502, {"error": "模型网关 %s" % exc.code, "detail": detail}, "application/json; charset=utf-8")
        except urllib.error.URLError as exc:
            self._send(502, {"error": "模型网关连不上", "detail": str(exc.reason)}, "application/json; charset=utf-8")
        except json.JSONDecodeError:
            self._send(502, {"error": "模型返回无法解析"}, "application/json; charset=utf-8")


def main() -> None:
    print(f"ops assistant demo http://{HOST}:{PORT}/")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
