"""Prepare private, traceable workbook tables from validation snapshots."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from sellfox_settlement.validation_paths import private_output


def load(root, name):
    return json.loads((root / name).read_text(encoding='utf-8'))


def table(name, headers, rows, note):
    return {'name': name, 'headers': headers, 'rows': rows, 'note': note}


def build_tables(root):
    monthly = load(root, 'monthly_validation.json')
    accounts = load(root, 'account_validation.json')
    costs = load(root, 'cost/cost_coverage_details.json')
    settlements = load(root, 'settlement/settlement_groups_scoped.json')
    account_by_file = {Path(f['file']).name: f for f in accounts['files']}
    sheets = []
    summary = monthly['summary']
    coverage = [['SUMMARY', k, json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else v, '', '', '', '', '']
                for k, v in summary.items()]
    coverage += [[p.get('source_file', p['key']), p['status'], p.get('input_rows', 0),
                  p.get('normalized_rows', 0), p.get('rejected_rows', 0), p.get('currency', ''),
                  p.get('currency_evidence', {}).get('kind', ''), '|'.join(p.get('metadata_issues', []))]
                 for p in monthly['pairs']]
    sheets.append(table('文件覆盖', ['文件/范围', '状态/指标', '输入/指标值', '规范化', '拒绝', '币种', '币种证据', '异常'],
                        coverage, '2026-08 技术底稿；财务口径待确认。源文件与全部明细保留在同目录 JSON，未修改原始文件。'))
    candidate_headers = ['文件', '账号候选', '币种', '状态', '行数', '收入A', '退款A带符号', '净额A',
                         '收入B', '退款B带符号', '净额B', '促销税带符号', 'B加促销税诊断']
    candidate_keys = ['income_candidate_a', 'refund_candidate_a_signed', 'net_candidate_a',
                      'income_candidate_b', 'refund_candidate_b_signed', 'net_candidate_b',
                      'promotional_tax_signed', 'net_b_all_tax_diagnostic']
    candidates = [[c['source_file'], account_by_file.get(c['source_file'], {}).get('account_candidate', ''),
                   c['currency'], c['transaction_status'], c['input_rows'], *[c.get(k, '') for k in candidate_keys]]
                  for c in monthly['candidate_groups']]
    sheets.append(table('收入候选', candidate_headers, candidates,
                        'A/B复现PR284候选公式，金额以精确十进制文本保存；B加促销税仅诊断。未分摊Refund.other；不能用作最终申报数。'))
    subjects = [[p['source_file'], p['currency'], key, str(value)] for p in monthly['pairs']
                if 'csv_controls' in p for key, value in p['csv_controls']['controls'].items()]
    sheets.append(table('Amazon科目', ['文件', '币种', '原始投影科目', '金额精确文本'], subjects,
                        '包含Released和Deferred。原始科目保持不变；解释桥不回写收入候选。跨币种不求和。'))
    checks = [[p['source_file'], p['currency'], c['control'], c['status'], c['csv_value'], c['pdf_value'],
               c['difference'], '|'.join(c['missing_components'])] for p in monthly['pairs'] for c in p.get('comparisons', [])]
    checks += [[p['source_file'], p['currency'], 'Refund.other解释桥', p['refund_other_bridge']['status'],
                p['refund_other_bridge']['csv_refund_other'],
                json.dumps(p['refund_other_bridge']['pdf_minus_csv_deltas'], ensure_ascii=False),
                p['refund_other_bridge']['residual'], '|'.join(p['refund_other_bridge']['missing_components'])]
               for p in monthly['pairs'] if 'refund_other_bridge' in p]
    sheets.append(table('PDF对账', ['文件', '币种', '科目', '状态', 'CSV值', 'PDF值/解释分量', '差异/残差', '缺科目'], checks,
                        'complete/partial/difference分别保留。5项PDF空值不能视作零；18项差异仅在文件汇总层解释。逐行证据见monthly_validation.json。'))
    bridge_keys = ['storeName', 'currency', 'settlementId', 'traceId', 'groupStartStr', 'groupEndStr',
                   'beginningBalance', 'endingBalance', 'accountIncome', 'accountRefund', 'accountExpenditure',
                   'accountNetIncome', 'transferAmount', 'arrivalAmount', 'arrivalStatusStr']
    sheets.append(table('结算银行桥', bridge_keys, [[str(s.get(k, '')) for k in bridge_keys] for s in settlements],
                        '8-9月V2原始结算组。arrivalAmount/状态属于平台记录，不能证明银行实际到账；本批8月Amazon银行流水缺输入。'))
    counts = Counter((c['source_file'], c['fulfillment'], c['status']) for c in costs)
    cost_rows = [[file, '', '', fulfillment, status, count, '', ''] for (file, fulfillment, status), count in sorted(counts.items())]
    cost_rows += [[c['source_file'], c['source_line'], c['order_id'], c['fulfillment'], c['status'], 1,
                   c['sku'], '|'.join(c.get('en_order_names', []))] for c in costs
                  if c['status'] not in {'matched', 'excluded_non_order_or_missing_id'}]
    sheets.append(table('成本覆盖', ['文件', '原始行', '订单号', '履约', '连接状态', '行数', 'SKU', 'EN订单证据'], cost_rows,
                        '上半部全部11580行按文件/状态计数；下半部147条主连接异常重复展示供追溯。9969仅global订单+SKU候选，账号映射/数量/历史BOM待确认，不计算最终成本。'))
    account_rows = [[Path(f['file']).name, f.get('account_candidate', ''), f['match']['status'],
                     f['site_evidence'].get('site', ''), f.get('en_exists', False), f.get('shop_match_status', ''),
                     f.get('pdf_legal_name', ''), f.get('legal_entity_status', '')] for f in accounts['files']]
    sheets.append(table('账号法人', ['文件', '标准账号候选', '匹配状态', '站点', 'EN存在', '赛狐身份连接', 'PDF法定名称原文', '法人归属状态'],
                        account_rows, 'PDF法定名称为证据原文；未经财务确认，不据品牌或文件名指定中国申报主体。'))
    pending = [['银行实际到账', '缺输入', '提供8月Amazon实际流水；含银行/收款平台reference。'],
               ['财务F01-F20', '待ZJ/税务顾问', '按PR284填写；候选A/B、Deferred、税、汇率、法人不自行拍板。'],
               ['本币V2明细', '见settlement_validation_summary.json', '按原币限店、UTC缓冲及站点8月过滤；完整性与差异保留。'],
               ['历史成本', '缺历史快照', '当前10月BOM不能代替8月；数量/组件/退款成本先确认证据。'],
               ['订单账号映射', '候选连接', 'CSV标准账号到通途原生account未全部确认；跨账号重复订单号必须保留。']]
    pending += [[p['source_file'], c['status'], c['control'] + ': ' + c['difference']]
                for p in monthly['pairs'] for c in p.get('comparisons', []) if c['status'] != 'complete']
    pending += [[f['source_file'], 'CSV失败', f['reason']] for f in monthly['csv_validation']['file_errors']]
    sheets.append(table('待确认与异常', ['事项/文件', '状态', '原因/下一证据'], pending,
                        '技术通过仅指已列明的验证；缺输入和财务决策保持显式待确认。未匹配明细没有删除。'))
    return {'month': summary['month'], 'sheets': sheets, 'source_manifest': monthly['source_manifest']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reports', type=Path, required=True)
    args = parser.parse_args()
    root = private_output(args.reports)
    result = build_tables(root)
    (root / 'workbook_tables.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({s['name']: len(s['rows']) for s in result['sheets']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
