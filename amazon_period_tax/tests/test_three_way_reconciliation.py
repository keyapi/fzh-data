# -*- coding: utf-8 -*-
"""D 批三方对账：正/负/零结转、缺失一侧、身份/金额/期间冲突、分页完整性、例外失效。"""
from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal

import pytest

from reconciliation import (
    AMOUNT_TOLERANCE,
    ExceptionBook,
    ExceptionEntry,
    GroupFact,
    OaFact,
    ReconciliationError,
    TxtFact,
    fetch_groups,
    oa_facts_from_frame,
    parse_group,
    reconcile,
    store_account_map,
    txt_facts_from_read,
)

TODAY = date(2026, 8, 15)
PERIOD = "2026-07"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_group(
    sid: str = "S1",
    *,
    gid: str | None = None,
    store: str = "Store-US",
    account: str = "AMZAcctUS",
    currency: str = "USD",
    end: str = "2026-07-10",
    transfer: float = 100.0,
    net: float = 100.0,
    status: str = "转账成功",
    processing: str = "已结算",
) -> GroupFact:
    raw = {
        "settlementId": sid,
        "groupId": gid or f"G{sid}",
        "currency": currency,
        "transferAmount": transfer,
        "accountNetIncome": net,
        "accountIncome": net,
        "accountRefund": 0.0,
        "accountExpenditure": 0.0,
        "beginningBalance": 0.0,
        "endingBalance": 0.0,
        "storeName": store,
        "marketplaceName": "美国",
        "processingStatusStr": processing,
        "fundTransferStatusStr": status,
        "siteGroupEndStr": end,
        "groupEndStr": end,
        "siteFundTransferDateStr": end,
        "utcFundTransferDateStr": end,
    }
    return parse_group(raw, {store: account})


def make_txt(
    sid: str = "S1",
    *,
    account: str = "AMZAcctUS",
    currency: str = "USD",
    end: str = "2026-07-10",
    header=100.0,
    detail=100.0,
    rel: str | None = None,
    schema: str = "v2",
) -> TxtFact:
    return TxtFact(
        settlement_id=sid,
        rel=rel or f"运营A/AMZAcctUS-{sid}.txt",
        bucket="账期20260704-20260803",
        account=account,
        currency=currency,
        end_date=date.fromisoformat(end),
        deposit_date=date.fromisoformat(end),
        header_total=None if header is None else Decimal(str(header)),
        detail_net=None if detail is None else Decimal(str(detail)),
        schema=schema,
        sha256=_sha(f"{sid}|{header}|{schema}"),
        rows=1,
    )


def make_oa(
    *,
    account: str = "AMZAcctUS",
    currency: str = "USD",
    settle: str = "2026-07-10",
    amount=100.0,
    approval: str = "A1",
    row_id: str | None = None,
) -> OaFact:
    return OaFact(
        row_id=row_id or f"{approval}|{settle}|{account}|{amount}",
        approval_id=approval,
        account=account,
        currency=currency,
        settle_date=date.fromisoformat(settle),
        amount=Decimal(str(amount)),
        sales_amount=Decimal("1000"),
        platform="亚马逊",
        person=account,
        submit_class="正常",
    )


def run(groups, txts, oas, **kwargs):
    return reconcile(PERIOD, groups, txts, oas, today=TODAY, **kwargs)


def link_of(result, sid="S1"):
    return next(l for l in result.links if l.settlement_id == sid)


# ---------------------------------------------------------------- 金额口径


def test_positive_net_matches_as_triplet():
    result = run([make_group()], [make_txt()], [make_oa()])
    link = link_of(result)
    assert link.state == "matched_triplet"
    assert link.group.compare_rule == "transfer_amount"
    assert result.publishable is True


def test_negative_carryover_uses_account_net_income_when_transfer_zero():
    g = make_group(transfer=0.0, net=-644.21, status="转账未知")
    t = make_txt(header=-644.21, detail=-644.21)
    o = make_oa(amount=-644.21)
    result = run([g], [t], [o])
    link = link_of(result)
    assert link.state == "matched_triplet"
    assert link.group.compare_rule == "account_net_income"
    assert link.group_amount == Decimal("-644.21")


def test_zero_transfer_and_zero_net_is_kept_not_dropped():
    g = make_group(transfer=0.0, net=0.0, status="转账失败")
    t = make_txt(header=0.0, detail=0.0)
    o = make_oa(amount=0.0)
    result = run([g], [t], [o])
    assert link_of(result).state == "matched_triplet"


def test_untransferred_group_is_included_in_expected_set():
    g = make_group(transfer=0.0, net=-19.31, status="转账未知")
    t = make_txt(header=-19.31, detail=-19.31)
    o = make_oa(amount=-19.31)
    result = run([g], [t], [o])
    assert result.partition_counts()["excluded_by_approved_policy"] == 0
    assert link_of(result).state == "matched_triplet"


def test_negative_transfer_amount_compares_transfer():
    g = make_group(transfer=-5.0, net=-5.0, status="转账失败")
    t = make_txt(header=-5.0, detail=-5.0)
    result = run([g], [t], [make_oa(amount=-5.0)])
    assert link_of(result).group.compare_rule == "transfer_amount"


# ---------------------------------------------------------------- 三方差集


def test_group_without_txt_or_oa_is_group_only():
    result = run([make_group()], [], [])
    link = link_of(result)
    assert link.state == "group_only"
    assert "UNREVIEWED-ORPHAN group_only=1" in result.blockers()


def test_txt_without_group_or_oa_is_txt_only():
    result = run([], [make_txt()], [])
    assert link_of(result).state == "txt_only"


def test_oa_without_any_source_is_oa_only():
    result = run([], [], [make_oa()])
    assert link_of(result, "OA:A1|2026-07-10|AMZAcctUS|100.0").state == "oa_only"


def test_group_and_txt_without_oa_is_pair_only():
    result = run([make_group()], [make_txt()], [])
    link = link_of(result)
    assert link.state == "pair_only"
    assert link.pair_kind == "group+txt"


def test_group_and_oa_without_txt_is_pair_only():
    result = run([make_group()], [], [make_oa()])
    link = link_of(result)
    assert link.state == "pair_only"
    assert link.pair_kind == "group+oa"


def test_txt_and_oa_without_group_is_pair_only():
    result = run([], [make_txt()], [make_oa()])
    link = link_of(result)
    assert link.state == "pair_only"
    assert link.pair_kind == "txt+oa"


# ---------------------------------------------------------------- 身份冲突


def test_same_sid_different_account_is_identity_conflict():
    result = run([make_group(account="AMZAcctUS")], [make_txt(account="AMZOtherUS")], [])
    link = link_of(result)
    assert link.state == "identity_conflict"
    assert "account" in link.reason


def test_currency_mismatch_is_identity_conflict():
    result = run([make_group(currency="USD")], [make_txt(currency="EUR")], [])
    assert link_of(result).state == "identity_conflict"


def test_group_txt_end_date_one_day_is_not_identity_conflict():
    # 赛狐 siteGroupEnd 与 Amazon txt UTC 结算日可差 1 天；身份键是 settlement-id。
    result = run([make_group(end="2026-07-10")], [make_txt(end="2026-07-11")], [])
    link = link_of(result)
    assert link.state == "pair_only"
    assert link.group_txt_date_delta == 1


# ---------------------------------------------------------------- 歧义与差额


def test_same_amount_multiple_candidates_is_ambiguous():
    groups = [make_group(sid="S1"), make_group(sid="S2", gid="G2")]
    result = run(groups, [], [make_oa()])
    assert result.partition_counts()["ambiguous"] == 2
    assert all(o.state == "ambiguous" for o in result.oa_facts)


def test_duplicate_oa_claim_is_ambiguous_not_silently_merged():
    first = make_oa(approval="A1")
    second = make_oa(approval="A2", row_id="A2|2026-07-10|AMZAcctUS|100.0")
    result = run([make_group()], [make_txt()], [first, second])
    link = link_of(result)
    assert link.state == "ambiguous"
    assert link.reason == "DUPLICATE_OA_CLAIM"


def test_amount_difference_above_one_cent_is_amount_mismatch():
    result = run([make_group()], [make_txt(header=100.02, detail=100.02)], [make_oa(amount=100.02)])
    link = link_of(result)
    assert link.state == "amount_mismatch"
    assert abs(link.amount_diff) == Decimal("0.02")


def test_amount_difference_exactly_one_cent_matches():
    result = run([make_group()], [make_txt(header=100.01, detail=100.01)], [make_oa(amount=100.01)])
    assert link_of(result).state == "matched_triplet"
    assert AMOUNT_TOLERANCE == Decimal("0.01")


def test_hundredfold_amount_is_diagnosed_not_divided():
    result = run([make_group()], [], [make_oa(amount=10000.0)])
    link = link_of(result)
    assert link.state == "amount_mismatch"
    assert link.oa_amount == Decimal("10000.0")
    assert "oa=10000.0 source=100" in link.reason


# ---------------------------------------------------------------- 期间 / 容差


def test_date_outside_zero_tolerance_is_period_mismatch():
    result = run([make_group()], [make_txt()], [make_oa(settle="2026-07-11")])
    link = link_of(result)
    assert link.state == "period_mismatch"
    assert "date_delta=1" in link.reason


def test_approved_date_tolerance_matches_as_triplet():
    book = ExceptionBook(
        [
            ExceptionEntry(
                reason_code="DATE_TOLERANCE",
                key="AMZAcctUS",
                scope="account",
                approver_role="财务账期负责人",
                approved_at="2026-07-01",
                valid_until="2026-12-31",
                payload={"days": 2},
            )
        ]
    )
    result = run([make_group()], [make_txt()], [make_oa(settle="2026-07-11")], book=book)
    link = link_of(result)
    assert link.state == "matched_triplet"
    assert "DATE_TOLERANCE days=1" in link.reason
    assert result.tolerance_policy["accounts"]["AMZAcctUS"]["days"] == 2


def test_expired_date_tolerance_is_not_applied():
    book = ExceptionBook(
        [
            ExceptionEntry(
                reason_code="DATE_TOLERANCE",
                key="AMZAcctUS",
                scope="account",
                approver_role="财务账期负责人",
                approved_at="2026-01-01",
                valid_until="2026-02-01",
                payload={"days": 2},
            )
        ]
    )
    result = run([make_group()], [make_txt()], [make_oa(settle="2026-07-11")], book=book)
    assert link_of(result).state == "period_mismatch"


def test_date_tolerance_without_approver_is_invalid():
    book = ExceptionBook(
        [
            ExceptionEntry(
                reason_code="DATE_TOLERANCE",
                key="AMZAcctUS",
                scope="account",
                approver_role="",
                approved_at="",
                payload={"days": 2},
            )
        ]
    )
    result = run([make_group()], [make_txt()], [make_oa(settle="2026-07-11")], book=book)
    assert link_of(result).state == "period_mismatch"


# ---------------------------------------------------------------- 期间分类


def test_out_of_period_group_without_policy_needs_review():
    g = make_group(end="2026-06-30")
    result = run([g], [], [])
    link = link_of(result)
    assert link.state == "needs_review"
    assert g.state == "needs_review"


def test_out_of_period_group_approved_include():
    book = ExceptionBook(
        [
            ExceptionEntry(
                reason_code="OUT_OF_PERIOD",
                key="group:S1",
                scope="settlement",
                approver_role="财务账期负责人",
                approved_at="2026-07-01",
                valid_until="2026-12-31",
                payload={"action": "include"},
            )
        ]
    )
    g = make_group(end="2026-06-30")
    result = run([g], [], [], book=book)
    assert g.state == "included"
    assert link_of(result).state == "group_only"


def test_out_of_period_group_approved_exclude():
    book = ExceptionBook(
        [
            ExceptionEntry(
                reason_code="OUT_OF_PERIOD",
                key="group:S1",
                scope="settlement",
                approver_role="财务账期负责人",
                approved_at="2026-07-01",
                valid_until="2026-12-31",
                payload={"action": "exclude"},
            )
        ]
    )
    g = make_group(end="2026-06-30")
    result = run([g], [], [], book=book)
    assert link_of(result).state == "excluded_by_approved_policy"
    assert result.partition_counts()["excluded_by_approved_policy"] == 1


# ---------------------------------------------------------------- txt 版本


def test_v1_v2_dual_same_sid_needs_review():
    t1 = make_txt(schema="v1")
    t2 = make_txt(schema="v2", rel="运营B/AMZAcctUS-copy.txt")
    result = run([make_group()], [t1, t2], [])
    states = {l.state for l in result.links}
    assert states == {"needs_review"}
    assert any("V1_V2_DUAL" in (l.reason or "") for l in result.links)


def test_same_sid_multiple_versions_needs_review():
    t1 = make_txt(header=100.0)
    t2 = make_txt(header=100.0, rel="运营B/AMZAcctUS-v2.txt")
    result = run([make_group()], [t1, t2], [])
    assert any("SID_MULTIPLE_FILES" in (l.reason or "") for l in result.links)


def test_header_detail_mismatch_needs_review():
    result = run([make_group()], [make_txt(header=100.0, detail=99.0)], [])
    link = link_of(result)
    assert link.state == "needs_review"
    assert "header_detail_mismatch" in link.reason


# ---------------------------------------------------------------- 例外失效


def test_amount_mismatch_exception_keeps_partition_but_unblocks():
    txt = make_txt(header=100.02, detail=100.02)
    observed = txt.sha256
    book = ExceptionBook(
        [
            ExceptionEntry(
                reason_code="AMOUNT_MISMATCH",
                key="S1",
                scope="settlement",
                approver_role="财务账期负责人",
                approved_at="2026-08-01",
                valid_until="2026-12-31",
                payload={"sha256": observed},
            )
        ]
    )
    result = run([make_group()], [txt], [make_oa(amount=100.02)], book=book)
    link = link_of(result)
    assert link.state == "amount_mismatch"  # 例外不改写成 PASS
    assert link.blocking is False
    assert link.exception["reason_code"] == "AMOUNT_MISMATCH"


def test_amount_exception_hash_change_invalidates():
    book = ExceptionBook(
        [
            ExceptionEntry(
                reason_code="AMOUNT_MISMATCH",
                key="S1",
                scope="settlement",
                approver_role="财务账期负责人",
                approved_at="2026-08-01",
                valid_until="2026-12-31",
                payload={"sha256": "deadbeef" * 8},
            )
        ]
    )
    result = run([make_group()], [make_txt(header=100.02, detail=100.02)], [], book=book)
    link = link_of(result)
    assert link.blocking is True
    assert link.exception is None


def test_orphan_exception_unblocks_but_keeps_partition():
    book = ExceptionBook(
        [
            ExceptionEntry(
                reason_code="GROUP_WITHOUT_TXT_OA",
                key="S1",
                scope="settlement",
                approver_role="财务账期负责人",
                approved_at="2026-08-01",
                valid_until="2026-12-31",
            )
        ]
    )
    result = run([make_group()], [], [], book=book)
    link = link_of(result)
    assert link.state == "group_only"
    assert link.blocking is False


# ---------------------------------------------------------------- 分页完整性


def _fake_post(pages, *, total_size=None, total_page=None):
    """pages: list[list[dict]]；返回 (post, calls)。"""
    calls = []

    def post(path, body):
        calls.append(dict(body))
        idx = int(body["pageNo"]) - 1
        rows = pages[idx] if idx < len(pages) else []
        tp = total_page if total_page is not None else len(pages)
        return {
            "groupVoList": rows,
            "pageNo": body["pageNo"],
            "pageSize": body["pageSize"],
            "totalPage": tp,
            "totalSize": total_size if total_size is not None else sum(len(p) for p in pages),
        }

    return post, calls


def _raw_group(sid: str) -> dict:
    return {
        "settlementId": sid,
        "groupId": f"G{sid}",
        "currency": "USD",
        "transferAmount": 10.0,
        "accountNetIncome": 10.0,
        "storeName": "Store-US",
        "marketplaceName": "美国",
        "processingStatusStr": "已结算",
        "fundTransferStatusStr": "转账成功",
        "siteGroupEndStr": "2026-07-10 00:00:00",
    }


def test_pagination_completes_two_pages():
    post, calls = _fake_post([[_raw_group("S1")], [_raw_group("S2")]])
    result = fetch_groups(post, "2026-07-01", "2026-07-31", page_size=1, store_to_account={"Store-US": "A"})
    assert len(result.groups) == 2
    assert len(calls) == 2


def test_pagination_interruption_raises():
    post, _ = _fake_post([[_raw_group("S1")], [], [_raw_group("S2")]], total_page=3, total_size=2)
    with pytest.raises(ReconciliationError, match="早停"):
        fetch_groups(post, "2026-07-01", "2026-07-31", page_size=1)


def test_duplicate_page_raises():
    same = [_raw_group("S1")]
    post, _ = _fake_post([same, same], total_page=2, total_size=2)
    with pytest.raises(ReconciliationError, match="重复页"):
        fetch_groups(post, "2026-07-01", "2026-07-31", page_size=1)


def test_total_size_contradiction_raises():
    post, _ = _fake_post([[_raw_group("S1")]], total_size=5)
    with pytest.raises(ReconciliationError, match="totalSize"):
        fetch_groups(post, "2026-07-01", "2026-07-31")


def test_missing_required_group_field_raises():
    raw = _raw_group("S1")
    del raw["accountNetIncome"]
    post, _ = _fake_post([[raw]])
    with pytest.raises(ReconciliationError, match="缺字段"):
        fetch_groups(post, "2026-07-01", "2026-07-31")


def test_missing_total_page_raises():
    def post(path, body):
        return {"groupVoList": [], "totalSize": 0}

    with pytest.raises(ReconciliationError, match="totalPage"):
        fetch_groups(post, "2026-07-01", "2026-07-31")


def test_duplicate_group_id_across_pages_raises():
    page2 = [_raw_group("S1"), _raw_group("S2")]
    post, _ = _fake_post([[_raw_group("S1")], page2], total_page=2, total_size=3)
    with pytest.raises(ReconciliationError, match="重复 groupId"):
        fetch_groups(post, "2026-07-01", "2026-07-31", page_size=1)


# ---------------------------------------------------------------- 守恒 / OA 归一


def test_every_source_record_has_exactly_one_terminal_state():
    groups = [make_group(sid="S1"), make_group(sid="S2", gid="G2", store="Store2-US", account="AMZAcct2US")]
    txts = [make_txt(sid="S1"), make_txt(sid="S3", rel="运营B/S3.txt", account="AMZAcct3US")]
    oas = [make_oa(approval="A1"), make_oa(approval="A2", account="AMZAcct9US", amount=9.0)]
    result = run(groups, txts, oas)
    result.assert_conservation()
    assert result.source_totals() == {"group": 2, "txt": 2, "oa": 2}
    counts = result.source_counts()
    assert sum(counts["group"].values()) == 2
    assert sum(counts["txt"].values()) == 2
    assert sum(counts["oa"].values()) == 2


def test_oa_frame_selects_amazon_month_and_keeps_other_period_out():
    import pandas as pd

    frame = pd.DataFrame(
        [
            {
                "选择平台": "亚马逊",
                "账期日期": pd.Timestamp("2026-07-10"),
                "销售账户_展开": "AMZAcctUS",
                "账期收款额": 100.0,
                "销售额": 1000.0,
                "币种": "美元(USD)",
                "审批编号": "A1",
                "提交分类": "正常",
            },
            {
                "选择平台": "亚马逊",
                "账期日期": pd.Timestamp("2026-06-10"),
                "销售账户_展开": "AMZAcctUS",
                "账期收款额": 50.0,
                "销售额": 500.0,
                "币种": "美元(USD)",
                "审批编号": "A2",
                "提交分类": "迟交",
            },
            {
                "选择平台": "新平台",
                "账期日期": pd.Timestamp("2026-07-10"),
                "销售账户_展开": "WFUS",
                "账期收款额": 20.0,
                "销售额": 200.0,
                "币种": "美元(USD)",
                "审批编号": "A3",
                "提交分类": "正常",
            },
        ]
    )
    facts, out, problems = oa_facts_from_frame(frame, PERIOD, today=TODAY)
    assert len(facts) == 1
    assert facts[0].currency == "USD"
    assert {o["reason"] for o in out} == {"other_period", "not_amazon"}
    assert problems == []


def test_oa_currency_alias_mxi_is_normalized_not_guessed_elsewhere():
    import pandas as pd

    frame = pd.DataFrame(
        [
            {
                "选择平台": "亚马逊",
                "账期日期": pd.Timestamp("2026-07-10"),
                "销售账户_展开": "AMZAcctMX",
                "账期收款额": 10.0,
                "销售额": 100.0,
                "币种": "墨西哥比索(MXI)",
                "审批编号": "A1",
                "提交分类": "正常",
            }
        ]
    )
    facts, _, _ = oa_facts_from_frame(frame, PERIOD, today=TODAY)
    assert facts[0].currency == "MXN"


# ---------------------------------------------------------------- E1 接入


class _LedgerRec:
    def __init__(self, rel, state="used", **kw):
        self.rel = rel
        self.state = state
        self.bucket = "账期20260704-20260803"
        self.settlement_id = kw.get("settlement_id")
        self.account = kw.get("account")
        self.sha256 = kw.get("sha256")
        self.schema = kw.get("schema", "v2")
        self.reason = kw.get("reason")
        self.is_candidate = True


class _Ledger:
    def __init__(self, records):
        self.records = records


def test_txt_facts_from_read_uses_e1_result_and_inventory():
    import pandas as pd

    df = pd.DataFrame(
        [
            {"文件名": "AMZAcctUS-7.10.txt", "子文件夹名": "运营A", "settlement-id": "S1",
             "currency": "USD", "amount": 60.0, "total-amount": 100.0,
             "settlement-end-date": "2026-07-10 00:00:00 UTC", "deposit-date": "2026-07-12 00:00:00 UTC"},
            {"文件名": "AMZAcctUS-7.10.txt", "子文件夹名": "运营A", "settlement-id": "S1",
             "currency": "USD", "amount": 40.0, "total-amount": float("nan"),
             "settlement-end-date": "2026-07-10 00:00:00 UTC", "deposit-date": "2026-07-12 00:00:00 UTC"},
        ]
    )
    ledger = _Ledger(
        [
            _LedgerRec("运营A/AMZAcctUS-7.10.txt", settlement_id="S1", account="AMZAcctUS", sha256="a" * 64),
            _LedgerRec("运营A/AMZBad.txt", state="failed", reason="EMPTY-FILE"),
        ]
    )
    facts, inventory = txt_facts_from_read(df, ledger)
    assert len(facts) == 1
    assert facts[0].header_total == Decimal("100")
    assert facts[0].detail_net == Decimal("100")
    assert facts[0].end_date == date(2026, 7, 10)
    assert inventory == [
        {"rel": "运营A/AMZBad.txt", "bucket": "账期20260704-20260803", "state": "failed",
         "reason": "EMPTY-FILE", "settlement_id": None, "account": None, "sha256": None}
    ]


def test_store_account_map_reads_channel_snapshot_shape():
    header = ["渠道", "渠道账号", "渠道账号别名", "赛狐店铺"]
    rows = [["Amazon", "AMZStruseryUS", "", "FZH深圳-Strusery-US"], ["Amazon", "", "", "空店铺"]]
    assert store_account_map(header, rows) == {"FZH深圳-Strusery-US": "AMZStruseryUS"}
