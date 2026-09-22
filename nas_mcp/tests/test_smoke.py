#!/usr/bin/env python3
"""nas_mcp 只读冒烟测试（会真的连 NAS，但只读）。

用法（在仓库根执行）：
    uv run python nas_mcp/tests/test_smoke.py

需要 NAS_API/.env 里的 NAS_URL / NAS_USERNAME / NAS_PASSWORD（脚本会加载它）。
不会写入 NAS 任何内容。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

# 加载 NAS 凭证（与 NAS_API 同一份 .env）。
# 注意：凭证在**父仓库**里，worktree 内通常没有 —— 两处都找。
candidates = [REPO / "NAS_API" / ".env"]
try:
    parent_repo = Path(__file__).resolve().parents[5]   # <repo>/.claude/worktrees/<wt>/nas_mcp/tests/x.py
    if (parent_repo / "NAS_API" / ".env").is_file():
        candidates.append(parent_repo / "NAS_API" / ".env")
except IndexError:
    pass
env_file = next((p for p in candidates if p.is_file()), None)
if env_file:
    print(f"[env] 使用 {env_file}")
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
else:
    print("[env] 未找到 NAS_API/.env —— 只跑离线护栏检查")

os.environ.setdefault("NAS_MCP_TOKEN", "test-token")
# 多根目录场景（DSM 上各共享文件夹是彼此独立的顶层目录）
os.environ["NAS_ALLOWED_ROOTS"] = "/FZH共享文件夹,/产品信息"

sys.path.insert(0, str(REPO / "nas_mcp"))
import server as S  # noqa: E402

ok = fail = 0


def check(label: str, cond: bool, extra: str = "") -> None:
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {label} {extra}")
    else:
        fail += 1
        print(f"  FAIL  {label} {extra}")


print(f"ROOTS = {S.ROOTS}\n")

print("── 1) 路径护栏（越界必须被拒；多根必须都放行）")
for bad in ["/etc/passwd", "/FZH共享文件夹/../../etc", "/其他共享文件夹", "/FZH共享文件夹X/x",
            "/产品信息X/x"]:
    try:
        S.safe_path(bad)
        check(f"拒绝 {bad}", False, "← 竟然放行了！")
    except S.PathDenied:
        check(f"拒绝 {bad}", True)
check("放行根1", S.safe_path("") == S.ROOTS[0], f"-> {S.safe_path('')}")
check("放行根1子目录", S.safe_path("B-部门负责人共享").startswith(S.ROOTS[0]))
check("放行根2（本次新增能力）",
      S.safe_path("/产品信息") == "/产品信息" and S.safe_path("/产品信息/x") == "/产品信息/x")
try:
    S.safe_path("/FZH共享文件夹X")
    check("前缀混淆被拒", False, "← /FZH共享文件夹X 竟然放行")
except S.PathDenied:
    check("前缀混淆被拒", True)

print("\n── 2) nas_health")
h = S.tool_health({})
check("available=True", h.get("available") is True, str(h))

print("\n── 3) nas_list_folder")
r = S.tool_list({"limit": 5})
check("返回条目", r.get("count", 0) > 0, f"count={r.get('count')}")
names = [i["name"] for i in r.get("items", [])]
check("拿到名字", len(names) > 0, str(names[:4]))

print("\n── 4) nas_file_info")
if names:
    info = S.tool_info({"path": f"{S.ROOT}/{names[0]}"})
    check("查到条目", not info.get("not_found"), str(info)[:120])

print("\n── 5) nas_read_text 的护栏（不该读的不读）")
# 找一个目录：读它必须被拒
dirs = [i for i in r.get("items", []) if i.get("is_dir")]
if dirs:
    try:
        S.tool_read_text({"path": dirs[0]["path"]})
        check("目录不可被 read_text", False, "← 竟然读了目录")
    except ValueError as e:
        check("目录不可被 read_text", "文件夹" in str(e), f"({e})")
# 非白名单扩展名必须被拒
try:
    S.tool_read_text({"path": f"{S.ROOT}/x.exe"})
    check("非文本扩展名被拒", False, "← 竟然放行")
except ValueError as e:
    check("非文本扩展名被拒", "白名单" in str(e) or "不存在" in str(e), f"({e})")

print("\n── 6) tools/list 只含只读工具")
tool_names = [t["name"] for t in S.TOOLS]
check("无写/删工具",
      not any(w in n for n in tool_names for w in ("delete", "create", "move", "upload", "write")),
      str(tool_names))

print("\n── 7) 回归护栏：**出错必须报错，不能伪装成「空」**")
# 这正是实测踩到的 bug：会话过期被 NAS_API 吞成 []，前端看到「文件夹是空的」
try:
    res = S.tool_list({"path": f"{S.ROOTS[0]}/这个目录不存在_zzz", "limit": 5})
    check("不存在的目录不返回「空」", False, f"← 竟然返回了 {res}")
except S.NasError as e:
    check("不存在的目录抛 NasError", True, f"({str(e)[:60]})")
except Exception as e:                              # noqa: BLE001
    check("不存在的目录抛错（类型非 NasError）", False, f"{type(e).__name__}: {e}")

# 正常目录必须返回 total，供模型判断「还有下一页」
r2 = S.tool_list({"path": S.ROOTS[0], "limit": 3})
check("返回 total 供翻页", r2.get("total") is not None, f"total={r2.get('total')} count={r2.get('count')}")
check("超出一页时给出 note", ("note" in r2) == (r2.get("total", 0) > 3), str(r2.get("note"))[:70])

print("\n── 8) 图片工具：返回 MCP 原生 image 内容")
IMG = "/产品信息/KS0001_三角靠枕/图片/2026新图/宽条绒/土黄色/100/3.jpg"
try:
    out = S.tool_read_image({"path": IMG})
    blocks = out.get("_content") or []
    check("返回两个内容块（文本+图片）", len(blocks) == 2, f"实际 {len(blocks)}")
    img = next((b for b in blocks if b.get("type") == "image"), None)
    check("含 image 块", img is not None)
    if img:
        check("mimeType 是图片", str(img.get("mimeType", "")).startswith("image/"), str(img.get("mimeType")))
        import base64 as _b64
        raw = _b64.b64decode(img["data"])
        check("base64 可解码且是图片魔数",
              raw[:2] == b"\xff\xd8" or raw[:8] == b"\x89PNG\r\n\x1a\n", f"{len(raw)} bytes")
        from PIL import Image as _I
        import io as _io
        im = _I.open(_io.BytesIO(raw))
        check("长边不超上限", max(im.size) <= S.IMAGE_MAX_EDGE,
              f"{im.size} (上限 {S.IMAGE_MAX_EDGE}) 返回 {len(raw)/1024:.0f} KiB")
except S.NasError as e:
    print(f"  SKIP  图片用例（该路径在当前账号下不可读）：{str(e)[:70]}")
except ValueError as e:
    print(f"  SKIP  图片用例：{e}")

try:
    S.tool_read_image({"path": f"{S.ROOTS[0]}/x.txt"})
    check("非图片扩展名被拒", False, "← 竟然放行")
except ValueError as e:
    check("非图片扩展名被拒", "只允许图片类型" in str(e), f"({str(e)[:40]})")

print("\n── 9) 放开模式：NAS_ALLOWED_ROOTS=* 时信任 DSM 账号权限")
import importlib, os as _os
_os.environ["NAS_ALLOWED_ROOTS"] = "*"
_os.environ["NAS_ROOT_FOLDER"] = "/FZH共享文件夹"
S2 = importlib.reload(S)
check("ALLOW_ANY=True", S2.ALLOW_ANY is True)
check("任意共享文件夹都放行", S2.safe_path("/产品信息/x") == "/产品信息/x"
      and S2.safe_path("/任何共享/a") == "/任何共享/a")
check(".. 逃逸仍被 normpath 吃掉", S2.safe_path("/a/../../etc") == "/etc",
      f"-> {S2.safe_path('/a/../../etc')}（路径已规范化，真正的边界交给 DSM 账号）")

print("\n── 10) 新增三工具（真连 NAS，只读）")
try:
    r = S.tool_search({"path": "/产品信息", "extension": "pdf", "limit": 3})
    check("nas_search 返回结果", (r.get("total") or 0) > 0,
          f"total={r.get('total')} 例: {(r.get('items') or [{}])[0].get('name')}")
except Exception as e:                                  # noqa: BLE001
    check("nas_search", False, f"{type(e).__name__}: {str(e)[:70]}")

try:
    r = S.tool_folder_size({"path": "/产品信息/KS0001_三角靠枕/设计稿"})
    check("nas_folder_size 返回大小", r.get("total_size") is not None,
          f"{r.get('human')} (finished={r.get('finished')})")
except Exception as e:                                  # noqa: BLE001
    check("nas_folder_size", False, f"{type(e).__name__}: {str(e)[:70]}")

PDF = "/产品信息/KS0001_三角靠枕/设计稿/24.11.21三角靠枕有扣无扣终版.pdf"
try:
    out = S.tool_read_pdf({"path": PDF, "pages": "1"})
    b = out.get("_content") or []
    imgs = [x for x in b if x.get("type") == "image"]
    txts = [x for x in b if x.get("type") == "text"]
    check("nas_read_pdf 渲染出图片", len(imgs) >= 1, f"{len(imgs)} 张")
    check("nas_read_pdf 抽出文字", any("产品名称" in t.get("text", "") for t in txts),
          next((t["text"][:40] for t in txts if "产品名称" in t.get("text", "")), ""))
except S.NasError as e:
    print(f"  SKIP  PDF 用例（该文件当前账号不可读）：{str(e)[:70]}")
except ValueError as e:
    print(f"  SKIP  PDF 用例：{e}")


print("\n── 11) B+C 新工具（缩略图 / MD5 / Office 文本）")
import base64 as _b64
import json as _json
import re as _re

IMG2 = "/产品信息/KS0001_三角靠枕/图片/2026新图/宽条绒/土黄色/100/3.jpg"
try:
    out = S.tool_thumbnail({"path": IMG2, "size": "small"})
    meta = _json.loads(out["_content"][0]["text"])
    raw = _b64.b64decode(out["_content"][1]["data"])
    check("nas_thumbnail 返回 JPEG", raw[:2] == b"\xff\xd8",
          "DSM %s %dKiB -> 返回 %.1f KiB" % (meta["dsm_format"], meta["dsm_bytes"] // 1024, len(raw) / 1024))
    check("nas_thumbnail 确实更小", len(raw) < meta["dsm_bytes"],
          "%d < %d" % (len(raw), meta["dsm_bytes"]))
except Exception as e:                                  # noqa: BLE001
    check("nas_thumbnail", False, "%s: %s" % (type(e).__name__, str(e)[:70]))

try:
    r = S.tool_file_md5({"path": IMG2})
    md5 = str(r.get("md5") or "")
    check("nas_file_md5 得到 32 位 md5", bool(_re.fullmatch(r"[0-9a-f]{32}", md5)), md5)
except Exception as e:                                  # noqa: BLE001
    check("nas_file_md5", False, "%s: %s" % (type(e).__name__, str(e)[:70]))

try:
    sr = S.tool_search({"path": "/产品信息", "extension": "docx", "limit": 1})
    items = sr.get("items") or []
    if items:
        r = S.tool_read_doc({"path": items[0]["path"], "max_chars": 800})
        check("nas_read_doc 抽出文字", r.get("chars", 0) > 0,
              "%s %d 字" % (r.get("ext"), r.get("chars")))
    else:
        print("  SKIP  docx 用例（搜不到 docx）")
except Exception as e:                                  # noqa: BLE001
    check("nas_read_doc", False, "%s: %s" % (type(e).__name__, str(e)[:70]))


print("\n── 12) 定向/批量工具（共享文件夹清单、批量缩略图）")
try:
    r = S.tool_list_shares({})
    names = [x["name"] for x in (r.get("shares") or [])]
    check("nas_list_shares 列出共享文件夹", len(names) > 0, str(names))
except Exception as e:                                  # noqa: BLE001
    check("nas_list_shares", False, "%s: %s" % (type(e).__name__, str(e)[:70]))

try:
    out = S.tool_folder_thumbnails({"path": "/产品信息/KS0001_三角靠枕/图片/2026新图/宽条绒/土黄色/100",
                                    "limit": 4})
    imgs = [x for x in out["_content"] if x["type"] == "image"]
    meta = _json.loads(out["_content"][0]["text"])
    check("nas_folder_thumbnails 出图", len(imgs) >= 1,
          "images=%s returned=%s" % (meta.get("images"), meta.get("returned")))
    if imgs:
        small = all(len(_b64.b64decode(x["data"])) < 60 * 1024 for x in imgs)
        check("缩略图确实小（<60KiB/张）", small,
              "平均 %.1f KiB" % (sum(len(_b64.b64decode(x["data"])) for x in imgs) / len(imgs) / 1024))
except Exception as e:                                  # noqa: BLE001
    check("nas_folder_thumbnails", False, "%s: %s" % (type(e).__name__, str(e)[:70]))


print("\n── 13) nas_list_archive（不解压看压缩包）")
try:
    sr = S.tool_search({"path": "/FZH共享文件夹", "extension": "zip", "limit": 1})
    items = sr.get("items") or []
    if items:
        out = S.tool_list_archive({"path": items[0]["path"], "limit": 5})
        check("nas_list_archive 列出包内条目", (out.get("count") or 0) > 0,
              "%s -> %s" % (items[0]["name"], [i["name"] for i in (out.get("items") or [])[:3]]))
    else:
        print("  SKIP  压缩包用例（搜不到 zip）")
except Exception as e:                                  # noqa: BLE001
    check("nas_list_archive", False, "%s: %s" % (type(e).__name__, str(e)[:70]))

try:
    S.tool_list_archive({"path": "/FZH共享文件夹/软件"})
    check("非压缩包被拒", False, "← 竟然放行")
except ValueError as e:
    check("非压缩包被拒", "只处理压缩包" in str(e), str(e)[:50])

print("\n── 14) File Station 深链（格式照抄 EN 实现，用真实样例钉住）")
EXPECT_PARAM = ("openfile%3D%252F%25E4%25BA%25A7%25E5%2593%2581%25E4%25BF%25A1%25E6%2581%25AF"
                "%252FKS0236_%25E4%25B9%2590%25E9%25AB%2598%25E6%2594%25B6%25E7%25BA%25B3%25E6%25A1%25B6"
                "%252F%25E8%25B0%2583%25E7%25A0%2594%25E6%258A%25A5%25E5%2591%258A%252F")
got = S.filestation_link("/产品信息/KS0236_乐高收纳桶/调研报告/").split("launchParam=", 1)[1]
check("深链编码与 EN 样例逐字一致", got == EXPECT_PARAM,
      "一致" if got == EXPECT_PARAM else "不一致！")

out = S.tool_link({"path": "/产品信息/KS0236_乐高收纳桶/调研报告"})
link = out.get("link") or ""
check("nas_link 返回可点链接",
      link.startswith("https://") and "launchApp=SYNO.SDS.App.FileStation3.Instance" in link,
      link[:80] + "...")
check("深链不是公开分享（无需 DSM 登录才怪）", "sharing" not in link.lower(), "")

info = S.tool_info({"path": "/FZH共享文件夹"})
check("nas_file_info 带 link 字段", bool(info.get("link")), str(info.get("link"))[:60] + "...")

lf = S.tool_list({"path": "/FZH共享文件夹", "limit": 2})
check("nas_list_folder 带自身 link", bool(lf.get("link")), "")
check("默认不给子项附 link（避免输出膨胀）",
      not any("link" in i for i in (lf.get("items") or [])), "")

print(f"\n结果：{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
