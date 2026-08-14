from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from missing_products.tongtu_data import load_tongtu_aliases
from missing_products.audit_three_systems import (
    en_session,
    fetch_en_attributes,
    fetch_en_items,
    fetch_sellfox_rows,
    load_env,
)
from SELLFOX_API.client import SellfoxClient, SellfoxConfig

from .catalog import build_candidate_catalog, load_catalog, save_catalog
from .evidence import EvidenceIndex
from .v2 import decide_v2
from .fallback import build_fallback_evidence
from .v2_report import write_v2_workbook
from .ranking import PairExample, RankingModel, evaluate_rankings, grouped_split
from .routing import route_listing
from .features import build_pair_features
from .attributes import extract_attributes
from .candidates import ListingQuery
from .report import ReviewRecord, write_review_workbook
from .feedback import validate_feedback
from .training import CandidateRetriever, FamilyClassifier, TrainingListing, build_pair_examples
from .data import build_label_audit, load_amazon_cache


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MAIN = Path(r"D:\Work\赛狐\Cursor")


def _latest(directory: Path, pattern: str) -> Path:
    candidates = [path for path in directory.glob(pattern) if not path.name.startswith("~$")]
    if not candidates:
        raise FileNotFoundError(f"No {pattern} under {directory}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_labels(args: argparse.Namespace) -> int:
    main = args.main_workspace.resolve()
    cache = args.matched_cache or main / "missing_products/out/pairing_cache/amazon_matched.json"
    mapping = args.mapping or _latest(main / "missing_products/out", "通途EN赛狐映射表_*.xlsx")
    tongtu_zip = args.tongtu_zip or _latest(Path(r"D:\Work\赛狐\配对"), "通途商品导出_*.zip")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    listings = load_amazon_cache(cache)
    aliases = load_tongtu_aliases(tongtu_zip)
    mapping_frame = pd.read_excel(mapping, sheet_name="映射全量", dtype=str)
    audited = build_label_audit(listings, aliases, mapping_frame)
    frame = pd.DataFrame(audited)
    frame.to_csv(output / "historical_label_audit.csv", index=False, encoding="utf-8-sig")

    tiers = Counter(frame["tier"])
    gold = frame[frame["usable_for_training"] == True]  # noqa: E712
    families = Counter(gold["target_sku"].str.extract(r"^(KS\d+)", expand=False).dropna())
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_rows": len(frame),
        "tiers": dict(tiers),
        "training_rows": len(gold),
        "training_unique_msku_targets": int(gold[["msku", "target_sku"]].drop_duplicates().shape[0]),
        "training_unique_asins": int(gold["asin"].replace("", pd.NA).nunique()) if "asin" in gold else 0,
        "families": dict(families.most_common()),
        "sources": {
            "amazon_matched": {"path": str(cache), "sha256": _sha256(cache)},
            "mapping": {"path": str(mapping), "sha256": _sha256(mapping)},
            "tongtu_zip": {"path": str(tongtu_zip), "sha256": _sha256(tongtu_zip)},
        },
    }
    (output / "label_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def snapshot_catalog(args: argparse.Namespace) -> int:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    env = load_env()
    base, session = en_session(env)
    en_rows = fetch_en_items(base, session)
    product_codes = sorted(
        {
            str(row.get("item_code") or row.get("name") or "")
            for row in en_rows
            if str(row.get("item_code") or row.get("name") or "").startswith("KS")
            and not row.get("has_variants")
        }
    )
    en_details = fetch_en_attributes(base, session, product_codes)
    valid_en = [row for row in en_details.values() if "error" not in row]
    main = args.main_workspace.resolve()
    client = SellfoxClient(SellfoxConfig.from_env(main / ".env", main / "EN_API/.env"))
    sellfox_rows = fetch_sellfox_rows(client)
    catalog, excluded = build_candidate_catalog(valid_en, sellfox_rows)

    temp_catalog = output / "candidate_catalog.json.tmp"
    save_catalog(temp_catalog, catalog)
    temp_catalog.replace(output / "candidate_catalog.json")
    (output / "catalog_excluded.json").write_text(
        json.dumps(excluded, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "en_product_codes": len(product_codes),
        "en_details": len(valid_en),
        "en_errors": len(product_codes) - len(valid_en),
        "sellfox_rows": len(sellfox_rows),
        "candidate_products": len(catalog),
        "excluded": dict(Counter(row["reason"] for row in excluded)),
    }
    (output / "catalog_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


PILOT_FAMILIES = ("KS0001", "KS0002", "KS0248", "KS0007")


def _training_listings(frame: pd.DataFrame) -> list[TrainingListing]:
    rows = []
    deduped = frame.drop_duplicates(subset=["msku", "target_sku"])
    for _, row in deduped.iterrows():
        target = str(row.get("target_sku") or "")
        family = target.split("-", 1)[0]
        if family not in PILOT_FAMILIES:
            continue
        rows.append(
            TrainingListing(
                msku=str(row.get("msku") or ""),
                title=str(row.get("title") or ""),
                asin=str(row.get("asin") or ""),
                target_sku=target,
                family=family,
            )
        )
    return rows


def train_pilot(args: argparse.Namespace) -> int:
    labels = pd.read_csv(args.labels, dtype=str).fillna("")
    labels = labels[(labels["usable_for_training"].astype(str).str.lower() == "true")]
    catalog = load_catalog(args.catalog)
    catalog_skus = {product.sku for product in catalog}
    listings = [row for row in _training_listings(labels) if row.target_sku in catalog_skus]

    catalog_by_sku = {product.sku: product for product in catalog}
    split_examples = [
        PairExample(
            query_id=str(index), msku=row.msku, asin=row.asin,
            product=catalog_by_sku[row.target_sku], label=1, features={}
        )
        for index, row in enumerate(listings)
    ]
    train_markers, validation_markers = grouped_split(
        split_examples, validation_fraction=args.validation_fraction, seed=args.seed
    )
    train_ids = {int(row.query_id) for row in train_markers}
    validation_ids = {int(row.query_id) for row in validation_markers}
    train_rows = [row for index, row in enumerate(listings) if index in train_ids]
    validation_rows = [row for index, row in enumerate(listings) if index in validation_ids]

    family = FamilyClassifier(seed=args.seed).fit(train_rows)
    predicted_validation = [
        tuple(name for name, _ in family.predict(row.msku, row.title, top_k=2))
        for row in validation_rows
    ]
    family_top1 = sum(
        family.predict(row.msku, row.title, top_k=1)[0][0] == row.family for row in validation_rows
    ) / len(validation_rows)
    family_top2 = sum(
        row.family in predictions
        for row, predictions in zip(validation_rows, predicted_validation)
    ) / len(validation_rows)

    retriever = CandidateRetriever(catalog)
    _, raw_recall = build_pair_examples(
        validation_rows, catalog, max_candidates=20, predicted_families=predicted_validation,
        retriever=retriever, inject_positive=False
    )
    train_examples, _ = build_pair_examples(
        train_rows, catalog, max_candidates=20, retriever=retriever, inject_positive=True
    )
    validation_examples, _ = build_pair_examples(
        validation_rows, catalog, max_candidates=20, predicted_families=predicted_validation,
        retriever=retriever, inject_positive=True
    )
    ranker = RankingModel(seed=args.seed).fit(train_examples)
    scores = ranker.predict(validation_examples)
    rankings: dict[str, list[tuple[str, float, int]]] = {}
    for example, score in zip(validation_examples, scores):
        rankings.setdefault(example.query_id, []).append((example.product.sku, score, example.label))
    metrics = evaluate_rankings(rankings)
    per_family = {}
    for family_name in PILOT_FAMILIES:
        query_ids = {
            example.query_id for example in validation_examples if example.product.sku.startswith(family_name + "-") and example.label == 1
        }
        per_family[family_name] = evaluate_rankings(
            {query_id: rankings[query_id] for query_id in query_ids if query_id in rankings}
        )

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    family.save(output / "family_classifier.joblib")
    ranker.save(output / "ranker.txt")
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed": args.seed,
        "pilot_families": PILOT_FAMILIES,
        "training_listings": len(train_rows),
        "validation_listings": len(validation_rows),
        "family_top1": family_top1,
        "family_top2": family_top2,
        "raw_candidate_recall_at_20": raw_recall,
        "ranking": metrics,
        "per_family": per_family,
        "production_ready": raw_recall >= 0.98 and metrics.get("recall_at_3", 0) >= 0.65,
    }
    (output / "evaluation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def suggest_active(args: argparse.Namespace) -> int:
    main = args.main_workspace.resolve()
    unmatched_path = args.unmatched_cache or main / "missing_products/out/pairing_cache/amazon_unmatched.json"
    matched_path = args.matched_cache or main / "missing_products/out/pairing_cache/amazon_matched.json"
    unmatched = [row for row in load_amazon_cache(unmatched_path) if row.online_status.upper() == "ACTIVE"]
    matched = load_amazon_cache(matched_path)
    catalog = load_catalog(args.catalog)
    catalog_by_sku = {product.sku: product for product in catalog}
    family = FamilyClassifier.load(args.family_model)
    ranker = RankingModel.load(args.ranker_model)
    evaluation = json.loads(args.evaluation.read_text(encoding="utf-8"))

    labels = pd.read_csv(args.labels, dtype=str).fillna("")
    exact_map: dict[str, set[str]] = {}
    for _, row in labels[labels["tier"] == "gold_a"].iterrows():
        exact_map.setdefault(str(row["msku"]).casefold(), set()).add(str(row["target_sku"]))
    asin_map: dict[tuple[str, str], set[str]] = {}
    for row in matched:
        if row.asin and row.target_sku:
            asin_map.setdefault((row.marketplace_id, row.asin), set()).add(row.target_sku)

    exact_records: list[ReviewRecord] = []
    model_pending = []
    specials = []
    no_candidates = []
    for row in unmatched:
        route = route_listing(row.msku, row.title, row.parent_sku)
        if route.object_type != "ordinary":
            specials.append({
                "MSKU": row.msku, "ASIN": row.asin, "标题": row.title,
                "对象类型": route.object_type, "原因": " | ".join(route.reasons),
            })
            continue
        exact_targets = {sku for sku in exact_map.get(row.msku.casefold(), set()) if sku in catalog_by_sku}
        asin_targets = {
            sku for sku in asin_map.get((row.marketplace_id, row.asin), set()) if sku in catalog_by_sku
        } if row.asin else set()
        strong_targets = exact_targets or (asin_targets if len(asin_targets) == 1 else set())
        if len(strong_targets) == 1:
            product = catalog_by_sku[next(iter(strong_targets))]
            evidence = "strict_alias" if exact_targets else "unique_marketplace_asin_history"
            exact_records.append(
                ReviewRecord(
                    shop=row.shop_id, marketplace=row.marketplace_id, msku=row.msku, asin=row.asin,
                    title=row.title, image_url=row.image_url, route="ordinary",
                    candidates=((product.sku, product.name, 1.0, evidence),), warnings="仍需人工确认",
                )
            )
            continue
        predictions = family.predict(row.msku, row.title, top_k=2)
        if not predictions or predictions[0][1] < args.min_family_score:
            no_candidates.append({"MSKU": row.msku, "ASIN": row.asin, "标题": row.title, "原因": "family_confidence_low"})
            continue
        attributes = extract_attributes(f"{row.msku} {row.title}")
        model_pending.append((row, predictions, attributes))

    retriever = CandidateRetriever(catalog)
    selected_many = retriever.retrieve_many(
        [(row.msku, row.title, tuple(name for name, _ in predictions), attributes) for row, predictions, attributes in model_pending],
        20,
    )
    model_records: list[ReviewRecord] = []
    for (row, predictions, attributes), selected in zip(model_pending, selected_many):
        query = ListingQuery(
            row.msku, row.title, tuple(name for name, _ in predictions), attributes
        )
        examples = [
            PairExample(
                f"{row.shop_id}|{row.msku}", row.msku, row.asin, catalog[index], 0,
                build_pair_features(query, catalog[index])
            )
            for index in selected
        ]
        compatible_examples = [
            example for example in examples if example.features["reliable_conflicts"] == 0
        ]
        if compatible_examples:
            examples = compatible_examples
        if not examples:
            no_candidates.append({"MSKU": row.msku, "ASIN": row.asin, "标题": row.title, "原因": "empty_candidate_pool"})
            continue
        if all(example.features["reliable_conflicts"] > 0 for example in examples):
            no_candidates.append({
                "MSKU": row.msku, "ASIN": row.asin, "标题": row.title,
                "原因": "all_candidates_have_reliable_conflicts",
            })
            continue
        scores = ranker.predict(examples)
        ranked = sorted(zip(examples, scores), key=lambda pair: pair[1], reverse=True)[:3]
        candidates = tuple(
            (example.product.sku, example.product.name, float(score), f"family={predictions[0][0]}; conflicts={example.features['reliable_conflicts']}")
            for example, score in ranked
        )
        model_records.append(
            ReviewRecord(
                shop=row.shop_id, marketplace=row.marketplace_id, msku=row.msku, asin=row.asin,
                title=row.title, image_url=row.image_url, route="ordinary", candidates=candidates,
                recognized_attributes=str(attributes),
                warnings="实验级：当前模型未通过候选召回门槛，仅供人工审核",
            )
        )

    output = args.output.resolve()
    summary = {
        "输入在售未配对": len(unmatched),
        "高可信精确证据": len(exact_records),
        "实验模型候选": len(model_records),
        "特殊对象暂缓": len(specials),
        "无可靠候选": len(no_candidates),
        "数量对账": len(exact_records) + len(model_records) + len(specials) + len(no_candidates),
        "模型可生产使用": evaluation.get("production_ready", False),
        "写入赛狐": "禁止，本工作簿仅审核建议",
        "labels_sha256": _sha256(args.labels),
        "catalog_sha256": _sha256(args.catalog),
        "family_model_sha256": _sha256(args.family_model),
        "ranker_model_sha256": _sha256(args.ranker_model),
        "evaluation_sha256": _sha256(args.evaluation),
        "unmatched_cache_sha256": _sha256(unmatched_path),
        "matched_cache_sha256": _sha256(matched_path),
    }
    metrics = {
        "family_top1": evaluation.get("family_top1", 0),
        "family_top2": evaluation.get("family_top2", 0),
        "raw_candidate_recall_at_20": evaluation.get("raw_candidate_recall_at_20", 0),
        **{f"ranking_{key}": value for key, value in evaluation.get("ranking", {}).items()},
    }
    quarantine = labels[labels["tier"] == "quarantine"][["msku", "target_sku", "reasons"]].to_dict("records")
    write_review_workbook(
        output, model_records, summary, specials, no_candidates, quarantine, metrics, exact_records=exact_records
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"workbook={output}")
    return 0

def suggest_v2(args: argparse.Namespace) -> int:
    main = args.main_workspace.resolve()
    unmatched_path = args.unmatched_cache or main / "missing_products/out/pairing_cache/amazon_unmatched.json"
    matched_path = args.matched_cache or main / "missing_products/out/pairing_cache/amazon_matched.json"
    matched = load_amazon_cache(matched_path)
    unmatched = [row for row in load_amazon_cache(unmatched_path) if row.online_status.upper() == "ACTIVE"]
    catalog = load_catalog(args.catalog)
    catalog_by_sku = {product.sku: product for product in catalog}
    index = EvidenceIndex.build([row.raw for row in matched])
    fallback_positions = [
        position
        for position, row in enumerate(unmatched)
        if not index.candidates_for_listing(row.raw)
    ]
    fallback_maps = build_fallback_evidence(
        [unmatched[position].raw for position in fallback_positions],
        catalog,
    ) if fallback_positions else []
    if fallback_positions and args.family_model.exists():
        family_model = FamilyClassifier.load(args.family_model)
        predicted_families = [
            tuple(name for name, _ in family_model.predict(row.msku, row.title, top_k=2))
            for row in (unmatched[position] for position in fallback_positions)
        ]
        fallback_maps = build_fallback_evidence(
            [unmatched[position].raw for position in fallback_positions],
            catalog,
            predicted_families=predicted_families,
        )
    fallback_indexes = dict(zip(fallback_positions, fallback_maps))
    decisions = [
        (
            row.raw,
            decide_v2(
                row.raw,
                index,
                catalog_by_sku,
                fallback_evidence=fallback_indexes.get(position),
            ),
        )
        for position, row in enumerate(unmatched)
    ]
    buckets = Counter(decision.bucket for _, decision in decisions)
    summary = {
        "输入在售未配对": len(unmatched),
        "强证据建议": buckets.get("strong_single", 0),
        "Top候选审核": buckets.get("candidate", 0),
        "低证据候选": buckets.get("low_candidate", 0),
        "冲突候选审核": buckets.get("conflict", 0),
        "对象专项": buckets.get("special", 0) + buckets.get("special_with_candidate", 0),
        "无候选": buckets.get("no_candidate", 0),
        "数量对账": len(decisions),
        "模型可生产使用": False,
        "写入赛狐": "禁止，本工作簿仅审核建议",
        "unmatched_cache_sha256": _sha256(unmatched_path),
        "matched_cache_sha256": _sha256(matched_path),
        "catalog_sha256": _sha256(args.catalog),
    }
    output = args.output.resolve()
    write_v2_workbook(output, decisions, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"workbook={output}")
    return 0

def import_feedback(args: argparse.Namespace) -> int:
    catalog = load_catalog(args.catalog)
    summary_frame = pd.read_excel(args.workbook, sheet_name="运行汇总", dtype=str).fillna("")
    summary = dict(zip(summary_frame["指标"], summary_frame["值"]))
    frames = []
    for sheet in ("高可信精确证据", "智能候选审核"):
        frame = pd.read_excel(args.workbook, sheet_name=sheet, dtype=str).fillna("")
        selected = frame[frame["人工结论"] != ""].copy() if "人工结论" in frame else frame.iloc[0:0].copy()
        selected["source_sheet"] = sheet
        frames.append(selected)
    feedback = validate_feedback(pd.concat(frames, ignore_index=True), {row.sku for row in catalog})
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    feedback["imported_at"] = datetime.now(timezone.utc).isoformat()
    feedback["source_workbook"] = str(args.workbook.resolve())
    feedback["source_workbook_sha256"] = _sha256(args.workbook)
    for key, path in (
        ("catalog_sha256", args.catalog),
        ("family_model_sha256", args.family_model),
        ("ranker_model_sha256", args.ranker_model),
        ("evaluation_sha256", args.evaluation),
    ):
        feedback[key] = summary.get(key) or _sha256(path)
    for key in ("labels_sha256", "unmatched_cache_sha256", "matched_cache_sha256"):
        feedback[key] = summary.get(key, "")
    feedback.to_json(output, orient="records", lines=True, force_ascii=False, mode="a")
    print(f"feedback_rows={len(feedback)} output={output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Amazon pairing assistance pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    labels = sub.add_parser("build-labels", help="Audit historical matched listings")
    labels.add_argument("--main-workspace", type=Path, default=DEFAULT_MAIN)
    labels.add_argument("--matched-cache", type=Path)
    labels.add_argument("--mapping", type=Path)
    labels.add_argument("--tongtu-zip", type=Path)
    labels.add_argument("--output", type=Path, default=ROOT / "amazon_pairing/out/labels")
    labels.set_defaults(func=build_labels)
    catalog = sub.add_parser("snapshot-catalog", help="Snapshot EN/Sellfox ordinary products")
    catalog.add_argument("--main-workspace", type=Path, default=DEFAULT_MAIN)
    catalog.add_argument("--output", type=Path, default=ROOT / "amazon_pairing/out/catalog")
    catalog.set_defaults(func=snapshot_catalog)
    train = sub.add_parser("train-pilot", help="Train and evaluate the four-family pilot")
    train.add_argument("--labels", type=Path, default=ROOT / "amazon_pairing/out/labels/historical_label_audit.csv")
    train.add_argument("--catalog", type=Path, default=ROOT / "amazon_pairing/out/catalog/candidate_catalog.json")
    train.add_argument("--output", type=Path, default=ROOT / "amazon_pairing/out/model")
    train.add_argument("--validation-fraction", type=float, default=0.2)
    train.add_argument("--seed", type=int, default=42)
    train.set_defaults(func=train_pilot)
    suggest = sub.add_parser("suggest-active", help="Build the read-only active-unpaired review workbook")
    suggest.add_argument("--main-workspace", type=Path, default=DEFAULT_MAIN)
    suggest.add_argument("--unmatched-cache", type=Path)
    suggest.add_argument("--matched-cache", type=Path)
    suggest.add_argument("--labels", type=Path, default=ROOT / "amazon_pairing/out/labels/historical_label_audit.csv")
    suggest.add_argument("--catalog", type=Path, default=ROOT / "amazon_pairing/out/catalog/candidate_catalog.json")
    suggest.add_argument("--family-model", type=Path, default=ROOT / "amazon_pairing/out/model/family_classifier.joblib")
    suggest.add_argument("--ranker-model", type=Path, default=ROOT / "amazon_pairing/out/model/ranker.txt")
    suggest.add_argument("--evaluation", type=Path, default=ROOT / "amazon_pairing/out/model/evaluation.json")
    suggest.add_argument("--min-family-score", type=float, default=0.5)
    suggest.add_argument("--output", type=Path, default=ROOT / f"amazon_pairing/out/Amazon在售未配对智能审核_{datetime.now():%Y%m%d_%H%M%S}.xlsx")
    suggest.set_defaults(func=suggest_active)
    v2 = sub.add_parser("suggest-v2", help="Build the evidence-graph V2 review workbook")
    v2.add_argument("--main-workspace", type=Path, default=DEFAULT_MAIN)
    v2.add_argument("--unmatched-cache", type=Path)
    v2.add_argument("--matched-cache", type=Path)
    v2.add_argument("--catalog", type=Path, default=ROOT / "amazon_pairing/out/catalog/candidate_catalog.json")
    v2.add_argument("--family-model", type=Path, default=ROOT / "amazon_pairing/out/model/family_classifier.joblib")
    v2.add_argument("--output", type=Path, default=ROOT / f"amazon_pairing/out/Amazon在售未配对证据图审核_{datetime.now():%Y%m%d_%H%M%S}.xlsx")
    v2.set_defaults(func=suggest_v2)
    feedback = sub.add_parser("import-feedback", help="Validate and append human review feedback")
    feedback.add_argument("workbook", type=Path)
    feedback.add_argument("--catalog", type=Path, default=ROOT / "amazon_pairing/out/catalog/candidate_catalog.json")
    feedback.add_argument("--family-model", type=Path, default=ROOT / "amazon_pairing/out/model/family_classifier.joblib")
    feedback.add_argument("--ranker-model", type=Path, default=ROOT / "amazon_pairing/out/model/ranker.txt")
    feedback.add_argument("--evaluation", type=Path, default=ROOT / "amazon_pairing/out/model/evaluation.json")
    feedback.add_argument("--output", type=Path, default=ROOT / "amazon_pairing/out/feedback/confirmed.jsonl")
    feedback.set_defaults(func=import_feedback)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
