"""Read-only account evidence audit. Private details must be written outside Git."""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

COUNTRIES = {"美国": "US", "加拿大": "CA", "墨西哥": "MX", "德国": "DE", "法国": "FR", "英国": "UK", "西班牙": "ES", "意大利": "IT", "荷兰": "NL", "比利时": "BE", "波兰": "PL", "瑞典": "SE"}
MARKETS = {"amazon.com": "US", "amazon.ca": "CA", "amazon.com.mx": "MX", "amazon.de": "DE", "amazon.fr": "FR", "amazon.co.uk": "UK", "amazon.es": "ES", "amazon.it": "IT", "amazon.nl": "NL", "amazon.com.be": "BE", "amazon.be": "BE", "amazon.pl": "PL", "amazon.se": "SE"}
FAMILIES = {"百纳": "BAINA", "佰纳": "BAINA", "方州汇绍兴": "FZHSX", "君缘": "Johna", "如森": "Rosoon", "如泱": "BJRYECLTD", "云途汇德": "YTHD", "Centrade": "CTRD", "DANEEY": "DANEEY", "FZH深圳": "Strusery", "TOODDLY": "TOODDLY", "VERCART": "Ver"}
DISPLAY_LABELS = ("Display name", "Anzeigename", "Nome visualizzato", "Nom affiché", "Nombre mostrado", "Nombre público", "Nombre para mostrar", "Weergavenaam", "Visningsnamn", "Nazwa wyświetlana", "Wywietlana nazwa", "Nom commercial tel qu’il doit app")
LEGAL_LABELS = ("Legal name", "Eingetragener Firmenname", "Nome legale", "Nom légal", "Nom juridique", "Dénomination légale", "Razón social", "Nombre legal", "Nombre de la empresa", "Wettelijke naam", "Juridiskt namn", "Nazwa prawna")
MARKET_HEADERS = {"marketplace", "marketplace-website", "marketplace website", "marché", "marktplatz", "mercado", "mercato", "marktplaats", "marknadsplats", "rynek", "site de vente", "web de amazon"}


def alias_index(rows):
    index, issues = defaultdict(list), []
    for line, row in enumerate(rows, 2):
        line = row.get("_sheet_row", line)
        canonical = row.get("渠道账号", "").strip()
        tokens = [canonical] + row.get("渠道账号别名", "").replace("，", ",").split(",")
        for token in [t.strip() for t in tokens if t.strip()]:
            if any(x["row"] == line for x in index[token]):
                issues.append({"kind": "repeated_alias", "alias": token, "row": line})
            index[token].append({"account": canonical, "row": line})
    for token, entries in index.items():
        if len({e["account"] for e in entries}) > 1:
            issues.append({"kind": "conflicting_alias", "alias": token, "entries": entries})
    return dict(index), issues


def resolve(index, token):
    entries = index.get(token)
    exact = entries is not None
    if entries is None:
        entries = [e for key, values in index.items() if key.casefold() == token.casefold() for e in values]
    accounts = sorted({e["account"] for e in entries})
    return {"status": "matched" if len(accounts) == 1 else "ambiguous" if accounts else "unmatched", "accounts": accounts, "exact": exact, "source_rows": sorted({e["row"] for e in entries})}


def infer_site(filename, marketplaces, currency=None):
    filename_sites = {site for word, site in COUNTRIES.items() if word in filename}
    match = re.search(r"202608(?:[-_ ]?)(US|CA|MX|DE|FR|UK|ES|IT|NL|BE|PL|SE)(?:\.|$)", filename, re.I)
    if match:
        filename_sites.add(match.group(1).upper())
    observed = {MARKETS[m.strip().lower()] for m in marketplaces if m.strip().lower() in MARKETS}
    candidates = filename_sites | observed
    return {"site": next(iter(candidates)) if len(candidates) == 1 else None, "status": "conflict" if len(candidates) > 1 else "identified" if candidates else "unknown", "filename_sites": sorted(filename_sites), "marketplace_sites": sorted(observed), "unknown_marketplaces": sorted(set(m for m in marketplaces if m.strip().lower() not in MARKETS)), "currency": currency}


def pdf_key(path):
    if path.name.startswith("2026AugMonthly"):
        return "2026augmonthly"
    return re.sub(r"[\s_-]|交易|汇总", "", path.stem).casefold()


def label_value(text, labels):
    for label in labels:
        match = re.search(re.escape(label) + r"[ \t]*:?[ \t]+([^\n]+)", text, re.I)
        if match:
            return match.group(1).strip()
    return None


def csv_evidence(path):
    text = path.read_text(encoding="utf-8-sig")
    rows = list(csv.reader(text.splitlines()))
    header_at = next((i for i, row in enumerate(rows) if any(c.strip().casefold() in MARKET_HEADERS for c in row)), None)
    if header_at is None:
        return {"rows": 0, "marketplaces": [], "header": [], "error": "missing_header"}
    header = rows[header_at]
    data = [r for r in rows[header_at + 1:] if len(r) == len(header)]
    market_col = next((i for i, h in enumerate(header) if h.strip().casefold() in MARKET_HEADERS), None)
    markets = sorted({r[market_col].strip() for r in data if market_col is not None and r[market_col].strip()})
    return {"rows": len(data), "marketplaces": markets, "header": header, "bad_width_rows": sum(len(r) != len(header) for r in rows[header_at+1:] if r)}


def supplemental_shop_matches(files, shops):
    """Find unique stable keys from exact PDF legal text, keeping account unresolved."""
    site_ids, legal_sellers = defaultdict(set), defaultdict(set)
    for f in files:
        if len(f["shops"]) == 1:
            shop = f["shops"][0]
            site_ids[f["site_evidence"]["site"]].add(shop["marketplaceId"])
            if f["pdf_legal_name"]:
                legal_sellers[f["pdf_legal_name"]].add(shop["sellerId"])
    result = []
    for f in files:
        if f["shops"]:
            continue
        markets = site_ids[f["site_evidence"]["site"]]
        sellers = legal_sellers[f["pdf_legal_name"]]
        if len(markets) != 1 or len(sellers) != 1:
            continue
        candidates = [s for s in shops if s["marketplaceId"] in markets and s["sellerId"] in sellers]
        if len(candidates) == 1:
            result.append({"file": f["file"], "account": f["account_candidate"], **candidates[0], "evidence": {"method": "exact_pdf_legal_text_and_unique_seller_marketplace", "pdf_legal_name": f["pdf_legal_name"], "site": f["site_evidence"]["site"]}, "legal_entity_status": "pending_finance_confirmation"})
    return result


def require_private_output(path):
    path = path.resolve()
    if any((p/".git").exists() for p in (path, *path.parents)):
        raise ValueError("Private reports must be written outside Git repositories")


def audit(raw, sheet, en, shops=None):
    import pymupdf
    required = {"渠道", "渠道账号", "渠道账号别名", "赛狐店铺"}
    missing = required - set(sheet["header"])
    repeated_headers = [name for name, count in Counter(sheet["header"]).items() if count > 1]
    if missing or repeated_headers:
        raise ValueError(f"Sheet schema error: missing={sorted(missing)}, repeated={repeated_headers}")
    rows = [{**dict(zip(sheet["header"], r)), "_sheet_row": n} for n, r in enumerate(sheet["rows"][1:], 2)]
    amazon = [r for r in rows if r.get("渠道") == "Amazon"]
    index, issues = alias_index(amazon)
    en_index = {d["name"]: d for d in en["accounts"]}
    shop_index = defaultdict(list)
    for shop in (shops or {}).get("shops", []):
        shop_index[(shop.get("name") or "").strip().casefold()].append(shop)
    sheet_index = {r["渠道账号"]: r for r in amazon}
    pdfs = defaultdict(list)
    for path in raw.rglob("*.pdf"):
        pdfs[pdf_key(path)].append(path)
    files = []
    for path in sorted(raw.rglob("*.csv")):
        evidence = csv_evidence(path)
        pair = pdfs.get(pdf_key(path), [])
        text = ""
        if len(pair) == 1:
            with pymupdf.open(pair[0]) as doc:
                text = "\n".join(p.get_text(sort=True) for p in doc)
        display, legal = label_value(text, DISPLAY_LABELS), label_value(text, LEGAL_LABELS)
        currency = next((c for c in ("USD", "CAD", "MXN", "EUR", "GBP", "SEK", "PLN") if re.search(r"\b" + c + r"\b", text)), None)
        site = infer_site(path.name, evidence["marketplaces"], currency)
        family = next((code for word, code in FAMILIES.items() if word.casefold() in path.name.casefold()), None)
        if family is None and display:
            # Only exact account-code evidence; never infer a legal entity from brand.
            families = {d.get("account_code") for d in en["accounts"] if (d.get("account_code") or "").casefold() == display.casefold()}
            if len(families) == 1:
                family = next(iter(families))
        token = "AMZ" + family + site["site"] if family and site["site"] else ""
        match = resolve(index, token)
        account = match["accounts"][0] if match["status"] == "matched" else None
        en_doc = en_index.get(account)
        shop_name = sheet_index.get(account, {}).get("赛狐店铺", "")
        candidates = shop_index.get(shop_name.casefold(), []) if shop_name else []
        files.append({"file": str(path), "pdf": [str(p) for p in pair], "csv": evidence, "pdf_display_name": display, "pdf_legal_name": legal, "site_evidence": site, "constructed_account_key": token or None, "account_candidate": account, "match": match, "en_exists": en_doc is not None, "en_site_agrees": en_doc.get("channel_region") == site["site"] if en_doc else None, "en_currency": en_doc.get("currency") if en_doc else None, "shops": candidates, "shop_match_status": "matched" if len(candidates) == 1 else "ambiguous" if candidates else "unmatched", "legal_entity_status": "pending_finance_confirmation"})
    missing_en = [r["渠道账号"] for r in amazon if r["渠道账号"] not in en_index]
    canonical_counts = Counter(r["渠道账号"] for r in amazon)
    alias_drift = []
    for row in amazon:
        doc = en_index.get(row["渠道账号"])
        if doc:
            wanted = {t.strip() for t in row.get("渠道账号别名", "").replace("，", ",").split(",") if t.strip()}
            actual = {a.get("account_alias") for a in doc.get("channel_account_alias", [])}
            if wanted - actual:
                alias_drift.append({"account": doc["name"], "missing_aliases": sorted(wanted-actual)})
    stats = {"sheet_amazon_rows": len(amazon), "en_amazon_accounts": len(en_index), "canonical_duplicates": sum(c-1 for c in canonical_counts.values() if c>1), "alias_issues": dict(Counter(i["kind"] for i in issues)), "sheet_accounts_missing_en": len(missing_en), "accounts_with_alias_drift": len(alias_drift), "files": len(files), "matched": sum(f["match"]["status"] == "matched" for f in files), "en_matched": sum(f["en_exists"] for f in files), "site_conflicts": sum(f["site_evidence"]["status"] == "conflict" for f in files), "pdf_unique_pairs": sum(len(f["pdf"]) == 1 for f in files), "pdf_display_extracted": sum(bool(f["pdf_display_name"]) for f in files), "pdf_legal_extracted": sum(bool(f["pdf_legal_name"]) for f in files), "marketplace_observed_files": sum(bool(f["csv"]["marketplaces"]) for f in files), "legal_entities_confirmed": 0}
    stats.update({"shop_matched_files": sum(f["shop_match_status"] == "matched" for f in files), "shop_ambiguous_files": sum(f["shop_match_status"] == "ambiguous" for f in files), "pdf_legal_name_strings": len({f["pdf_legal_name"] for f in files if f["pdf_legal_name"]}), "en_nonlocal_currency_accounts": sum(d.get("currency") != "CNY" for d in en["accounts"]), "en_fetch_errors": len(en.get("errors", [])), "en_site_conflicts": sum(f["en_site_agrees"] is False for f in files), "csv_header_errors": sum(bool(f["csv"].get("error")) for f in files), "csv_width_errors": sum(f["csv"].get("bad_width_rows", 0) for f in files)})
    supplemental = supplemental_shop_matches(files, (shops or {}).get("shops", []))
    represented_accounts = {f["account_candidate"] for f in files if f["account_candidate"]}
    represented_shop_ids = {f["shops"][0]["id"] for f in files if len(f["shops"]) == 1} | {s["id"] for s in supplemental}
    not_represented = [r for r in amazon if r["渠道账号"] not in represented_accounts]
    shop_not_represented = [s for s in (shops or {}).get("shops", []) if s["id"] not in represented_shop_ids]
    stats.update({"supplemental_shop_matched_files": len(supplemental), "current_sheet_accounts_without_august_file": len(not_represented), "current_shops_without_august_file": len(shop_not_represented)})
    return {"summary": stats, "files": files, "alias_issues": issues, "sheet_accounts_missing_en": missing_en, "alias_drift": alias_drift, "seller_id_available_in_sheet_or_en": False, "seller_id_available_in_shops": bool(shops), "legal_entity_master_available": False, "supplemental_shop_matches": supplemental, "coverage_comparison": {"status": "current_inventory_only_historical_expected_scope_unconfirmed", "sheet_accounts_without_august_file": not_represented, "shops_without_august_file": shop_not_represented}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True, help="Main repository containing gitignored credentials")
    parser.add_argument("--refresh", action="store_true", help="GET only: refresh Google/EN snapshots")
    args = parser.parse_args()
    require_private_output(args.out)
    args.out.mkdir(parents=True, exist_ok=True)
    if args.refresh:
        sys.path.insert(0, str(args.data_root))
        from channel_account_sync.fetch_sources import fetch_sheet
        from channel_account_sync.rest import session, get_all, get_doc
        sheet = fetch_sheet()
        s, url = session()
        accounts, errors = [], []
        for row in get_all(s, url, "Channel Account", ["name", "channel"]):
            if row.get("channel") != "Amazon":
                continue
            response = get_doc(s, url, "Channel Account", row["name"])
            if response.status_code == 200:
                accounts.append(response.json()["data"])
            else:
                errors.append({"name": row["name"], "status": response.status_code})
        en = {"accounts": accounts, "errors": errors}
        for name, value in (("account_sheet.json", sheet), ("account_en.json", en)):
            (args.out/name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        from SELLFOX_API.client import SellfoxClient, SellfoxConfig
        client = SellfoxClient(SellfoxConfig.from_env(args.data_root/".env"))
        data = client.signed_post("/api/shop/pageList.json", {"pageSize": 200, "pageNum": 1})
        shops = list(data.get("rows", []))
        total = int(data.get("totalSize", len(shops)))
        for page in range(2, (total + 199)//200 + 1):
            shops.extend(client.signed_post("/api/shop/pageList.json", {"pageSize": 200, "pageNum": page}).get("rows", []))
        if len(shops) != total:
            raise ValueError("Shop pagination count mismatch")
        (args.out/"account_shops.json").write_text(json.dumps({"total": total, "shops": shops}, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        sheet, en = [json.loads((args.out/name).read_text(encoding="utf-8")) for name in ("account_sheet.json", "account_en.json")]
    shop_path = args.out/"account_shops.json"
    shops = json.loads(shop_path.read_text(encoding="utf-8")) if shop_path.exists() else None
    report = audit(args.raw, sheet, en, shops)
    (args.out/"account_validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.out/"additional_shop_scope.json").write_text(json.dumps(report["supplemental_shop_matches"], ensure_ascii=False, indent=2), encoding="utf-8")
    exact_scope = [{"file": f["file"], "account": f["account_candidate"], **f["shops"][0]} for f in report["files"] if len(f["shops"]) == 1]
    (args.out/"account_shop_scope.json").write_text(json.dumps(exact_scope, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
