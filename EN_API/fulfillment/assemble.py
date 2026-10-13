"""组装层：逐输入查询 → 并集 → 事实层 → 阶段/数量/异常 → 统一结果（蓝图 §2.2 / §9）。

复用引擎 `item_shipment_status` 的查询函数（不重写 ERPNext 访问）；本层只做多输入编排、
逐输入来源标注，以及阶段/数量/异常层的叠加。并集语义严格复刻引擎 `build_context`：
客户码模式先按客户码找单，再在**同一客户范围内**按订单行物料码补一轮。
"""
from __future__ import annotations

import contextlib
import io

import item_shipment_status as iss

from . import codes as codes_mod
from . import kit as kit_mod
from . import quantities as qty_mod
from . import rules as rules_mod
from . import stages as stages_mod
from .model import FulfillmentLine, FulfillmentQueryResult, InputEntity


def _mute(enabled):
    return contextlib.redirect_stdout(io.StringIO()) if enabled else contextlib.nullcontext()


def _dedupe_lines(lines):
    seen, out = set(), []
    for r in lines:
        key = (r["so"], r["line_id"])
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def run_query(entities, base_url, key, secret, sleep_s=0.15, lead_months=3,
              stall_days=rules_mod.DEFAULT_STALL_DAYS, scope="input_items",
              quiet=True) -> FulfillmentQueryResult:
    if isinstance(entities, str):
        entities = codes_mod.parse_inputs(entities)
    elif isinstance(entities, InputEntity):
        entities = [entities]
    entities = list(entities)
    result = FulfillmentQueryResult(inputs_text=", ".join(e.raw for e in entities))

    item_inputs = [e.raw for e in entities if e.kind == "item_code"]
    cust_inputs = [e.raw for e in entities if e.kind == "customer_code"]

    # ── 1. 逐输入发现 SO（客户码只找 SO，物料并集补轮在第 2 步做）──
    so_raw, cust_sos = [], {}
    with _mute(quiet):
        for e in entities:
            if e.kind == "item_code":
                so_raw += iss.find_sales_orders_by_items([e.raw], base_url, key, secret)
            else:
                rows = iss.find_sales_orders_by_customer_code(e.raw, base_url, key, secret)
                so_raw += rows
                cust_sos[e.raw] = iss.dedupe_by(rows, "name")
    so_list = iss.dedupe_by(so_raw, "name")
    if not so_list:
        result.empty = True
        result.resolutions = codes_mod.resolve_inputs(entities, [], {})
        return result
    so_names_all = [s["name"] for s in so_list]

    # ── 2. 订单行（逐输入 + 复刻引擎客户码模式的同客户内物料并集补轮）──
    lines_raw = []
    with _mute(quiet):
        if item_inputs:
            lines_raw += iss.fetch_so_lines(so_names_all, item_inputs, None,
                                            base_url, key, secret, sleep_s)
        for code in cust_inputs:
            lines_raw += iss.fetch_so_lines(so_names_all, [], code,
                                            base_url, key, secret, sleep_s)
    so_rows = _dedupe_lines(lines_raw)

    for code in cust_inputs:
        items_c = sorted({r["item_code"] for r in so_rows
                          if r["item_code"] and iss.code_in(r.get("customer_item_code"), [code])})
        if not items_c:
            continue
        customers = {s["customer"] for s in cust_sos.get(code, []) if s.get("customer")}
        have = {r["so"] for r in so_rows}
        with _mute(quiet):
            extra = iss.dedupe_by(
                iss.find_sales_orders_by_items(items_c, base_url, key, secret, customers), "name")
            extra = [x for x in extra if x["name"] not in have]
            if extra:
                so_rows += _dedupe_lines(iss.fetch_so_lines([x["name"] for x in extra], items_c,
                                                            code, base_url, key, secret, sleep_s))
    so_rows = _dedupe_lines(so_rows)
    if not so_rows:
        result.empty = True
        result.resolutions = codes_mod.resolve_inputs(entities, [], {})
        return result

    item_codes = sorted({r["item_code"] for r in so_rows if r["item_code"]})
    so_names = sorted({r["so"] for r in so_rows})

    # ── 3. 物料主档 / 客户码解析 ──
    master_by_code = {}
    with _mute(quiet):
        item_master = iss.fetch_item_master(item_codes, base_url, key, secret)
        master_items = []
        for code in cust_inputs:
            items = iss.resolve_customer_code(code, base_url, key, secret)
            master_by_code[code] = items
            master_items += items
        master_items = iss.dedupe_by(master_items, "name")
        if not master_items:
            master_items = [{"name": c, "item_name": item_master.get(c, {}).get("item_name"),
                             "item_group": item_master.get(c, {}).get("item_group")}
                            for c in item_codes]
        master_text = ", ".join(m["name"] for m in master_items)

    # ── 4. 出库 / 工单 / 工序卡 / 生产计划 ──
    # 出库单只查一次：DN 必须按 item_code 匹配（旧单 customer_item_code 为 NULL）；
    # 单一客户码输入时带上客户码，与引擎口径一致。**不要**为"多一层保险"重复调用 ——
    # ERPNext 对突发请求限流，多一轮请求会让后续查询返回 403。
    dn_customer = cust_inputs[0] if (len(cust_inputs) == 1 and not item_inputs) else None
    with _mute(quiet):
        dn_rows = iss.fetch_delivery_notes(so_names, item_codes, dn_customer,
                                           base_url, key, secret, sleep_s)
        wos = iss.fetch_work_order_details(iss.fetch_work_orders(item_codes, base_url, key, secret),
                                           base_url, key, secret, sleep_s)
        jc_map = iss.jobcards_by_wo(iss.fetch_job_cards([w["name"] for w in wos],
                                                        base_url, key, secret))
        pp_rows = iss.fetch_production_plans(so_names, item_codes, base_url, key, secret, sleep_s)

    # ── 5. 每行补 出库/工单/生产计划（与引擎共用 enrich_so_rows，避免口径分叉）──
    iss.enrich_so_rows(so_rows, dn_rows, pp_rows, wos, jc_map, master_text)

    # ── 6. 异常判定（复用引擎口径）──
    ctx = {"empty": False, "so_rows": so_rows, "dn_rows": dn_rows, "wos": wos, "jc_map": jc_map,
           "pp_rows": pp_rows, "item_master": item_master, "item_codes": item_codes,
           "master_items": master_items, "master_text": master_text,
           "customer_code": cust_inputs[0] if len(cust_inputs) == 1 else None,
           "lead_months": lead_months, "dup_window": iss.DUP_WINDOW_DAYS}
    iss.classify_anomalies(ctx)

    # ── 7. 逐输入命中/未命中 ──
    result.resolutions = codes_mod.resolve_inputs(entities, so_rows, master_by_code)

    # ── 8. 异常 §8 结构 ──
    anomalies = rules_mod.build_anomalies(ctx, stall_days=stall_days)
    anom_by_so = {}
    for a in anomalies:
        if a.so:
            anom_by_so.setdefault(a.so, []).append(a)

    sources_by_line = {}
    for res in result.resolutions:
        for lid in res.hit_lines:
            sources_by_line.setdefault(lid, []).append(res.raw)

    # ── 9. 履约行（阶段 + 数量 + 异常）──
    for r in so_rows:
        result.lines.append(FulfillmentLine(
            so=r["so"], so_line_id=r["line_id"], item_code=r["item_code"],
            item_name=r.get("item_name"), customer=r.get("customer"),
            company=r.get("company"), so_status=r.get("so_status"),
            so_docstatus=r.get("so_docstatus"), delivery_date=r.get("delivery_date"),
            ordered_qty=r["qty"], shipped_qty=r["delivered_qty"], open_qty=r["open_qty"],
            draft_qty=r["draft_dn"], progress=r["progress"],
            quantities=qty_mod.quantity_ladder(r, jc_map),
            stage=stages_mod.resolve_stage(r, jc_map),
            anomalies=anom_by_so.get(r["so"], []),
            input_sources=sources_by_line.get(r["line_id"], []),
        ))

    result.anomalies = anomalies
    result.totals = ctx["totals"]
    result.ctx = ctx
    result.dn_rows, result.wos, result.jc_map = dn_rows, wos, jc_map
    result.pp_rows, result.item_master = pp_rows, item_master
    result.master_items = master_items

    # ── 10. 整单齐套（opt-in，蓝图 §7.2）──
    if scope == "full_order_kit":
        with _mute(quiet):
            kit_mod.evaluate_kit(result.lines, base_url, key, secret, sleep_s)
    return result
