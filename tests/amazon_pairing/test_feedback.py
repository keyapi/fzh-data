from argparse import Namespace
from pathlib import Path

import pandas as pd
import pytest

from amazon_pairing.attributes import AttributeValue, ListingAttributes
from amazon_pairing.candidates import CandidateProduct
from amazon_pairing.catalog import save_catalog
from amazon_pairing.cli import import_feedback
from amazon_pairing.feedback import validate_feedback


def test_feedback_accepts_top_choice_and_manual_catalog_sku():
    frame = pd.DataFrame(
        [
            {"MSKU": "A", "人工结论": "确认Top1", "Top1 SKU": "KS0001-A", "正确SKU另填": ""},
            {"MSKU": "B", "人工结论": "正确SKU另填", "Top1 SKU": "KS0001-A", "正确SKU另填": "KS0001-B"},
        ]
    )

    result = validate_feedback(frame, {"KS0001-A", "KS0001-B"})

    assert list(result["confirmed_sku"]) == ["KS0001-A", "KS0001-B"]


def test_feedback_rejects_manual_sku_outside_catalog():
    frame = pd.DataFrame(
        [{"MSKU": "A", "人工结论": "正确SKU另填", "正确SKU另填": "BAD-SKU"}]
    )

    with pytest.raises(ValueError, match="BAD-SKU"):
        validate_feedback(frame, {"KS0001-A"})


def test_import_feedback_appends_provenance_hashes(tmp_path: Path):
    workbook = tmp_path / "review.xlsx"
    exact = pd.DataFrame(
        [{"MSKU": "A", "人工结论": "确认Top1", "Top1 SKU": "KS0001-A"}]
    )
    model = pd.DataFrame(columns=exact.columns)
    summary = pd.DataFrame(
        [
            ("catalog_sha256", "catalog-at-generation"),
            ("family_model_sha256", "family-at-generation"),
            ("ranker_model_sha256", "ranker-at-generation"),
            ("evaluation_sha256", "evaluation-at-generation"),
        ],
        columns=["指标", "值"],
    )
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="运行汇总", index=False)
        exact.to_excel(writer, sheet_name="高可信精确证据", index=False)
        model.to_excel(writer, sheet_name="智能候选审核", index=False)

    empty = ListingAttributes(
        AttributeValue(), AttributeValue(), AttributeValue(), AttributeValue()
    )
    catalog = tmp_path / "catalog.json"
    save_catalog(catalog, [CandidateProduct("KS0001-A", "KS0001", "A", empty)])
    family_model = tmp_path / "family.joblib"
    ranker_model = tmp_path / "ranker.txt"
    evaluation = tmp_path / "evaluation.json"
    family_model.write_bytes(b"family")
    ranker_model.write_bytes(b"ranker")
    evaluation.write_text('{"production_ready": false}', encoding="utf-8")
    output = tmp_path / "confirmed.jsonl"

    import_feedback(
        Namespace(
            workbook=workbook,
            catalog=catalog,
            family_model=family_model,
            ranker_model=ranker_model,
            evaluation=evaluation,
            output=output,
        )
    )

    row = pd.read_json(output, lines=True).iloc[0]
    assert row["source_sheet"] == "高可信精确证据"
    assert row["source_workbook"] == str(workbook.resolve())
    assert row["source_workbook_sha256"]
    assert row["catalog_sha256"] == "catalog-at-generation"
    assert row["family_model_sha256"] == "family-at-generation"
    assert row["ranker_model_sha256"] == "ranker-at-generation"
    assert row["evaluation_sha256"] == "evaluation-at-generation"
