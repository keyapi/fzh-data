"""统一履约查询入口 CLI（蓝图 §9 多态输出：JSON / 控制台 / Excel）。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import item_shipment_status as iss

from . import codes as codes_mod
from . import render
from .assemble import run_query
from .report import build_partitions, build_summary

OUT_DIR = iss.DATA_DIR


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="fulfillment_query",
        description="统一履约查询：多个客户码/EN 物料码 → 销售订单→生产→销售出库（阶段 0–3 + 异常/下一行动）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n"
               "  %(prog)s --codes CENKZ1325-Yellow-138\n"
               "  %(prog)s --codes \"CENKZ1325-Yellow-138,PK#KS0001-DM-140-YELLOW\"\n"
               "  %(prog)s --customer-code X --json\n"
               "  %(prog)s --item \"PK#KS0001-DM-140-YELLOW\" --legacy-sheets",
    )
    parser.add_argument("--codes", help="输入，逗号/分号分隔（客户码或 EN 物料码，自动判型）")
    parser.add_argument("--customer-code", help="单个客户物料号（兼容旧用法）")
    parser.add_argument("--item", help="EN 物料编码，逗号分隔（兼容旧用法）")
    parser.add_argument("--entity-type", choices=["auto", "customer_code", "item_code"],
                        default="auto", help="强制输入类型（默认自动判型）")
    parser.add_argument("--test", action="store_true", help="使用测试系统 (ensh.vilavi.cn)")
    parser.add_argument("--output", "-o", help="输出路径 (默认 EN_API/out/ 下)")
    parser.add_argument("--no-excel", action="store_true", help="只打控制台，不写文件")
    parser.add_argument("--json", action="store_true", help="额外/仅输出 JSON（配 --no-excel 时仅 JSON）")
    parser.add_argument("--legacy-sheets", action="store_true", help="Excel 出旧 3 Sheet（兼容 item_shipment_status）")
    parser.add_argument("--env-file", help="指定 .env 路径 (默认自动探测)")
    parser.add_argument("--lead-months", type=int, default=3, help="交付约定: 下单 + N 月 (默认 3)")
    parser.add_argument("--sleep", type=float, default=0.15, help="单文档请求间隔秒数 (默认 0.15)")
    parser.add_argument("--assert-fixture", action="store_true", help="跑 CENKZ1325-Yellow-138 断言 (回归自检)")
    args = parser.parse_args(argv)

    raw = ",".join(x for x in (args.codes, args.customer_code, args.item) if x)
    if not raw.strip():
        parser.error("至少给一个输入：--codes / --customer-code / --item")
    entities = codes_mod.parse_inputs(raw, default_kind=args.entity_type)

    env = "test" if args.test else "prod"
    key, secret = iss.load_credentials(env, iss.resolve_env_files(args.env_file))
    if not key or not secret or "your_" in key:
        print("✗ API 凭证未配置。请先检查 EN_API/.env 文件", file=sys.stderr)
        return 1
    base_url = iss.ENV_URLS[env]

    try:
        result = run_query(entities, base_url, key, secret,
                           sleep_s=args.sleep, lead_months=args.lead_months)
    except iss.QueryError as e:
        print(f"✗ 查询中断 (部分结果不可信): {e}", file=sys.stderr)
        return 1

    result.summary = build_summary(result)
    result.partitions = build_partitions(result)

    if result.empty:
        print("\n无匹配的销售订单。")
        return 0

    render.render_console(result)

    if args.assert_fixture:
        if result.inputs_text.strip() != iss.FIXTURE["customer_code"]:
            print(f"\n⚠ --assert-fixture 只对 --codes {iss.FIXTURE['customer_code']} 有效。",
                  file=sys.stderr)
            return 2
        return 0 if iss.assert_fixture(result.ctx) else 1

    wrote = []
    if args.json or not args.no_excel:
        out_json = (Path(args.output) if args.output and args.output.endswith(".json") else
                    (OUT_DIR / f"{iss.slugify(result.inputs_text)}_履约.json"))
        render.write_json(result, out_json)
        wrote.append(str(out_json))
    if not args.no_excel and not args.json:
        out_xlsx = Path(args.output) if args.output else None
        wb = render.build_workbook(result, legacy=args.legacy_sheets)
        if out_xlsx is None:
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            out_xlsx = render.default_output_path(result, OUT_DIR, args.legacy_sheets)
        out_xlsx.parent.mkdir(parents=True, exist_ok=True)
        wb.save(str(out_xlsx))
        wrote.append(str(out_xlsx))
    for w in wrote:
        print(f"\nOK: {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
