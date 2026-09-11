# -*- coding: utf-8 -*-
"""拉取销售收款确认单附件到 data/（gitignore）。按 fileId 落盘，避免重名覆盖。"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from client import (
    DEFAULT_PROCESS_CODE,
    MODULE_DIR,
    get_access_token,
    get_instance,
    grant_download,
    http_get_bytes,
    list_instance_ids,
    load_env,
)
from parse import collect_dd_attachments, instance_summary, keep_approval, keep_attachment, safe_filename
from paths import OA_DATA

DEFAULT_OUT = OA_DATA
DATA = DEFAULT_OUT
FILES = DATA / "files"
MANIFEST = DATA / "manifest.jsonl"


def set_out(path: Path) -> None:
    global DATA, FILES, MANIFEST
    DATA = path
    FILES = DATA / "files"
    MANIFEST = DATA / "manifest.jsonl"


def _ms(s: str) -> int:
    dt = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def load_done_ids() -> set[str]:
    done = set()
    if not MANIFEST.is_file():
        return done
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("processInstanceId") and rec.get("ok"):
            done.add(rec["processInstanceId"])
    return done


def append_manifest(rec: dict) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    with MANIFEST.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def dest_path(inst_id: str, att: dict) -> Path:
    folder = FILES / inst_id
    folder.mkdir(parents=True, exist_ok=True)
    orig = safe_filename(att.get("fileName") or "file")
    fid = att.get("fileId") or "nofileid"
    if att.get("kind") == "图片" and not att.get("fileId"):
        stem = Path(orig).stem
        suf = Path(orig).suffix or ".png"
        return folder / f"photo__{stem}{suf}"
    return folder / f"{fid}__{orig}"


def fetch_one(token: str, inst_id: str) -> dict:
    inst = get_instance(token, inst_id)
    summary = instance_summary(inst)
    summary["processInstanceId"] = inst_id
    form = inst.get("formComponentValues") or []
    atts = collect_dd_attachments(form)
    if not keep_approval(summary.get("status") or "", summary.get("result") or ""):
        rec = {
            **summary,
            "attachments": [],
            "errors": [],
            "ok": True,
            "skipped_reason": "not_keep_approval",
        }
        return rec
    saved = []
    errors = []
    for att in atts:
        if not keep_attachment(att):
            continue
        dest = dest_path(inst_id, att)
        try:
            if dest.exists() and dest.stat().st_size > 0:
                saved.append({"path": str(dest.relative_to(DATA)), "skipped": True, **att})
                continue
            if att.get("url"):
                blob = http_get_bytes(att["url"])
            elif att.get("fileId"):
                granted = grant_download(token, inst_id, att["fileId"])
                uri = ((granted.get("result") or {}) if isinstance(granted.get("result"), dict) else {}).get("downloadUri") or ""
                if not uri.startswith("http"):
                    errors.append({"fileId": att.get("fileId"), "reason": f"uri={uri[:80]}"})
                    continue
                blob = http_get_bytes(uri)
            else:
                errors.append({"fileName": att.get("fileName"), "reason": "no fileId/url"})
                continue
            dest.write_bytes(blob)
            saved.append({"path": str(dest.relative_to(DATA)), "bytes": len(blob), **att})
        except Exception as e:
            errors.append({"fileId": att.get("fileId"), "fileName": att.get("fileName"), "reason": str(e)[:300]})
        time.sleep(0.05)
    rec = {**summary, "attachments": saved, "errors": errors, "ok": not errors}
    return rec


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2026-06-01")
    p.add_argument("--end", default="", help="YYYY-MM-DD（含当天）；默认今天，以免漏掉截止日后补交")
    p.add_argument("--process-code", default="")
    p.add_argument("--out", default=str(DEFAULT_OUT), help="附件缓存目录（DINGTALK_OA_DATA，默认模块 data/）")
    p.add_argument("--limit", type=int, default=0, help="调试：最多拉 N 个实例")
    p.add_argument("--env", default="", help="dingtalk_oa.env 路径")
    p.add_argument("--sleep", type=float, default=0.12, help="实例之间间隔秒；钉钉应用维度约 20 QPS")
    p.add_argument("--workers", type=int, default=1, help="保留：>1 需共享限速，默认串行以免打到 QPS")
    args = p.parse_args()
    if not args.end:
        args.end = datetime.now().strftime("%Y-%m-%d")
    if args.workers > 1:
        print("workers>1 暂未启用：同一 appKey 共享约 20 QPS，串行已接近安全上限", file=sys.stderr)
    set_out(Path(args.out))
    env = load_env(Path(args.env) if args.env else None)
    code = args.process_code or env.get("DINGTALK_OA_PROCESS_CODE") or DEFAULT_PROCESS_CODE
    token = get_access_token(env)
    ids = list_instance_ids(token, code, _ms(args.start), _ms(args.end) + 86400000 - 1)
    if args.limit:
        ids = ids[: args.limit]
    print(f"instances={len(ids)} {args.start}..{args.end}")
    done = load_done_ids()
    (DATA / "instance_ids.json").write_text(json.dumps(ids, ensure_ascii=False, indent=2), encoding="utf-8")
    n_ok = n_err = n_skip = 0
    for i, inst_id in enumerate(ids, 1):
        if inst_id in done:
            n_skip += 1
            continue
        try:
            rec = fetch_one(token, inst_id)
            append_manifest(rec)
            if rec.get("ok"):
                n_ok += 1
            else:
                n_err += 1
            print(f"[{i}/{len(ids)}] {rec.get('businessId')} {rec.get('originator')} atts={len(rec.get('attachments') or [])} err={len(rec.get('errors') or [])}")
        except Exception as e:
            n_err += 1
            append_manifest({"processInstanceId": inst_id, "ok": False, "errors": [{"reason": str(e)[:400]}]})
            print(f"[{i}/{len(ids)}] FAIL {inst_id} {e}")
        time.sleep(args.sleep)
    print(f"done ok={n_ok} err={n_err} skip={n_skip} manifest={MANIFEST}")


if __name__ == "__main__":
    main()
