import json
from argparse import Namespace
from pathlib import Path

import pandas as pd

from amazon_pairing.attributes import AttributeValue, ListingAttributes
from amazon_pairing.candidates import CandidateProduct
from amazon_pairing.catalog import save_catalog
from amazon_pairing.cli import train_family


def test_train_family_saves_classifier_and_summary(tmp_path: Path):
    labels = tmp_path / "labels.csv"
    pd.DataFrame(
        [
            {
                "msku": "A",
                "title": "triangle pillow",
                "target_sku": "KS0001-HLR-153-BLUE",
                "usable_for_training": "true",
            },
            {
                "msku": "B",
                "title": "long bolster pillow",
                "target_sku": "KS0002-DM-100-BLUE",
                "usable_for_training": "true",
            },
        ]
    ).to_csv(labels, index=False, encoding="utf-8-sig")
    catalog = tmp_path / "catalog.json"
    empty = ListingAttributes(
        AttributeValue(), AttributeValue(), AttributeValue(), AttributeValue()
    )
    save_catalog(
        catalog,
        [
            CandidateProduct("KS0001-HLR-153-BLUE", "KS0001", "A", empty),
            CandidateProduct("KS0002-DM-100-BLUE", "KS0002", "B", empty),
        ],
    )
    output = tmp_path / "model"

    result = train_family(
        Namespace(labels=labels, catalog=catalog, output=output, seed=7)
    )

    assert result == 0
    assert (output / "family_classifier_all.joblib").exists()
    summary = json.loads((output / "family_summary.json").read_text(encoding="utf-8"))
    assert summary["families"] == 2
    assert summary["listings"] == 2
