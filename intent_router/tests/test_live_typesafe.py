"""opt-in 真实调用：唯一真正测量路由准确率的地方。

默认跳过。开启：设 INTENT_ROUTER_LIVE=1 且环境里能取到 TYPESAFE_API_KEY。

这里的「期望模块」是根据 AGENTS.md 模块索引人工标注的。跑出来的准确率就是调
--min-confidence 与 catalog 里 exclusions 文案的依据。

输出刻意只用 ASCII：Windows 控制台是 cp936，打印中文可能直接 UnicodeEncodeError。
"""

from __future__ import annotations

import os

import pytest

from intent_router.catalog import load_catalog
from intent_router.router import GATE_NONE, GATE_OK, resolve_api_key, route

pytestmark = pytest.mark.skipif(
    os.environ.get("INTENT_ROUTER_LIVE") != "1",
    reason="真实调用 TypeSafe，需要 INTENT_ROUTER_LIVE=1",
)

CATALOG = load_catalog()

# 人工标注：中文请求 → 期望模块。取自各模块 SKILL.md 的触发词与 AGENTS.md 的一句话。
LABELED = [
    ("帮我把 BOM 成本表导进赛狐的采购成本", "item-cost"),
    ("导入库存初始值", "stock-init"),
    ("尾程打单出运单标签", "sellfox-shipping"),
    ("统计一下上个月的尾程异常", "parcel-track"),
    ("把商品重尺填一下，包装长宽高和单箱重量", "item-weight"),
    ("生成四级分类导入文件", "category"),
    ("其他出库清零库存", "other-outbound"),
    ("查一下 FedEx 的轨迹和异常报表", "fedex-track"),
    ("帮我把赛狐图片链接更新到物料组主图", "en-image-upload"),
    ("通途订单特殊规则 1.7.0 本地审计", "tongtool-order-cost"),
]

# 两条对照样例：模糊到无法路由，以及明确不属于本仓库
VAGUE_REQUEST = "那个东西弄一下"
OUT_OF_SCOPE_REQUEST = "帮我订一张去上海的机票"


def _require_key() -> str:
    key = resolve_api_key()
    if not key:
        pytest.skip("环境里没有 TYPESAFE_API_KEY")
    return key


@pytest.fixture(scope="module")
def api_key() -> str:
    return _require_key()


def _run(request: str, api_key: str, *, min_confidence: float = 0.5):
    return route(request, catalog=CATALOG, api_key=api_key, min_confidence=min_confidence)


@pytest.mark.parametrize(("request_text", "expected"), LABELED, ids=[item[1] for item in LABELED])
def test_labeled_request_routes_to_expected_module(api_key, request_text, expected):
    result = _run(request_text, api_key)
    print(
        f"\n  expected={expected} got={result.skill} gate={result.gate} "
        f"confidence={result.confidence:.2f} ambiguity={result.ambiguity:.2f} "
        f"tokens={result.usage.get('input_tokens')}"
    )
    assert result.gate == GATE_OK, f"期望命中 {expected}，实际 gate={result.gate}（{result.reason}）"
    assert result.skill == expected


def test_vague_request_is_not_confidently_routed(api_key):
    result = _run(VAGUE_REQUEST, api_key)
    print(f"\n  gate={result.gate} skill={result.skill} confidence={result.confidence:.2f}")
    assert result.gate != GATE_OK


def test_out_of_scope_request_falls_to_none(api_key):
    result = _run(OUT_OF_SCOPE_REQUEST, api_key)
    print(f"\n  gate={result.gate} skill={result.skill} confidence={result.confidence:.2f}")
    assert result.gate == GATE_NONE
