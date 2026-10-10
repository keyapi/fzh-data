"""Coordinate-based, evidence-preserving Amazon monthly Summary PDF reader."""

from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal
from pathlib import Path


def _normal(text):
    return ' '.join(text.split()).casefold()


def parse_amount(text):
    """Require an integer or a valid grouped amount with exactly two decimal digits."""
    text = text.replace('\u00a0', '').replace('\u202f', '').replace(' ', '').replace('−', '-')
    if re.fullmatch(r'-?\d+', text):
        return Decimal(text)
    if re.fullmatch(r'-?(?:\d+|\d{1,3}(?:,\d{3})+)\.\d{2}', text):
        return Decimal(text.replace(',', ''))
    if re.fullmatch(r'-?(?:\d+|\d{1,3}(?:\.\d{3})+),\d{2}', text):
        return Decimal(text.replace('.', '').replace(',', '.'))
    raise ValueError(f'Unsupported or ambiguous PDF amount: {text!r}')


def _center(span):
    box = span['bbox']
    return (box[1] + box[3]) / 2


def parse_spans(spans, width, height):
    """Parse known monthly Summary layouts without trusting PDF content-stream order.

    Unknown label/amount rows, duplicate controls and ambiguous row alignment are
    retained as issues; absent controls are never implicitly zero-filled.
    Coordinates use PyMuPDF's unrotated page system, in points.
    """
    result = {'controls': {}, 'control_evidence': {}, 'issues': [], 'raw_rows': [],
              'currency': None, 'currency_evidence': {'kind': 'unknown'},
              'period_start': None, 'period_end': None, 'timezone': None,
              'period_start_time': None, 'period_end_time': None,
              'display_name': None, 'legal_name': None}
    issues = result['issues']
    numbers = []
    for s in spans:
        try:
            value = parse_amount(s['text'])
        except ValueError:
            continue
        numbers.append((s, value))
    # Metadata is confined to its own top band, so labels elsewhere cannot supply currency.
    currency_spans = [s for s in spans if .095 * height < s['bbox'][1] < .13 * height
                      and s['bbox'][0] > width / 2]
    currencies = []
    for s in currency_spans:
        match = re.search(r'\b(USD|CAD|EUR|GBP|PLN|MXN|SEK)\b', s['text'])
        if match:
            currencies.append((match[1], 'direct', s))
        elif re.search(r'\bEuro\b', s['text'], re.I):
            currencies.append(('EUR', 'direct', s))
        elif re.search(r'\bAlla belopp i kr\b', s['text']):
            currencies.append(('SEK', 'inferred', s))
    if len({c[0] for c in currencies}) == 1:
        currency, kind, evidence = currencies[0]
        result['currency'] = currency
        result['currency_evidence'] = {'kind': kind, 'text': evidence['text'],
                                       'bbox': evidence['bbox'],
                                       'reason': 'Swedish-language kr symbol' if kind == 'inferred'
                                       else 'Currency specified in PDF heading'}
    else:
        issues.append({'reason': 'missing_or_ambiguous_currency'})
    period = [s for s in spans if .095 * height < s['bbox'][1] < .13 * height
              and s['bbox'][0] < width / 2]
    months = dict(zip('Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split(), range(1, 13)))
    period_text = ' '.join(s['text'] for s in sorted(period, key=lambda s:s['bbox'][0]))
    result['period_evidence'] = {'text': period_text, 'spans': period}
    dates = list(re.finditer(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) (\d{1,2}), (\d{4})', period_text))
    if len(dates) == 2:
        from datetime import date
        for field, match in zip(('period_start', 'period_end'), dates):
            try:
                result[field] = date(int(match[3]), months[match[1]], int(match[2])).isoformat()
            except ValueError:
                issues.append({'reason': 'invalid_period_date', 'field': field})
            suffix = period_text[match.end():]
            time = re.match(r' (\d{2}:\d{2})(?=\s|$)', suffix)
            if time:
                result[field + '_time'] = time[1]
        tzs = re.findall(r'\b(?:GMT[+-]\d{1,2}|PDT|PST|CST|CEST|CET|BST|UTC)\b', period_text)
        if tzs and len(set(tzs)) == 1:
            result['timezone'] = tzs[0]
        if result['period_end_time'] is None:
            issues.append({'reason': 'truncated_period_end_time'})
    else:
        issues.append({'reason': 'missing_or_ambiguous_period'})
    # Name values occupy fixed top-right cells; preserve evidence and never assign a法人.
    for key, ymin, ymax in [('display_name', .035, .05), ('legal_name', .05, .075)]:
        candidates = [s for s in spans if ymin*height <= s['bbox'][1] < ymax*height
                      and .61*width < s['bbox'][0] < .9*width]
        if len(candidates) == 1:
            result[key] = candidates[0]['text']
            result[key + '_evidence'] = candidates[0]
        else:
            issues.append({'reason': 'missing_or_ambiguous_' + key})
    lookup = defaultdict(set)
    for key, labels in ALIASES.items():
        for label in labels:
            lookup[_normal(label)].add(key)
    summary_keys = {'income', 'expenses', 'tax', 'transfers'}
    summary_labels = {_normal(a) for k in summary_keys for a in ALIASES[k]}
    labels = []
    for s in spans:
        x, y = s['bbox'][:2]
        if x < .35 * width and .165*height < y < .26*height:
            if _normal(s['text']) in lookup:
                labels.append((s, 'summary'))
        elif .345*height < y < .89*height and (x < .35*width or .50*width < x < .82*width):
            # Subtotals and section titles are explicit headers, not unrecognised transactions.
            if _normal(s['text']) in summary_labels:
                continue
            if _normal(s['text']) in {'subtotals','subtotal','subtotales','zwischensummen',
                                     'totale parziale','sous-totaux','subtotalen','sumy czciowe','delsummor'}:
                continue
            # Only actual labels begin in one of the two left-aligned table label columns.
            if x < .08*width or .50*width < x < .55*width:
                if set(s['text']) <= set('=-'):
                    continue
                labels.append((s, 'left' if x < width/2 else 'right'))
    grouped = defaultdict(list)
    for s, region in labels:
        candidates = []
        for number, value in numbers:
            nx = number['bbox'][0]
            if region == 'summary':
                valid_x = nx > .88*width
            elif region == 'left':
                valid_x = .35*width < nx < .5*width
            else:
                valid_x = nx > .82*width
            if valid_x and abs(_center(number)-_center(s)) <= 3:
                candidates.append((number,value))
        if not candidates:
            issues.append({'reason': 'missing_amount_row', 'label': s['text'],
                           'bbox': s['bbox'], 'candidate_keys': sorted(lookup.get(_normal(s['text']), []))})
            continue
        # A numeric cell within tolerance of more than one label is genuinely ambiguous.
        if any(sum(1 for other, r in labels if r == region and
                   abs(_center(number)-_center(other)) <= 3) != 1 for number,_ in candidates):
            issues.append({'reason': 'ambiguous_amount_row', 'label': s['text'], 'bbox': s['bbox']})
            continue
        keys = list(lookup.get(_normal(s['text']), []))
        if region == 'left':
            keys = [k for k in keys if k != 'commingling_vat_expenses']
        elif region == 'right':
            keys = [k for k in keys if k != 'commingling_vat_income']
        evidence = {'label': s['text'], 'label_bbox': s['bbox'], 'region': region,
                    'amounts': [{'text': n['text'], 'bbox': n['bbox'], 'value': v} for n,v in candidates],
                    'value': sum((v for _,v in candidates), Decimal('0'))}
        result['raw_rows'].append(evidence)
        if len(keys) != 1:
            issues.append({'reason': 'unknown_label' if not keys else 'ambiguous_label',
                           'label': s['text'], 'bbox': s['bbox']})
            continue
        grouped[keys[0]].append(evidence)
    for key, rows in grouped.items():
        result['control_evidence'][key] = rows
        if len(rows) == 1:
            result['controls'][key] = rows[0]['value']
        else:
            issues.append({'reason': 'duplicate_control', 'key': key, 'count': len(rows)})
    if summary_keys <= result['controls'].keys():
        result['controls']['totals'] = sum((result['controls'][k] for k in summary_keys), Decimal('0'))
        result['control_evidence']['totals'] = [{'derived_from': sorted(summary_keys),
                                               'reason': 'Sum of PDF section net totals'}]
    result['section_checks'] = {}
    transfers = {'bank_transfers', 'failed_bank_transfers', 'gift_card_transfer', 'credit_card_recovery'}
    taxes = {'tax_collected', 'tax_refunded', 'tax_withheld', 'income_tax_withheld', 'product_vat_adjustment'}
    income = {'product_sales_non_fba', 'refunds_non_fba', 'product_sales_fba', 'refunds_fba',
              'inventory_credit', 'liquidation_proceeds', 'liquidation_adjustments', 'shipping',
              'shipping_refunds', 'gift_wrap', 'gift_wrap_refunds', 'promotion', 'promotion_refunds',
              'guarantee_claims', 'chargebacks', 'shipping_reimbursement', 'safe_t_reimbursement',
              'commingling_vat_income', 'receivables_reversals'}
    sections = {'income': income, 'transfers': transfers, 'tax': taxes,
                'expenses': set(ALIASES) - summary_keys - income - transfers - taxes}
    for section, keys in sections.items():
        if section not in result['controls']:
            continue
        detail_sum = sum((result['controls'][k] for k in keys if k in result['controls']), Decimal(0))
        missing_rows = [i for i in issues if set(i.get('candidate_keys', [])) & keys]
        residual = detail_sum - result['controls'][section]
        result['section_checks'][section] = {'residual': residual,
            'complete': not missing_rows and not any(i['reason'] in
                ('ambiguous_amount_row', 'ambiguous_label', 'unknown_label', 'duplicate_control') for i in issues),
            'missing_rows': missing_rows}
        if residual:
            issues.append({'reason': 'section_total_mismatch', 'section': section, 'residual': residual})
    return result


def extract_pdf(path):
    """Return Decimal controls and private metadata; caller controls report redaction."""
    import fitz
    with fitz.open(Path(path)) as doc:
        if len(doc) != 1:
            raise ValueError(f'Unsupported Summary page count: {len(doc)}')
        page = doc[0]
        spans = [{'text': s['text'], 'bbox': tuple(s['bbox'])}
                 for block in page.get_text('dict')['blocks']
                 for line in block.get('lines', []) for s in line['spans']]
        result = parse_spans(spans, page.rect.width, page.rect.height)
        result['page_count'] = len(doc)
        result['path'] = str(path)
        result['text_span_count'] = len(spans)
        return result


def csv_controls(rows):
    """Build conservative controls from one normalized CSV, including Deferred.

    This is a column/type projection, not a financial classification decision.
    Refund.other is an opaque combined bucket: never force it into product sales.
    Net fee keys compare several PDF lines whose components CSV combines.
    Evidence keeps source lines and columns, so each residual stays reviewable.
    """
    rows = list(rows)
    currencies = {r.get('currency') for r in rows if r.get('currency')}
    if len(currencies) > 1:
        raise ValueError('csv_controls requires a single currency')
    required = {'product_sales', 'shipping_credits', 'gift_wrap_credits', 'promotional_rebates',
                'selling_fees', 'fba_fees', 'other_transaction_fees', 'other', 'total', 'type', 'fulfillment'}
    keys = {'product_sales_non_fba', 'product_sales_fba', 'refunds_non_fba', 'refunds_fba',
            'shipping', 'shipping_refunds', 'gift_wrap', 'gift_wrap_refunds', 'promotion',
            'promotion_refunds', 'selling_fees_non_fba', 'selling_fees_fba',
            'selling_fees_net', 'fba_fees_net', 'advertising', 'service_fees', 'shipping_labels',
            'shipping_label_adjustments', 'inventory_credit', 'adjustments',
            'liquidation_proceeds', 'liquidation_fees', 'safe_t_reimbursement', 'chargebacks',
            'tax_collected', 'tax_refunded', 'tax_withheld', 'tax', 'transfers', 'totals'}
    controls = dict.fromkeys(keys, Decimal(0))
    evidence = defaultdict(list)
    unallocated = []
    tax_columns = ('product_sales_tax', 'shipping_credits_tax', 'giftwrap_credits_tax',
                   'promotional_rebates_tax', 'regulatory_fee', 'tax_on_regulatory_fee')
    ad_labels = {_normal(x) for x in ALIASES['advertising']}

    def add(key, amount, row, columns, rule):
        controls[key] += amount
        if amount:
            evidence[key].append({'source_file': row.get('source_file'),
                'source_line': row.get('source_line'), 'columns': columns,
                'amount': amount, 'rule': rule})

    for row in rows:
        missing = required - row.keys()
        if missing:
            raise ValueError('Normalized CSV missing required columns: ' + ', '.join(sorted(missing)))
        amount = lambda c: Decimal(str(row.get(c, '0')))
        typ, fulfillment = row['type'], row['fulfillment']
        total = amount('total')
        add('totals', total, row, ['total'], 'All transaction types and statuses')
        if typ in ('Order', 'Refund'):
            add('selling_fees_net', amount('selling_fees'), row, ['selling_fees'],
                'Order/Refund selling-fee components')
        if typ != 'Liquidations':
            add('fba_fees_net', amount('fba_fees'), row, ['fba_fees'],
                'Net FBA fee column except liquidation components')
        present_tax_columns = ('collected_sales_tax',) if 'collected_sales_tax' in row else tax_columns
        taxes = sum((amount(c) for c in present_tax_columns), Decimal(0))
        add('tax_collected' if taxes >= 0 else 'tax_refunded', taxes, row,
            list(present_tax_columns), 'Sum tax/regulatory columns then split by sign')
        withheld = amount('marketplace_withheld_tax')
        add('tax_withheld', withheld, row, ['marketplace_withheld_tax'], 'Net withheld column')
        add('tax', taxes + withheld, row, list(present_tax_columns) + ['marketplace_withheld_tax'],
            'CSV explicit tax fields only; opaque other excluded')
        if typ in ('Order', 'Refund'):
            refund = typ == 'Refund'
            if fulfillment in ('FBA', 'FBM'):
                suffix = 'fba' if fulfillment == 'FBA' else 'non_fba'
                add(('refunds_' if refund else 'product_sales_') + suffix,
                    amount('product_sales'), row, ['product_sales'], typ + ' by fulfillment')
                if not refund:
                    add('selling_fees_' + suffix, amount('selling_fees'), row,
                        ['selling_fees'], 'Order selling fees by fulfillment')
            elif amount('product_sales'):
                unallocated.append({'source_file': row.get('source_file'),
                    'source_line': row.get('source_line'), 'column': 'product_sales',
                    'amount': amount('product_sales'), 'reason': 'unknown_fulfillment'})
            for source, target in [('shipping_credits', 'shipping'), ('gift_wrap_credits', 'gift_wrap'),
                                   ('promotional_rebates', 'promotion')]:
                add(target + ('_refunds' if refund else ''), amount(source), row,
                    [source], typ + ' column projection')
            if amount('other'):
                unallocated.append({'source_file': row.get('source_file'),
                    'source_line': row.get('source_line'), 'column': 'other',
                    'amount': amount('other'), 'fulfillment': fulfillment,
                    'reason': 'refund_other_combines_components' if refund else 'order_other_unknown'})
        elif typ in ('Transfer', 'Debt'):
            add('transfers', total, row, ['total'], 'Transfer/Debt activity')
        elif typ == 'Service Fee':
            key = 'advertising' if _normal(row.get('description', '')) in ad_labels else 'service_fees'
            add(key, total, row, ['total'], 'Service Fee description separates advertising')
        elif typ == 'Amazon Fees':
            add('service_fees', total, row, ['total'], 'Amazon Fees activity')
        elif typ == 'Shipping Services':
            description = _normal(row.get('description', ''))
            if description in ('returnpostagebilling', 'rechnung für den ruckversand', 'adjustment'):
                key = 'shipping_label_adjustments' if description == 'adjustment' else 'shipping_labels'
                add(key, total, row, ['total'], 'Shipping Services description')
            elif total:
                unallocated.append({'source_file': row.get('source_file'), 'source_line': row.get('source_line'),
                    'amount': total, 'reason': 'unknown_shipping_service'})
        elif typ == 'Adjustment':
            add('inventory_credit' if total >= 0 else 'adjustments', total, row,
                ['total'], 'Adjustment inventory credit / debit candidate by sign')
        elif typ == 'Liquidations':
            add('liquidation_proceeds', amount('product_sales'), row, ['product_sales'], 'Liquidations sales')
            add('liquidation_fees', amount('selling_fees') + amount('fba_fees') + amount('other_transaction_fees'),
                row, ['selling_fees', 'fba_fees', 'other_transaction_fees'], 'Liquidations fee columns')
        elif typ == 'SAFE-T reimbursement':
            add('safe_t_reimbursement', total, row, ['total'], 'Explicit transaction type')
        elif typ == 'Chargeback Refund':
            add('chargebacks', total, row, ['total'], 'Chargeback Refund net activity')
        elif typ != 'FBA Transaction fees' and total:
            unallocated.append({'source_file': row.get('source_file'), 'source_line': row.get('source_line'),
                'amount': total, 'type': typ, 'reason': 'unclassified_transaction_type'})
    return {'controls': controls, 'control_evidence': dict(evidence), 'unallocated': unallocated,
            'input_rows': len(rows), 'output_rows': len(rows), 'currency': next(iter(currencies), None),
            'comparison_groups': {'selling_fees_net': ['selling_fees_non_fba', 'selling_fees_fba',
                'selling_fee_refunds', 'refund_administration_fees'],
                'fba_fees_net': ['fba_fees', 'fba_fee_refunds', 'inventory_inbound_fees']}}

# Exact labels transcribed and reviewed across observed language/template variants.
ALIASES = {'adjustments': ['Aanpassingen',
                 'Adjustments',
                 'Ajustements',
                 'Ajustes',
                 'Anpassungen',
                 'Justeringar',
                 'Korekty',
                 'Modifiche'],
 'advertising': ['Advertentiekosten',
                 'Cost of Advertising',
                 'Costo de la publicidad',
                 'Costo della pubblicità',
                 'Coût de la publicité',
                 'Gastos de publicidad',
                 'Koszt reklamy',
                 'Prix de la publicité',
                 'Reklamkostnad',
                 'Werbekosten'],
 'advertising_refunds': ['Gutschrift für Inserenten',
                         'Reembolso para anunciante',
                         'Reembolso para el promotor',
                         'Refund for Advertiser',
                         'Remboursement pour le publicitaire',
                         'Remboursement pour l’annonceur',
                         'Rimborso per inserzionista',
                         'Terugbetaling voor adverteerder',
                         'Zwrot kosztów dla reklamodawcy',
                         'Återbetalning för annonsör'],
 'amazon_shipping_charges': ['Amazon Shipping Charge Adjustments',
                             'Amazon Shipping Charges',
                             'Amazon fraktkostnader',
                             'Costi di spedizione Amazon',
                             "Frais d'expédition Amazon",
                             'Gastos de envío de Amazon',
                             'Opłaty za wysyłk Amazon',
                             'Verzendkosten van Amazon'],
 'bank_transfers': ['Overboekingen naar bankrekening',
                    'Przelewy na rachunek bankowy',
                    'Transferencias a cuenta bancaria',
                    'Transferencias bancarias',
                    'Transfers to bank account',
                    'Transfert sur le compte bancaire',
                    'Transferts sur le compte bancaire',
                    'Trasferimenti sul conto corrente',
                    'Överföringar till bankkonto',
                    'Überweisungen auf Bankkonto'],
 'chargebacks': ['Chargeback',
                 'Chargebacks',
                 'Contestations de prélèvement',
                 'Obcienia zwrotne',
                 'Reintegros',
                 'Reversiones de cargo',
                 'Rétrofacturations',
                 'Rückbuchungen',
                 'Terugvorderingen',
                 'Återdebiteringar'],
 'commingling_vat_expenses': ['Commingling VAT',
                              'IVA de inventario combinado',
                              'TVA applicable au Stock sans étiquette',
                              'VAT za wspólne zapasy',
                              'Varierande moms'],
 'commingling_vat_income': ['Commingling VAT',
                            'IVA de inventario combinado',
                            'TVA applicable au Stock sans étiquette',
                            'VAT za wspólne zapasy',
                            'Varierande moms'],
 'credit_card_recovery': ['Avgifter för kreditkort och annan skuldindrivning',
                          'Cargos a tarjeta de crédito y otros tipos de recuperación de deuda',
                          'Cargos en tarjetas de crédito y otras recuperaciones de deudas',
                          'Charges to credit card and other debt recovery',
                          'Costi relativi alla carta di credito e ad altri tipi di recupero '
                          'crediti',
                          'Factures de cartes de crédit et autres recouvrements de dettes',
                          'Frais de recouvrement des cartes de crédit et autres créances',
                          "Kosten voor creditcardbetalingen en andere incasso's",
                          'Kreditkartengebühren und andere Inkassogebühren',
                          'Opłaty ztytułu kart kredytowych iinnych form odzyskiwania nalenoci'],
 'expenses': ['Ausgaben',
              'Costes',
              'Dépenses',
              'Expenses',
              'Gastos',
              'Spese',
              'Uitgaven',
              'Utgifter',
              'Wydatki'],
 'failed_bank_transfers': ['Failed transfers to bank account',
                           'Fehlgeschlagene Überweisungen zu Bankkonto',
                           'Mislukte overschrijvingen naar bankrekening',
                           'Misslyckade överföringar till bankkonto',
                           'Nieudane przelewy na rachunek bankowy',
                           'Transferencias bancarias fallidas',
                           'Transferencias con error a cuenta bancaria',
                           'Trasferimenti non riusciti sul conto corrente',
                           'Versements vers le compte bancaire ayant échoué',
                           'Échec des transferts sur le compte bancaire'],
 'fba_fee_refunds': ['Erstattungen zur Transaktionsgebühr - Versand durch Amazon',
                     'FBA transaction fee refunds',
                     'FBA — zwroty opłat transakcyjnych',
                     'Reembolsos de tarifas de transacción FBA',
                     'Remboursement des frais de transaction « Expédié par Amazon »',
                     'Remboursements des frais de transaction Expédié par Amazon',
                     'Rimborsi commissioni Logistica di Amazon per transazione',
                     'Tarifas de reembolso de transacciones de Logística de Amazon',
                     'Terugbetaling FBA-transactiekosten',
                     'Återbetalningar av FBA-transaktionsavgift'],
 'fba_fees': ['Commissioni Logistica di Amazon per transazione',
              'FBA transaction fees',
              'FBA — opłaty transakcyjne',
              'FBA-transactiekosten',
              'FBA-transaktionsavgifter',
              'Frais de transaction Expédié par Amazon',
              'Frais de transaction « Expédié par Amazon »',
              'Tarifas de transacciones de Logística de Amazon',
              'Tarifas de transacción FBA',
              'Transaktionsgebühren Versand durch Amazon'],
 'gift_card_transfer': ['Disburse to Amazon Gift Card balance'],
 'gift_wrap': ['Abonos de envoltorio para regalo',
               'Accrediti per confezione regalo',
               'Créditos por envoltorio de regalo',
               "Crédits des frais d'emballage",
               'Crédits pour l’emballage cadeau',
               'Gift wrap credits',
               'Gutschrift für Geschenkverpackung',
               'Krediter presentinslagning',
               'Tegoeden cadeauverpakking',
               'rodki na pokrycie pakowania na prezent'],
 'gift_wrap_refunds': ['Erstattungen zu Gutschriften aus Geschenkverpackungen',
                       'Gift wrap credit refunds',
                       'Kreditåterbetalningar presentinslagning',
                       'Reembolso de abonos por envoltorio para regalo',
                       'Reembolsos de crédito de envoltorio de regalo',
                       "Remboursement des crédits d'emballage",
                       'Remboursements du crédit pour l’emballage cadeau',
                       'Restituties cadeauverpakking',
                       'Rimborsi per accrediti confezioni regalo',
                       'Zwroty rodków na pokrycie pakowania na prezent'],
 'guarantee_claims': ['A-bis-Z-Garantieanträge',
                      'A-to-z Guarantee Claims',
                      'A-to-z Guarantee claims',
                      'A-tot-Z-garantieclaims',
                      'Anspråk på A-to-z guarantee',
                      'Garanties A à Z',
                      'Reclamaciones bajo la Garantía de la A a la Z',
                      'Reclami dalla A alla Z',
                      'Reclamos de A-to-z Guarantee',
                      'Roszczenia w ramach gwarancji od A do Z',
                      'Réclamations au titre de la Garantie A à Z'],
 'income': ['Einnahmen',
            'Income',
            'Ingresos',
            'Inkomen',
            'Intäkter',
            'Przychód',
            'Revenus',
            'Ricavi'],
 'income_tax_withheld': ['Impuesto sobre la Renta retenido'],
 'inventory_credit': ["Credito dell'inventario FBA",
                      'Crédit du stock Expédié par Amazon',
                      'Crédit inventaire FBA',
                      'Crédito de inventario FBA',
                      'Crédito de inventario del FBA',
                      'FBA Lagerbestandguthaben',
                      'FBA inventory credit',
                      'FBA — rodki na pokrycie zapasów',
                      'FBA-voorraadkrediet',
                      'Kredit för FBA-lager'],
 'inventory_inbound_fees': ["Costi di gestione dell'inventario e per i servizi di Logistica di "
                            'Amazon',
                            'FBA inventory and inbound services fees',
                            'FBA — opłaty za zapasy i usługi zwizane z wysyłk',
                            'FBA-avgifter för lagerhållning och inkommande tjänster',
                            'Frais de stockage et de services logistiques Expédié par Amazon',
                            'Kosten voor voorraad en binnenkomende goederen bij FBA',
                            'Lagerbestands- und Service-Gebühren für Versand durch Amazon',
                            'Tarifas de inventario y de servicios de Logística de Amazon'],
 'liquidation_adjustments': ['Aggiustamenti sui ricavi di liquidazione di Logistica di Amazon',
                             'Ajustements des recettes Liquidations Expédié par Amazon',
                             'Ajustements des recettes des liquidations Expédié par Amazon',
                             'Ajustes de ingresos por liquidación de Logística de Amazon',
                             'Anpassungen des "Versand durch Amazon" -Liquidationserlöses',
                             'FBA Liquidations proceeds adjustments'],
 'liquidation_fees': ['Avgifter för utförsäljningar',
                      'Frais de liquidation',
                      'Frais de liquidations',
                      'Gebühren für Liquidationen',
                      'Liquidations fees',
                      'Opłaty za likwidacj',
                      'Tarifas del programa de liquidación',
                      'Tariffe del Programma di liquidazione'],
 'liquidation_proceeds': ['Erlöse der Liquidation über Versand durch Amazon',
                          'FBA liquidation proceeds',
                          'FBA — przychody z likwidacji',
                          'FBA-liquidatieopbrengsten',
                          'Ingresos por liquidación',
                          'Intäkter från FBA-utförsäljning',
                          'Produits de liquidation Expédié par Amazon',
                          'Ricavi della liquidazione di Logistica di Amazon'],
 'other_fee_refunds': ['Other transaction fee refunds',
                       'Reembolso de tarifas de otras transacciones',
                       'Reembolsos de tarifas de otras transacciones',
                       "Remboursement d'autres frais de transaction",
                       'Remboursements des autres frais de transaction',
                       'Restituties overige transactiekosten',
                       'Rimborsi per altri costi relativi alle transazioni',
                       'Sonstige Erstattungen zu Transaktionsgebühren',
                       'Zwroty innych opłat transakcyjnych',
                       'Återbetalningar av andra transaktionsavgifter'],
 'other_fees': ['Altri costi relativi alle transazioni',
                'Andere Transaktionsgebühren',
                'Autres frais de transaction',
                'Inne opłaty transakcyjne',
                'Other transaction fees',
                'Overige transactiekosten',
                'Tarifas de otra transacción',
                'Tarifas de otras transacciones',
                'Övriga transaktionsavgifter'],
 'penalty_charges': ['Penalty Charges'],
 'product_sales_fba': ['FBA product sales',
                       'FBA — sprzeda produktów',
                       'FBA-produktförsäljning',
                       'Vendite articoli gestiti con Logistica di Amazon',
                       'Venta de productos de Logística de Amazon',
                       'Ventas de producto FBA',
                       'Vente des produits Expédié par Amazon',
                       'Ventes de produits Expédié par Amazon',
                       'Verkoop van FBA-producten',
                       'Verkäufe mit Versand durch Amazon'],
 'product_sales_non_fba': ['Product sales (non-FBA)',
                           'Produktförsäljning (ej FBA)',
                           'Seller fulfilled product sales',
                           'Seller-fulfilled product sales',
                           'Sprzeda produktów (inna ni FBA)',
                           'Vendite articoli gestiti dal venditore',
                           'Venta de producto realizada por el vendedor',
                           'Venta de productos gestionados por el vendedor',
                           'Vente de produits expédiés par le vendeur',
                           'Ventes de produits (non expédiés par Amazon)',
                           'Verkoop van producten (niet-FBA)',
                           'Verkäufe, die durch Verkäufer selbst verschickt wurden'],
 'product_vat_adjustment': ['Ajuste del IVA del producto'],
 'promotion': ['Descuentos promocionales',
               'Devoluciones promocionales',
               'Kampanjrabatter',
               'Promotiekortingen',
               'Promotional rebates',
               'Rabais promotionnels',
               'Rabaty promocyjne',
               'Sconti promozionali',
               'Total des réductions',
               'Werbeaktions-Rabatte'],
 'promotion_refunds': ['Erstattungen zu Werbeaktions-Rabatt',
                       'Promotional rebate refunds',
                       'Reembolso de devoluciones promocionales',
                       'Reembolsos de descuento promocional',
                       'Remboursement des rabais promotionnels',
                       'Remboursements de remises promotionnelles',
                       'Rimborsi per sconti promozionali',
                       'Terugbetalingen promotiekorting',
                       'Zwroty kosztów rabatów promocyjnych',
                       'Återbetalning av kampanjrabatt'],
 'receivables_deductions': ['Avdrag för fordringar',
                            'Deducciones de cuentas por cobrar',
                            'Detrazioni dei crediti',
                            'Déductions pour créances',
                            'Déductions sur créances',
                            'Inhoudingen op vorderingen',
                            'Potrcenia nalenoci',
                            'Receivables Deductions'],
 'receivables_reversals': ['Annulations de créances',
                           'Odwrócenie nalenoci',
                           'Receivables Reversals',
                           'Reversiones de cuentas por cobrar',
                           'Storni dei crediti',
                           'Terugboekingen van vorderingen',
                           'Återkallande av fordringar'],
 'refund_administration_fees': ['Administratiekosten terugbetalen',
                                'Administrativ avgift för återbetalning',
                                'Bearbeitungsgebühren für Erstattungen',
                                'Costi amministrativi relativi ai rimborsi',
                                'Opłata manipulacyjna za zwrot kosztów',
                                'Refund administration fees',
                                'Remboursement des frais administratifs',
                                'Retenues sur les remboursements',
                                'Tarifas de administración de reembolso',
                                'Tarifas de administración de reembolsos'],
 'refunds_fba': ['Erstattungen für durch Amazon versandte Artikel',
                 'FBA product sale refunds',
                 'FBA — zwroty kosztów sprzeday produktów',
                 'Reembolso de ventas de productos de Logística de Amazon',
                 'Reembolsos de venta de producto FBA',
                 'Remboursement des produits vendus et « Expédié par Amazon »',
                 'Remboursements des ventes de produits Expédié par Amazon',
                 'Rimborsi per articoli gestiti con Logistica di Amazon',
                 'Terugbetalingen voor verkoop van FBA-producten',
                 'Återbetalningar FBA-produktförsäljning'],
 'refunds_non_fba': ['Erstattungen für vom Verkäufer versandte Artikel',
                     'Product sale refunds (non-FBA)',
                     'Reembolso de ventas de productos gestionados por el vendedor',
                     'Reembolsos de venta de producto realizada por el vendedor',
                     'Remboursement des produits vendus et expédiés par le vendeur',
                     'Remboursements dans le cadre de la vente de produits (non expédiés par A',
                     'Rimborsi per vendita articoli gestiti dal venditore',
                     'Seller fulfilled product sale refunds',
                     'Seller-fulfilled product sale refunds',
                     'Terugbetalingen voor productverkoop (niet-FBA)',
                     'Zwroty kosztów sprzeday produktów (innej ni FBA)',
                     'Återbetalningar av produktförsäljning (ej FBA)'],
 'safe_t_reimbursement': ['Dédommagement SAFE-T',
                          'Reembolso de SAFE-T',
                          'Remboursement SAFE-T',
                          'Rimborso SAFE-T (Seller Assurance for E-commerce Transactions)',
                          'SAFE-T reimbursement',
                          'SAFE-T-Erstattung',
                          'SAFE-T-terugbetaling',
                          'SAFE-T-återbetalning',
                          'Zwrot kosztów SAFE-T'],
 'selling_fee_refunds': ['Erstattungen zur Verkaufsgebühr',
                         'Reembolso de tarifas de venta',
                         'Reembolsos de tarifa de venta',
                         'Remboursement des frais de vente',
                         'Remboursements des frais de vente',
                         'Rimborsi per commissioni di vendita',
                         'Selling fee refunds',
                         'Terugbetaling van verkoopkosten',
                         'Zwroty opłat za sprzeda',
                         'Återbetalningar av försäljningsavgift'],
 'selling_fees_fba': ['Commissioni di vendita con Logistica di Amazon',
                      'FBA selling fees',
                      'FBA — opłaty za sprzeda',
                      'FBA-försäljningsavgifter',
                      'FBA-verkoopkosten',
                      'Frais de vente  « Expédié par Amazon »',
                      'Frais de ventes Expédié par Amazon',
                      'Tarifas de venta FBA',
                      'Tarifas de venta de Logística de Amazon',
                      'Verkaufsgebühren Versand durch Amazon'],
 'selling_fees_non_fba': ['Commissioni di vendita gestita dal venditore',
                          'Frais de vente expédié par le vendeur',
                          'Frais de vente expédiée par le vendeur',
                          'Försäljningsavgifter levererat av säljare',
                          'Opłaty za sprzeda realizowan przez Sprzedawc',
                          'Seller fulfilled selling fees',
                          'Seller-fulfilled selling fees',
                          'Tarifas de venta de pedidos gestionados por el vendedor',
                          'Tarifas de venta realizadas por el vendedor',
                          'Verkaufsgebühren Versand durch Verkäufer',
                          'Verkoper heeft verkoopkosten voldaan'],
 'service_fees': ['Commissioni di servizio',
                  'Frais de service',
                  'Frais sur les services',
                  'Opłaty za usługi',
                  'Service fees',
                  'Serviceavgifter',
                  'Servicegebühren',
                  'Servicekosten',
                  'Tarifas de servicio'],
 'shipping': ['Abonos de envío',
              'Accrediti per le spedizioni',
              'Créditos de envío',
              'Crédits d’expédition',
              "Crédits pour l'expédition",
              'Fraktkrediter',
              'Noty kredytowe za wysyłk',
              'Postage credits',
              'Shipping credits',
              'Versandkostengutschriften',
              'Verzendtegoeden'],
 'shipping_label_adjustments': ['Aanpassingen aan verzendetiketten van de transportdienst',
                                "Ajustements de l'étiquette d'expédition du transporteur",
                                'Ajustements de l’étiquette d’expédition du transporteur',
                                'Ajustes en etiqueta de envío del transportista',
                                'Ajustes en la etiqueta de envío del transportista',
                                'Anpassungen des Versandscheins',
                                'Carrier delivery label adjustments',
                                'Carrier shipping label adjustments',
                                'Justeringar av fraktetikett speditör',
                                'Korekty do etykiet wysyłkowych przez przewonika',
                                'Modifiche etichetta di spedizione corriere'],
 'shipping_label_refunds': ['Delivery label refunds',
                            'Erstattungen zu Versandscheinen',
                            'Reembolso de etiquetas de envío',
                            'Reembolsos de etiqueta de envío',
                            "Remboursement des étiquettes d'expédition",
                            'Remboursements des étiquettes d’expédition',
                            'Rimborsi relativi alle etichette di spedizione',
                            'Shipping label refunds',
                            'Terugbetalingen verzendetiket',
                            'Zwroty kosztów etykiet wysyłkowych',
                            'Återbetalningar fraktetikett'],
 'shipping_labels': ['Aankopen verzendetiketten',
                     "Achats d'étiquettes d'expédition",
                     'Achats d’étiquettes d’expédition',
                     'Acquisti delle etichette di spedizione',
                     'Compra de etiquetas de envío',
                     'Compras de etiqueta de envío',
                     'Delivery label purchases',
                     'Erwerb von Versandscheinen',
                     'Inköp fraktetikett',
                     'Shipping label purchases',
                     'Zakupy etykiet wysyłkowych'],
 'shipping_refunds': ['Delivery credit refunds',
                      'Erstattungen zu Versandkostengutschriften',
                      'Reembolso de abonos de envío',
                      'Reembolsos de crédito de envío',
                      "Remboursement des crédits sur l'expédition",
                      'Remboursements des crédits d’expédition',
                      'Rimborsi per accrediti spedizioni',
                      'Shipping credit refunds',
                      'Terugbetalingen verzendtegoed',
                      'Zwroty do not kredytowych za wysyłk',
                      'Återbetalningar av fraktkredit'],
 'shipping_reimbursement': ['Amazon Shipping Reimbursement',
                            'Amazon Shipping Reimbursement Adjustments',
                            'Dédommagement Amazon Shipping',
                            'Reembolso de envío de Amazon',
                            'Reembolso por envío de Amazon',
                            "Remboursement des frais d'expédition d'Amazon",
                            'Rimborso spedizione Amazon',
                            'Terugbetaling van Amazon-verzendkosten',
                            'Återbetalning av Amazon-frakt'],
 'tax': ['Belasting', 'Imposte', 'Impuesto', 'Moms', 'Podatek', 'Steuer', 'Tax', 'Taxe'],
 'tax_collected': ['Eingezogene Produkt-, Versand- und Geschenkverpackungssteuern',
                   'Imposte relative a prodotto, spedizione e confezione regalo riscosse',
                   'Impuestos cobrados por producto, envío y envoltorio para regalo',
                   'Impuestos de producto, envío y envoltura para regalo retenidos',
                   'Insamlade skatter för produkter, frakt och presentinslagning',
                   'Potrcone podatki od produktów, wysyłki i pakowania',
                   'Product, delivery and gift wrap taxes collected',
                   'Product, shipping and gift wrap taxes collected',
                   'Product, shipping, gift wrap taxes and regulatory fee collected',
                   'Product-, verzend- en cadeauverpakkingsbelasting verzameld',
                   "Taxes prélevées sur les produits, les frais d'expédition et l'emballage ca",
                   'Taxes sur les produits, l’expédition et les emballages cadeaux collectées'],
 'tax_refunded': ['Imposte relative a prodotto, spedizione e confezione regalo rimborsate',
                  'Impuestos de producto, envío y envoltura para regalo reembolsados',
                  'Impuestos reembolsados por producto, envío y envoltorio para regalo',
                  'Product, delivery and gift wrap taxes refunded',
                  'Product, shipping and gift wrap taxes refunded',
                  'Product, shipping, gift wrap taxes and regulatory fee refunded',
                  'Product-, verzend- en cadeauverpakkingsbelasting terugbetaald',
                  'Taxes remboursées concernant les produits, l’expédition et les emballag',
                  "Taxes remboursées sur les produits, les frais d'expédition et l'emballage",
                  'Zurückerstattete Produkt-, Versand- und Geschenkverpackungssteuern',
                  'Zwrócone podatki od produktów, wysyłki i pakowania',
                  'Återbetalade skatter för produkter, frakt och presentinslagning'],
 'tax_withheld': ['Amazon Obligated Tax and Regulatory Fee Withheld',
                  'Amazon obligated tax withheld',
                  'Amazon verpflichtete einbehaltene Steuer',
                  'Impuesto al valor agregado (IVA) obligatorio de Amazon retenido',
                  'Impuesto retenido por Amazon',
                  'Podatek potrcony przez Amazon (w ramach zobowiza)',
                  'Retenue de taxes Amazon',
                  'Ritenuta fiscale obbligatoria da Amazon',
                  'TVA Amazon retenue à la source',
                  'Uttagen obligatorisk Amazon-skatt',
                  'Verplichte belasting ingehouden door Amazon'],
 'transfers': ['Overboekingen',
               'Przelewy',
               'Transferencias',
               'Transfers',
               'Transferts',
               'Trasferimenti',
               'Överföringar',
               'Übertragungen']}
