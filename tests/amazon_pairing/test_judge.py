import pytest

from amazon_pairing.judge import JudgeResult, parse_judge_response


def test_parse_judge_accepts_strict_schema():
    result = parse_judge_response(
        """
        {
          "listing_id": "L1",
          "target_sku": "KS0001-HLR-153-DEEPBLUE",
          "confidence": 0.91,
          "reason": "size and color match",
          "abstain": false,
          "missing_info": []
        }
        """,
        listing_id="L1",
        allowed_skus={"KS0001-HLR-153-DEEPBLUE"},
    )

    assert result == JudgeResult(
        target_sku="KS0001-HLR-153-DEEPBLUE",
        confidence=0.91,
        reason="size and color match",
        abstain=False,
        missing_info=(),
    )


def test_parse_judge_rejects_target_outside_candidates():
    with pytest.raises(ValueError, match="not in candidate list"):
        parse_judge_response(
            """
            {
              "listing_id": "L1",
              "target_sku": "KS9999-NOT-ALLOWED",
              "confidence": 0.95,
              "reason": "guess",
              "abstain": false,
              "missing_info": []
            }
            """,
            listing_id="L1",
            allowed_skus={"KS0001-HLR-153-DEEPBLUE"},
        )


def test_parse_judge_maps_qualitative_confidence():
    result = parse_judge_response(
        """
        {
          "listing_id": "L1",
          "target_sku": "KS0001-HLR-153-DEEPBLUE",
          "confidence": "high",
          "reason": "strong evidence",
          "abstain": false,
          "missing_info": []
        }
        """,
        listing_id="L1",
        allowed_skus={"KS0001-HLR-153-DEEPBLUE"},
    )

    assert result.confidence == 0.9
    assert result.abstain is False


def test_parse_judge_forces_abstain_on_low_confidence():
    result = parse_judge_response(
        """
        {
          "listing_id": "L1",
          "target_sku": "KS0001-HLR-153-DEEPBLUE",
          "confidence": 0.4,
          "reason": "weak",
          "abstain": false,
          "missing_info": ["fabric"]
        }
        """,
        listing_id="L1",
        allowed_skus={"KS0001-HLR-153-DEEPBLUE"},
    )

    assert result.abstain is True


def test_parse_judge_rejects_unknown_schema_fields():
    with pytest.raises(ValueError, match="unknown field"):
        parse_judge_response(
            """
            {
              "listing_id": "L1",
              "target_sku": "KS0001-HLR-153-DEEPBLUE",
              "confidence": 0.9,
              "reason": "ok",
              "abstain": false,
              "missing_info": [],
              "hallucinated": "value"
            }
            """,
            listing_id="L1",
            allowed_skus={"KS0001-HLR-153-DEEPBLUE"},
        )
