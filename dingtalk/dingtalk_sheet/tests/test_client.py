# -*- coding: utf-8 -*-
"""dingtalk_sheet 口径单测 —— 不连钉钉。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import client as dc  # noqa: E402


def test_parse_base_id_from_alidocs_url():
    url = "https://alidocs.dingtalk.com/i/nodes/QOG9lyrgJPjjrl10uXDDw7RwWzN67Mw4?utm_scene=person_space"
    assert dc.parse_base_id(url) == "QOG9lyrgJPjjrl10uXDDw7RwWzN67Mw4"


def test_parse_base_id_from_team_space_url():
    url = "https://alidocs.dingtalk.com/i/nodes/qXomz1wAyjKVXd1x2xoxV3Y9pRBx5OrE?utm_scene=team_space"
    assert dc.parse_base_id(url) == "qXomz1wAyjKVXd1x2xoxV3Y9pRBx5OrE"


def test_parse_base_id_accepts_bare_id():
    assert dc.parse_base_id("abc123") == "abc123"
    assert dc.parse_base_id("  abc123?x=1  ") == "abc123"


def test_parse_base_id_rejects_empty():
    with pytest.raises(ValueError):
        dc.parse_base_id("")


def test_sheet_id_by_name_matches_and_trims():
    sheets = [{"id": "s1", "name": "物流信息表"}, {"id": "s2", "name": "2026年度订单明细"}]
    assert dc.sheet_id_by_name(sheets, "物流信息表") == "s1"
    assert dc.sheet_id_by_name(sheets, " 2026年度订单明细 ") == "s2"


def test_sheet_id_by_name_lists_available_on_miss():
    sheets = [{"id": "s1", "name": "物流信息表"}]
    with pytest.raises(KeyError) as e:
        dc.sheet_id_by_name(sheets, "不存在")
    assert "物流信息表" in str(e.value)


def test_load_env_prefers_explicit_path(tmp_path):
    env = tmp_path / ".env"
    env.write_text("DINGTALK_CLIENT_ID=ck\nDINGTALK_CLIENT_SECRET=cs\n", encoding="utf-8")
    got = dc.load_env(env)
    assert got["DINGTALK_CLIENT_ID"] == "ck"
    assert got["DINGTALK_CLIENT_SECRET"] == "cs"


def test_get_access_token_raises_without_credentials(monkeypatch):
    monkeypatch.delenv("DINGTALK_CLIENT_ID", raising=False)
    monkeypatch.delenv("DINGTALK_APP_KEY", raising=False)
    with pytest.raises(RuntimeError) as e:
        dc.get_access_token({})
    assert "DINGTALK_CLIENT_ID" in str(e.value)


# ── 分页与区域上限 ────────────────────────────────────────────────────────
# 两个实测坑：
#  1) 单次 range 最多 30000 个单元格，超了报
#     400 "This operation can only be performed on a range with at most 30000 cells"
#  2) **接口会用空行把请求区域补满** —— 读 A701:E1200 会稳稳返回 500 行空行。
#     所以「返回行数 < chunk 就结束」这种翻页条件永远不会触发，
#     会把空行当数据一路读下去（曾因此误报某表有 4 万行，实际 380 行）。

def test_col_letter():
    assert dc.col_letter(1) == "A"
    assert dc.col_letter(5) == "E"
    assert dc.col_letter(26) == "Z"
    assert dc.col_letter(27) == "AA"


def test_cell_limit_constant():
    assert dc.CELL_LIMIT == 30000


def test_chunk_rows_respects_cell_limit():
    for n_cols in (1, 5, 16, 20, 50):
        rows = dc.chunk_rows_for(n_cols)
        assert rows >= 1
        assert rows * n_cols <= dc.CELL_LIMIT, f"{n_cols} 列时 {rows} 行会超 30000 单元格"


def test_read_sheet_all_stops_at_blank_block(monkeypatch):
    """核心回归：数据只有 3 行，后面全是补齐的空行 —— 必须只返回 3 行。"""
    served = []

    def fake_http(method, url, token=None, body=None, timeout=60):
        start = int(url.split("/ranges/A")[1].split("%3A")[0])
        if start == 1:
            rows = [["a"], ["b"], ["c"]] + [[""] for _ in range(2)]
        else:
            rows = [[""] for _ in range(5)]   # 接口补齐的空行
        served.append(start)
        return 200, {"displayValues": rows}

    monkeypatch.setattr(dc, "http_json", fake_http)
    got = dc.read_sheet_all("base", "sid", "op", "tok", n_cols=1, chunk_rows=5)
    assert got == [["a"], ["b"], ["c"]], f"应剔除补齐空行，实得 {got}"
    assert served == [1, 6], "遇到整块全空就该停，不该继续翻页"


def test_read_sheet_all_keeps_interior_blank_rows(monkeypatch):
    """中间的空行是真实数据（留白/分段），不能当结束信号。"""
    def fake_http(method, url, token=None, body=None, timeout=60):
        start = int(url.split("/ranges/A")[1].split("%3A")[0])
        if start == 1:
            return 200, {"displayValues": [["a"], [""], ["c"], [""], [""]]}
        return 200, {"displayValues": [[""] for _ in range(5)]}

    monkeypatch.setattr(dc, "http_json", fake_http)
    got = dc.read_sheet_all("base", "sid", "op", "tok", n_cols=1, chunk_rows=5)
    assert got == [["a"], [""], ["c"]], got


def test_read_sheet_all_trims_trailing_blanks_on_last_real_chunk(monkeypatch):
    def fake_http(method, url, token=None, body=None, timeout=60):
        start = int(url.split("/ranges/A")[1].split("%3A")[0])
        if start == 1:
            return 200, {"displayValues": [["a"], ["b"]], "x": 1}
        return 200, {"displayValues": [[""] for _ in range(5)]}

    monkeypatch.setattr(dc, "http_json", fake_http)
    got = dc.read_sheet_all("base", "sid", "op", "tok", n_cols=1, chunk_rows=5)
    assert got == [["a"], ["b"]]


def test_read_sheet_all_raises_on_permission_error(monkeypatch):
    def fake_http(method, url, token=None, body=None, timeout=60):
        return 403, {"code": "forbidden.accessDenied", "message": "The operator has no permission."}

    monkeypatch.setattr(dc, "http_json", fake_http)
    with pytest.raises(RuntimeError) as e:
        dc.read_sheet_all("base", "sid", "op", "tok", n_cols=1)
    assert "no permission" in str(e.value)


# ── 5xx 瞬时故障要重试 ────────────────────────────────────────────────────
# 实测：整表读取中途会偶发 503 ServiceUnavailable（"temporary failure of the server"）。
# 把它当致命错误会让长扫描整段失败，必须退避重试；4xx 是确定性的，不该重试。

def test_http_json_retries_5xx_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_raw(method, url, headers, data, timeout):
        calls["n"] += 1
        if calls["n"] < 3:
            return 503, '{"code":"ServiceUnavailable"}'
        return 200, '{"ok":true}'

    monkeypatch.setattr(dc, "_raw_request", fake_raw)
    monkeypatch.setattr(dc.time, "sleep", lambda s: None)
    st, payload = dc.http_json("GET", "https://x")
    assert st == 200 and payload == {"ok": True}
    assert calls["n"] == 3, "应在第 3 次成功前重试 2 次"


def test_http_json_does_not_retry_4xx(monkeypatch):
    calls = {"n": 0}

    def fake_raw(method, url, headers, data, timeout):
        calls["n"] += 1
        return 403, '{"code":"forbidden.accessDenied"}'

    monkeypatch.setattr(dc, "_raw_request", fake_raw)
    monkeypatch.setattr(dc.time, "sleep", lambda s: None)
    st, payload = dc.http_json("GET", "https://x")
    assert st == 403
    assert calls["n"] == 1, "4xx 是确定性错误，不该重试"


def test_http_json_gives_up_after_max_retries(monkeypatch):
    calls = {"n": 0}

    def fake_raw(method, url, headers, data, timeout):
        calls["n"] += 1
        return 503, "{}"

    monkeypatch.setattr(dc, "_raw_request", fake_raw)
    monkeypatch.setattr(dc.time, "sleep", lambda s: None)
    st, _ = dc.http_json("GET", "https://x", retries=3)
    assert st == 503
    assert calls["n"] == 3, "最多试 retries 次"


def test_http_json_retries_network_errors(monkeypatch):
    calls = {"n": 0}

    def fake_raw(method, url, headers, data, timeout):
        calls["n"] += 1
        if calls["n"] < 2:
            raise OSError("connection reset")
        return 200, '{"ok":1}'

    monkeypatch.setattr(dc, "_raw_request", fake_raw)
    monkeypatch.setattr(dc.time, "sleep", lambda s: None)
    st, payload = dc.http_json("GET", "https://x")
    assert st == 200 and payload == {"ok": 1}


# 实测：同一个请求会**随机**返回 503 或
# 404 {"code":"invalidRequest.resource.notFound","message":"uuid not exist"}。
# 后者看着像"资源不存在"，其实是瞬时抖动 —— 不重试就会把能读通的表当读不通。

def test_is_retryable_5xx_and_transient_404():
    assert dc.is_retryable(503, {}) is True
    assert dc.is_retryable(500, {}) is True
    assert dc.is_retryable(404, {"code": "invalidRequest.resource.notFound",
                                 "message": "uuid not exist"}) is True


def test_is_retryable_keeps_deterministic_errors_non_retryable():
    assert dc.is_retryable(403, {"code": "forbidden.accessDenied"}) is False
    assert dc.is_retryable(404, {"code": "InvalidAction.NotFound"}) is False
    assert dc.is_retryable(400, {"code": "paramError-operatorId"}) is False
    assert dc.is_retryable(200, {}) is False


def test_http_json_retries_transient_uuid_not_exist(monkeypatch):
    calls = {"n": 0}

    def fake_raw(method, url, headers, data, timeout):
        calls["n"] += 1
        if calls["n"] < 3:
            return 404, '{"code":"invalidRequest.resource.notFound","message":"uuid not exist"}'
        return 200, '{"displayValues":[["a"]]}'

    monkeypatch.setattr(dc, "_raw_request", fake_raw)
    monkeypatch.setattr(dc.time, "sleep", lambda s: None)
    st, payload = dc.http_json("GET", "https://x")
    assert st == 200
    assert calls["n"] == 3

