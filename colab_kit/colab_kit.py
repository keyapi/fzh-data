#!/usr/bin/env python3
"""colab_kit — 在 Google Drive 上读写改 Colab notebook（.ipynb）的工具箱。

为什么需要它
------------
业务同事的 Colab notebook 都在登录墙后面（`colab.research.google.com/drive/<id>`），
WebFetch 只能拿到 Google 登录页。要可复现地读它的代码、改一个 cell、或做
「先备份再改」，只能走 Drive API。这套动作每次现写一遍既慢又容易出错
（尤其"改完怎么证明只动了那一格"），所以固化成 CLI。

关键认知
--------
`.ipynb` 在 Drive 里**就是一个 JSON 文件**，没有专门 API（同
`google_drive_permissions/docs/lessons.md` Lesson 2）。读要 `alt=media`
（`/export?mimeType=` 对 Colab 文件 403），写要 multipart 并显式带 mimeType。

命令分两类
----------
**网络命令**（读写 Drive）::

    meta    <file-id>                       看 modifiedTime / version / capabilities
    fetch   <file-id> --out PATH            下载 .ipynb
    backup  <file-id> [--dest DIR]          下载并另存带时间戳的兜底备份
    guard   <file-id> --expect MT           并发守卫：modifiedTime 不等于期望值就退出非 0
    write   <file-id> --from PATH           整份回写（multipart，保留 Colab mimeType）
    verify  <file-id> --from PATH [--expect-changed 5,6]
                                            回读逐 cell 比对，可选断言"只有这几格变了"

**本地命令**（纯文件操作，不碰网络，可离线测试）::

    cells     PATH                          列每格序号/类型/首行
    dump      PATH --index N                打印某格全文
    find      PATH --text S                 按内容找格（定位锚点用）
    insert    PATH --after N --from FILE [--cell-type code]
                                            在第 N 格之后插入新格（备份用这个）
    sed       PATH --index N --old S --new S [--all]
                                            格内精确替换；默认要求 old 唯一命中
    syntax    PATH --index N                语法自检（魔法行中和；保留缩进）
    diff      PATH_A PATH_B                 cell 级差异（哪个下标变了）

标准流程（改一格的安全姿势）::

    uv run python colab_kit/colab_kit.py fetch  <ID> --out /tmp/nb.ipynb
    uv run python colab_kit/colab_kit.py guard  <ID> --expect <刚读到的 modifiedTime>
    uv run python colab_kit/colab_kit.py cells  /tmp/nb.ipynb
    uv run python colab_kit/colab_kit.py insert /tmp/nb.ipynb --after 7 --from old_cell5.py
    uv run python colab_kit/colab_kit.py sed    /tmp/nb.ipynb --index 5 --old 'X' --new 'Y'
    uv run python colab_kit/colab_kit.py syntax /tmp/nb.ipynb --index 5
    uv run python colab_kit/colab_kit.py write  <ID> --from /tmp/nb.ipynb
    uv run python colab_kit/colab_kit.py verify <ID> --from /tmp/nb.ipynb --expect-changed 8,9

⚠️ 私钥风险
-----------
业务 notebook 常把服务账号私钥内嵌在「安装依赖」那个 cell 里。所以:
本地兜底备份**必须放在仓库外**（默认 `~/.claude/backups/colab/`），绝不进 git。
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import pathlib
import re
import sys
import time
import uuid
from typing import Any

DRIVE = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3"
COLAB_MIME = "application/vnd.google.colaboratory"
NB_MIME = "application/json"

# 本机对 googleapis 常发 SSL: UNEXPECTED_EOF_WHILE_READING（瞬时中断），必须重试。
RETRIES = 6
RETRY_SLEEP = 2.0

DEFAULT_BACKUP_DIR = pathlib.Path.home() / ".claude" / "backups" / "colab"


# ─────────────────────────── 基础设施 ───────────────────────────


def _stdout_utf8() -> None:
    """Windows 控制台默认 GBK，中文/emoji 会炸。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:
            pass


def load_credentials(scopes: list[str] | None = None):
    """服务账号凭证。路径取 `GSPREAD_SERVICE_ACCOUNT_FILE`，默认父仓库 secrets 下的同名文件。"""
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request

    scopes = scopes or ["https://www.googleapis.com/auth/drive"]
    path = os.environ.get("GSPREAD_SERVICE_ACCOUNT_FILE")
    if not path:
        here = pathlib.Path(__file__).resolve()
        for parent in here.parents:  # 有界上溯：worktree 里凭证在父仓库
            candidate = parent / "secrets" / "gsheets-service-account.json"
            if candidate.is_file():
                path = str(candidate)
                break
    if not path or not pathlib.Path(path).is_file():
        raise SystemExit(
            "找不到服务账号私钥。设 GSPREAD_SERVICE_ACCOUNT_FILE，或放到仓库的 secrets/gsheets-service-account.json。"
        )
    creds = service_account.Credentials.from_service_account_file(path, scopes=scopes)
    creds.refresh(Request())
    return creds


def drive_service(creds):
    from googleapiclient.discovery import build

    return build("drive", "v3", credentials=creds, cache_discovery=False)


def with_retry(fn, *, what: str = "", retries: int = RETRIES):
    """googleapis 的 SSL EOF 是瞬时故障，退避重试。"""
    last: Exception | None = None
    for attempt in range(retries):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — 逐次重试，最后一次才抛
            last = exc
            if attempt < retries - 1:
                print(f"  [retry {attempt + 1}/{retries - 1}] {what or 'call'}: {type(exc).__name__}", file=sys.stderr)
                time.sleep(RETRY_SLEEP)
    raise last  # type: ignore[misc]


def get_meta(svc, file_id: str) -> dict:
    return with_retry(
        lambda: svc.files()
        .get(fileId=file_id, fields="id,name,mimeType,modifiedTime,version,capabilities", supportsAllDrives=True)
        .execute(),
        what="files.get",
    )


def download(svc, file_id: str) -> bytes:
    return with_retry(lambda: svc.files().get_media(fileId=file_id, supportsAllDrives=True).execute(), what="get_media")


def upload(svc, file_id: str, raw: bytes) -> dict:
    """整份回写。multipart + 显式 mimeType —— 别让 Drive 把 Colab 文件改成普通 JSON。"""
    import io

    from googleapiclient.http import MediaIoBaseUpload

    media = MediaIoBaseUpload(io.BytesIO(raw), mimetype=NB_MIME, resumable=False)
    return with_retry(
        lambda: svc.files()
        .update(
            fileId=file_id,
            body={"mimeType": COLAB_MIME},
            media_body=media,
            supportsAllDrives=True,
            fields="modifiedTime,version",
        )
        .execute(),
        what="files.update",
    )


# ─────────────────────────── notebook 读写（本地） ───────────────────────────


def load_notebook(path: str | pathlib.Path) -> dict:
    nb = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if "cells" not in nb:
        raise SystemExit(f"{path} 不是 notebook JSON（没有 cells）")
    return nb


def dump_notebook(nb: dict, path: str | pathlib.Path) -> None:
    # Colab 落盘习惯：indent=1；保持与在线版本一致的写法，diff 才干净。
    pathlib.Path(path).write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")


def cell_source(cell: dict) -> str:
    return "".join(cell.get("source") or [])


def split_source(text: str) -> list[str]:
    """按 Colab 的存法切成行列表（保留行尾 \\n）。"""
    if not text:
        return []
    lines = text.splitlines(keepends=True)
    if text and not text.endswith("\n") and lines:
        pass  # 最后一行没有换行符，保持原样
    return lines


def new_cell(cell_type: str, source_text: str, *, title: str = "") -> dict:
    src = f"#@title {title}\n" if (title and cell_type == "code") else ""
    return {
        "cell_type": cell_type,
        "metadata": {},
        **({"execution_count": None, "outputs": []} if cell_type == "code" else {}),
        "source": split_source(src + source_text),
        "id": uuid.uuid4().hex[:8],
    }


def find_cell_indices(nb: dict, text: str) -> list[int]:
    return [i for i, c in enumerate(nb["cells"]) if text in cell_source(c)]


def is_magic(line: str) -> bool:
    return line.lstrip().startswith("!")


def neutralize_magics(source: list[str]) -> str:
    """把 `!cmd` 魔法行换成 `pass  # !cmd`，**保留原缩进**（丢缩进会得到假 IndentationError）。"""
    out = []
    for line in source:
        if is_magic(line):
            indent = line[: len(line) - len(line.lstrip())]
            out.append(f"{indent}pass  # {line.lstrip()}")
        else:
            out.append(line)
    return "".join(out)


def compile_cell(cell: dict) -> None:
    """语法自检。cell 内嵌的 `#@title` 表单行对语法无害，无需剥离。"""
    probe = neutralize_magics(cell.get("source") or [])
    compile(probe, f"<cell {cell.get('id', '?')}>", "exec")


def compare_cells(a: dict, b: dict) -> list[int]:
    """返回 source 不同的 cell 下标（长度不同也算）。"""
    changed = [i for i in range(min(len(a["cells"]), len(b["cells"]))) if cell_source(a["cells"][i]) != cell_source(b["cells"][i])]
    if len(a["cells"]) != len(b["cells"]):
        changed.extend(range(min(len(a["cells"]), len(b["cells"])), max(len(a["cells"]), len(b["cells"]))))
    return changed


# ─────────────────────────── 命令实现 ───────────────────────────


def cmd_meta(args) -> int:
    svc = drive_service(load_credentials())
    info = get_meta(svc, args.file_id)
    caps = info.pop("capabilities", {}) or {}
    info["canEdit"] = caps.get("canEdit")
    info["canModifyContent"] = caps.get("canModifyContent")
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


def cmd_fetch(args) -> int:
    svc = drive_service(load_credentials())
    raw = download(svc, args.file_id)
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(raw)
    nb = json.loads(raw)
    print(f"✅ 已下载 {len(raw)} bytes / {len(nb['cells'])} cells → {out}")
    meta = get_meta(svc, args.file_id)
    print(f"   modifiedTime={meta['modifiedTime']}  version={meta['version']}")
    print(f"   下一步：guard --expect {meta['modifiedTime']}")
    return 0


def cmd_backup(args) -> int:
    svc = drive_service(load_credentials())
    raw = download(svc, args.file_id)
    dest = pathlib.Path(args.dest) if args.dest else DEFAULT_BACKUP_DIR
    dest.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    path = dest / f"{args.file_id}_{stamp}.ipynb"
    path.write_bytes(raw)
    print(f"✅ 兜底备份 → {path}")
    print("   ⚠️ notebook 可能内嵌服务账号私钥 —— 这个目录必须在仓库外，且永不进 git。")
    return 0


def cmd_guard(args) -> int:
    svc = drive_service(load_credentials())
    meta = get_meta(svc, args.file_id)
    if args.expect and meta["modifiedTime"] != args.expect:
        print(f"❌ 文件已被改动，中止。\n   期望 {args.expect}\n   实际 {meta['modifiedTime']}", file=sys.stderr)
        print("   （用户在 Colab 里跑一次 cell，Colab 会把执行输出存回文件 —— modifiedTime 就会变。）", file=sys.stderr)
        return 2
    print(f"✅ modifiedTime={meta['modifiedTime']} version={meta['version']}")
    return 0


def cmd_write(args) -> int:
    raw = pathlib.Path(args.file).read_bytes()
    json.loads(raw)  # 先自检是合法 JSON，别把坏文件推上去
    svc = drive_service(load_credentials())
    if args.expect:
        meta = get_meta(svc, args.file_id)
        if meta["modifiedTime"] != args.expect:
            print(f"❌ 并发守卫失败：期望 {args.expect}，实际 {meta['modifiedTime']}", file=sys.stderr)
            return 2
    res = upload(svc, args.file_id, raw)
    print(f"✅ 已写回 version={res['version']} modifiedTime={res['modifiedTime']}")
    print(f"   下一步：verify --from {args.file} --expect-changed <逗号分隔的 cell 下标>")
    return 0


def cmd_verify(args) -> int:
    svc = drive_service(load_credentials())
    remote = json.loads(download(svc, args.file_id))
    local = load_notebook(args.file)
    changed = compare_cells(remote, local)
    print(f"远端 {len(remote['cells'])} cells / 本地 {len(local['cells'])} cells")
    print(f"source 不同的下标：{changed}")
    if args.expect_changed is not None:
        expected = sorted(int(x) for x in args.expect_changed.split(",") if x.strip())
        if changed != expected:
            print(f"❌ 与预期不符：期望只有 {expected} 变了", file=sys.stderr)
            return 1
        print(f"✅ 与预期一致：只有 {expected} 变了，其余 cell 逐字未变")
    return 0


def cmd_cells(args) -> int:
    nb = load_notebook(args.path)
    for i, cell in enumerate(nb["cells"]):
        src = cell_source(cell).strip()
        first = src.splitlines()[0][:96] if src else "(空)"
        print(f"[{i:3}] {cell['cell_type']:8} {len(src):6}  {first}")
    print(f"—— 共 {len(nb['cells'])} cells")
    return 0


def cmd_dump(args) -> int:
    nb = load_notebook(args.path)
    print(cell_source(nb["cells"][args.index]), end="")
    return 0


def cmd_find(args) -> int:
    nb = load_notebook(args.path)
    hits = find_cell_indices(nb, args.text)
    for i in hits:
        src = cell_source(nb["cells"][i]).strip()
        print(f"[{i:3}] {nb['cells'][i]['cell_type']:8} {src.splitlines()[0][:80] if src else '(空)'}")
    print(f"—— 命中 {len(hits)} 格")
    return 0 if hits else 1


def cmd_insert(args) -> int:
    nb = load_notebook(args.path)
    content = pathlib.Path(args.file).read_text(encoding="utf-8")
    nb["cells"].insert(args.after + 1, new_cell(args.cell_type, content, title=args.title))
    if args.cell_type == "code":
        compile_cell(nb["cells"][args.after + 1])
    dump_notebook(nb, args.path)
    print(f"✅ 已插入 1 格到下标 {args.after + 1}（{args.cell_type}），现在 {len(nb['cells'])} cells")
    return 0


def cmd_sed(args) -> int:
    nb = load_notebook(args.path)
    cell = nb["cells"][args.index]
    text = cell_source(cell)
    n = text.count(args.old)
    if n == 0:
        print(f"❌ 在下标 {args.index} 没找到 old 串（一字未改）", file=sys.stderr)
        return 1
    if n > 1 and not args.all:
        print(f"❌ old 串命中 {n} 次，不唯一；确认无误请加 --all", file=sys.stderr)
        return 1
    nb["cells"][args.index]["source"] = split_source(text.replace(args.old, args.new, -1 if args.all else 1))
    dump_notebook(nb, args.path)
    print(f"✅ 下标 {args.index}：替换 {n if args.all else 1} 处")
    return 0


def cmd_syntax(args) -> int:
    nb = load_notebook(args.path)
    idxs = range(len(nb["cells"])) if args.index is None else [args.index]
    bad = 0
    for i in idxs:
        cell = nb["cells"][i]
        if cell["cell_type"] != "code":
            continue
        try:
            compile_cell(cell)
        except SyntaxError as exc:
            bad += 1
            print(f"❌ 下标 {i} 语法错误：{exc}", file=sys.stderr)
    if bad:
        return 1
    print(f"✅ {len(list(idxs)) if args.index is None else 1} 格语法通过（魔法行已中和；缩进保留）")
    return 0


def cmd_diff(args) -> int:
    a, b = load_notebook(args.path_a), load_notebook(args.path_b)
    changed = compare_cells(a, b)
    if not changed:
        print("✅ 两文件 cell 级完全一致")
        return 0
    print(f"变了的下标：{changed}")
    for i in changed[:20]:
        if i < len(a["cells"]) and i < len(b["cells"]):
            first_a = (cell_source(a["cells"][i]).strip().splitlines() or ["(空)"])[0][:60]
            first_b = (cell_source(b["cells"][i]).strip().splitlines() or ["(空)"])[0][:60]
            print(f"  [{i}] {first_a!r} → {first_b!r}")
    return 1


def cmd_backup_cell(args) -> int:
    """把某一格全文复制成一个新格插到别处 —— notebook 自带的「下面老代码」收纳习惯。"""
    nb = load_notebook(args.path)
    src_cell = nb["cells"][args.index]
    clone = copy.deepcopy(src_cell)
    clone["id"] = uuid.uuid4().hex[:8]
    clone["outputs"] = []
    clone["execution_count"] = None
    nb["cells"].insert(args.after + 1, clone)
    dump_notebook(nb, args.path)
    print(f"✅ 下标 {args.index} 的全文已备份为下标 {args.after + 1}，现在 {len(nb['cells'])} cells")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="colab_kit", description="在 Google Drive 上读写改 Colab notebook (.ipynb)")
    sub = p.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("meta", help="看 modifiedTime / version / capabilities")
    m.add_argument("file_id")
    m.set_defaults(func=cmd_meta)

    f = sub.add_parser("fetch", help="下载 .ipynb")
    f.add_argument("file_id")
    f.add_argument("--out", required=True)
    f.set_defaults(func=cmd_fetch)

    b = sub.add_parser("backup", help="下载并另存带时间戳的兜底备份（默认放仓库外）")
    b.add_argument("file_id")
    b.add_argument("--dest")
    b.set_defaults(func=cmd_backup)

    g = sub.add_parser("guard", help="并发守卫：modifiedTime 不等于期望值就退出非 0")
    g.add_argument("file_id")
    g.add_argument("--expect")
    g.set_defaults(func=cmd_guard)

    w = sub.add_parser("write", help="整份回写（multipart，保留 Colab mimeType）")
    w.add_argument("file_id")
    w.add_argument("--from", dest="file", required=True)
    w.add_argument("--expect", help="先比 modifiedTime，不等则中止")
    w.set_defaults(func=cmd_write)

    v = sub.add_parser("verify", help="回读逐 cell 比对，可选断言只有这几格变了")
    v.add_argument("file_id")
    v.add_argument("--from", dest="file", required=True)
    v.add_argument("--expect-changed", help="逗号分隔的 cell 下标")
    v.set_defaults(func=cmd_verify)

    c = sub.add_parser("cells", help="列每格序号/类型/首行")
    c.add_argument("path")
    c.set_defaults(func=cmd_cells)

    d = sub.add_parser("dump", help="打印某格全文")
    d.add_argument("path")
    d.add_argument("--index", type=int, required=True)
    d.set_defaults(func=cmd_dump)

    fi = sub.add_parser("find", help="按内容找格（定位锚点用）")
    fi.add_argument("path")
    fi.add_argument("--text", required=True)
    fi.set_defaults(func=cmd_find)

    ins = sub.add_parser("insert", help="在第 N 格之后插入新格")
    ins.add_argument("path")
    ins.add_argument("--after", type=int, required=True)
    ins.add_argument("--from", dest="file", required=True, help="新格内容的文件路径")
    ins.add_argument("--cell-type", choices=["code", "markdown"], default="code")
    ins.add_argument("--title", default="", help="code 格时写进首行 #@title")
    ins.set_defaults(func=cmd_insert)

    bc = sub.add_parser("backup-cell", help="把某格全文复制成新格插到别处（「先备份再改」用）")
    bc.add_argument("path")
    bc.add_argument("--index", type=int, required=True)
    bc.add_argument("--after", type=int, required=True)
    bc.set_defaults(func=cmd_backup_cell)

    s = sub.add_parser("sed", help="格内精确替换；默认要求 old 唯一命中")
    s.add_argument("path")
    s.add_argument("--index", type=int, required=True)
    s.add_argument("--old", required=True)
    s.add_argument("--new", required=True)
    s.add_argument("--all", action="store_true")
    s.set_defaults(func=cmd_sed)

    sy = sub.add_parser("syntax", help="语法自检（魔法行中和；保留缩进）")
    sy.add_argument("path")
    sy.add_argument("--index", type=int)
    sy.set_defaults(func=cmd_syntax)

    di = sub.add_parser("diff", help="两个 .ipynb 的 cell 级差异")
    di.add_argument("path_a")
    di.add_argument("path_b")
    di.set_defaults(func=cmd_diff)

    return p


def main(argv: list[str] | None = None) -> int:
    _stdout_utf8()
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
