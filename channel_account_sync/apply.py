# -*- coding: utf-8 -*-
"""Apply a change-only Channel Account plan onto EN production. Default is dry-run."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from channel_account_sync.names import ILLIOS_CHANNEL, ILLIOS_CODE, parse_aliases, split_account
from channel_account_sync.rest import get_doc, post_doc, put_doc, session

OUT = Path(__file__).resolve().parent / "out"


def already_has_owner(owners: list[dict], user: str, from_date: str) -> bool:
    for o in owners or []:
        if (o.get("user") or "").strip() == user and str(o.get("from_date") or "")[:10] == from_date:
            return True
    return False


def append_owners(doc: dict, segs: list[dict]) -> tuple[list[dict], list[dict]]:
    owners = list(doc.get("owners") or [])
    added = []
    for seg in segs:
        if already_has_owner(owners, seg["owner"], seg["from_date"]):
            continue
        owners.append(
            {
                "user": seg["owner"],
                "from_date": seg["from_date"],
                "role_in_account": "Primary Owner",
                "is_active": 1,
            }
        )
        added.append(seg)
    return owners, added


def append_aliases(doc: dict, wanted: list[str]) -> tuple[list[dict], list[str]]:
    aliases = list(doc.get("channel_account_alias") or [])
    have = {(a.get("account_alias") or "").strip() for a in aliases}
    added = []
    for a in wanted:
        if not a or a in have:
            continue
        aliases.append({"account_alias": a})
        have.add(a)
        added.append(a)
    return aliases, added


def owner_payload(segs: list[dict]) -> list[dict]:
    rows = []
    for i, seg in enumerate(segs):
        rows.append(
            {
                "user": seg["owner"],
                "from_date": seg["from_date"],
                "role_in_account": "Operator" if i == 0 else "Primary Owner",
                "is_active": 1,
            }
        )
    return rows


def canary(s, url, account: str, owner: str, from_date: str) -> dict:
    r = get_doc(s, url, "Channel Account", account)
    if r.status_code != 200:
        return {"ok": False, "step": "get", "status": r.status_code, "body": r.text[:800]}
    doc = r.json()["data"]
    owners, added = append_owners(doc, [{"owner": owner, "from_date": from_date}])
    if not added:
        return {"ok": True, "step": "already", "name": account}
    put = put_doc(s, url, "Channel Account", account, {"owners": owners})
    verify = get_doc(s, url, "Channel Account", account)
    vdoc = verify.json().get("data") if verify.status_code == 200 else {}
    return {
        "ok": put.status_code == 200,
        "step": "put",
        "status": put.status_code,
        "owners_after": [(o.get("user"), o.get("from_date")) for o in (vdoc.get("owners") or [])],
    }


def ensure_kaufland(s, url, dry: bool) -> dict:
    r = get_doc(s, url, "Sales Channel", "Kaufland")
    if r.status_code != 200:
        return {"ok": False, "status": r.status_code, "body": r.text[:500]}
    doc = r.json()["data"]
    current = [x.strip() for x in (doc.get("supported_regions") or "").split(",") if x.strip()]
    missing = [x for x in ["AT", "IT", "FR"] if x not in current]
    if not missing:
        return {"ok": True, "skipped": True, "supported_regions": doc.get("supported_regions")}
    new = current + missing
    payload = {"supported_regions": ",".join(new)}
    if dry:
        return {"ok": True, "dry": True, "payload": payload}
    put = put_doc(s, url, "Sales Channel", "Kaufland", payload)
    return {"ok": put.status_code == 200, "status": put.status_code, "payload": payload}


def ensure_illios(s, url, dry: bool) -> dict:
    r = get_doc(s, url, "Sales Channel", ILLIOS_CHANNEL)
    if r.status_code == 200:
        return {"ok": True, "skipped": True, "name": r.json()["data"].get("name")}
    payload = {
        "channel_name": ILLIOS_CHANNEL,
        "channel_code": ILLIOS_CODE,
        "channel_type": "Marketplace",
        "is_active": 1,
        "region_type": "Country-based",
        "supported_regions": "PL",
    }
    if dry:
        return {"ok": True, "dry": True, "payload": payload}
    post = post_doc(s, url, "Sales Channel", payload)
    return {"ok": post.status_code in (200, 201), "status": post.status_code}


def create_accounts(s, url, en: dict, plan: dict, dry: bool) -> list[dict]:
    channels = {c["name"]: c for c in en.get("channels") or []}
    existing = {a["name"] for a in en.get("accounts") or []}
    results = []
    for item in plan.get("new_accounts") or []:
        name = item["en_name"]
        if name in existing:
            results.append({"account": name, "ok": True, "skipped": "exists_in_dump"})
            continue
        live = get_doc(s, url, "Channel Account", name)
        if live.status_code == 200:
            results.append({"account": name, "ok": True, "skipped": "exists_live"})
            continue
        channel = item["channel"]
        if channel == ILLIOS_CHANNEL and ILLIOS_CHANNEL not in channels:
            channels[ILLIOS_CHANNEL] = {"channel_code": ILLIOS_CODE}
        code = (channels[channel].get("channel_code") or "").strip()
        account_code, region, allow_empty = split_account(name, channel, code)
        aliases = parse_aliases(name, item.get("aliases") or "")
        if item["sheet"] != name and item["sheet"] not in aliases:
            aliases.append(item["sheet"])
        payload = {
            "channel": channel,
            "account_code": account_code,
            "allow_empty_account_code": allow_empty,
            "channel_region": region,
            "status": "Active",
            "default_language": "en",
            "currency": "CNY",
            "account_id": name,
            "channel_account_alias": [{"account_alias": a} for a in aliases],
            "owners": owner_payload(item["owners"]),
        }
        if dry:
            results.append({"account": name, "ok": True, "dry": True, "payload": payload})
            continue
        post = post_doc(s, url, "Channel Account", payload)
        row = {
            "account": name,
            "ok": post.status_code in (200, 201),
            "status": post.status_code,
            "body": post.text[:800],
        }
        if post.status_code in (200, 201):
            row["created_name"] = (post.json().get("data") or {}).get("name")
        results.append(row)
    return results


def patch_aliases(s, url, plan: dict, dry: bool) -> list[dict]:
    results = []
    for item in plan.get("alias_gaps") or []:
        en_name = item["account"]
        missing = item["add"]
        if dry:
            results.append({"account": en_name, "ok": True, "dry": True, "add": missing})
            continue
        r = get_doc(s, url, "Channel Account", en_name)
        if r.status_code != 200:
            results.append({"account": en_name, "ok": False, "status": r.status_code})
            continue
        aliases, added = append_aliases(r.json()["data"], missing)
        if not added:
            results.append({"account": en_name, "ok": True, "skipped": "already"})
            continue
        put = put_doc(s, url, "Channel Account", en_name, {"channel_account_alias": aliases})
        results.append(
            {"account": en_name, "ok": put.status_code == 200, "status": put.status_code, "add": added}
        )
    return results


def patch_owners(s, url, plan: dict, dry: bool) -> list[dict]:
    results = []
    for item in plan.get("insert_existing") or []:
        name = item["account"]
        if dry:
            results.append({"account": name, "ok": True, "dry": True, "needed": item["needed"]})
            continue
        r = get_doc(s, url, "Channel Account", name)
        if r.status_code != 200:
            results.append({"account": name, "ok": False, "status": r.status_code})
            continue
        owners, added = append_owners(r.json()["data"], item["needed"])
        if not added:
            results.append({"account": name, "ok": True, "skipped": "already"})
            continue
        put = put_doc(s, url, "Channel Account", name, {"owners": owners})
        results.append(
            {"account": name, "ok": put.status_code == 200, "status": put.status_code, "added": added}
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write production. Default is dry-run.")
    parser.add_argument("--canary", action="store_true")
    parser.add_argument("--plan", type=Path, default=OUT / "channel_account_plan.json")
    parser.add_argument("--en", type=Path, default=OUT / "channel_account_en.json")
    parser.add_argument("--canary-account", default="AMZFZHSXUS")
    parser.add_argument("--canary-owner", default="林俊彪")
    parser.add_argument("--canary-from", default="2026-07-01")
    args = parser.parse_args()
    s, url = session()
    report = {"url": url, "dry": not args.apply}
    OUT.mkdir(parents=True, exist_ok=True)

    if args.canary or args.apply:
        report["canary"] = canary(s, url, args.canary_account, args.canary_owner, args.canary_from)
        print("CANARY", json.dumps(report["canary"], ensure_ascii=False)[:1200])
        if not report["canary"].get("ok"):
            (OUT / "channel_account_apply.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            raise SystemExit("CANARY_FAILED")
        if args.canary and not args.apply:
            (OUT / "channel_account_apply.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return

    en = json.loads(args.en.read_text(encoding="utf-8"))
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    dry = not args.apply
    report["kaufland"] = ensure_kaufland(s, url, dry)
    print("KAUFLAND", report["kaufland"])
    report["illios"] = ensure_illios(s, url, dry)
    print("ILLIOS", report["illios"])
    report["creates"] = create_accounts(s, url, en, plan, dry)
    print("CREATES", sum(1 for x in report["creates"] if x.get("ok")), "/", len(report["creates"]))
    report["aliases"] = patch_aliases(s, url, plan, dry)
    print("ALIASES", sum(1 for x in report["aliases"] if x.get("ok")), "/", len(report["aliases"]))
    report["owners"] = patch_owners(s, url, plan, dry)
    print("OWNERS", sum(1 for x in report["owners"] if x.get("ok")), "/", len(report["owners"]))
    fails = [x for x in (report["creates"] + report["aliases"] + report["owners"]) if not x.get("ok")]
    print("fails", len(fails))
    for x in fails[:8]:
        print(" FAIL", x)
    (OUT / "channel_account_apply.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("wrote apply json dry", dry)


if __name__ == "__main__":
    main()
