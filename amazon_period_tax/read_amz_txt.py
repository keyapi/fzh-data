# -*- coding: utf-8 -*-
"""读取账期桶内 Amazon 结算 .txt（Colab「税账期TXT 挂载Gdrive」同源逻辑 + 渠道账号规范名）。

门禁要点（gate_audit_20261120.md R01–R09）：

- **R01 范围**：先枚举根目录/一级/更深文件与排除目录，每个文件都有终态（见
  ``source_ledger.SourceLedger``）；非 AMZ/非 txt 进库存清单；**内容像 Amazon 结算但
  命名/位置不对**的文件记为 ``needs_review``（阻断发布），不再静默跳过。
- **R02 schema**：逐文件识别 V1/V2；XML/未知/空文件/缺必需列显式拒绝。
- **R03 V1 守恒**：展开前后行数与**各金额族总额**都要守恒；有金额缺 type 直接失败；
  未知 ``*-amount`` 列不允许被 expected 与展开共同漏掉。
- **R04 金额**：复用 ``amounts.parse_amount_strict``（按单元格 ``auto``）。
- **R05 只读**：``write_repairs=False`` 时 tab 修复纯内存，不落任何缓存文件；
  修复前后列数/金额/结算号不变（``fix_issues_in_txt`` 只删多余 tab）。
- **R06 去重**：同 md5 同账号只读一份；同 md5 **不同账号** → ``needs_review``。
- **R07 结算唯一**：同 settlement-id 不同字节 / V1+V2 双份 → ``needs_review``。
- **R08 跨期**：按内部 settlement-end-date（缺失退 deposit-date）判账期月；无内部日期
  文件保留行但标记 ``no_period_date`` 并阻断发布；白名单支持绑定文件 sha256。
- **R09 守恒**：``stats['files_total'] == used+dup+failed+out_of_period+approved_excluded+needs_review``
  由 ``ledger.assert_conservation()`` 强校验。
"""
from __future__ import annotations

import io
import math
import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd

_REPO = Path(__file__).resolve().parents[1]
_PKG = Path(__file__).resolve().parent
_DING = _REPO / "dingtalk" / "dingtalk_oa_approval"
for _p in (_PKG, _DING):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from amounts import infer_decimal_format, is_blank_value, parse_amount_strict  # noqa: E402
from amz_txt_naming import account_prefix_from_stem, preprocess_stem  # noqa: E402
from bucket_meta import bucket_period_range  # noqa: E402
from channel_canonical import canonical_account  # noqa: E402
from source_ledger import (  # noqa: E402
    KIND_AMZ_TXT,
    KIND_DIR,
    KIND_NON_AMZ_TXT,
    KIND_NON_TXT,
    SCOPE_DIR,
    SCOPE_EXCLUDED_FOLDER,
    SCOPE_HIDDEN_DIR,
    SCOPE_IN_SCOPE,
    SCOPE_NESTED_FILE,
    SCOPE_OTHER_FILE,
    SCOPE_ROOT_FILE,
    STATE_APPROVED_EXCLUDED,
    STATE_DUP,
    STATE_FAILED,
    STATE_OUT_OF_PERIOD,
    STATE_USED,
    SourceLedger,
    SourceRecord,
)

DEFAULT_EXCLUDE_FOLDERS = ("杨鹏瑶", "贾晓林", "尹天强")

# settlement-end-date 形如 ``2026-07-28 01:03:22 UTC``；部分国家站导出为 ``28.07.2026 01:03:22 UTC``
_DATE_YMD = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
_DATE_DMY = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})")

_META_COLS = ("settlement-id", "settlement-end-date", "deposit-date")

# 每种 schema 的必需列（R02）。V1 额外要求至少一组成对金额列。
V2_REQUIRED_COLUMNS = ("settlement-id", "currency", "amount", "amount-type", "amount-description")
V1_REQUIRED_COLUMNS = ("settlement-id", "currency")

_V1_FAMILIES = (
    ("price-type", "price-amount", "ItemPrice"),
    ("item-related-fee-type", "item-related-fee-amount", "ItemFees"),
    ("shipment-fee-type", "shipment-fee-amount", "ItemFees"),
    ("order-fee-type", "order-fee-amount", "ItemFees"),
    ("promotion-type", "promotion-amount", "Promotion"),
    ("direct-payment-type", "direct-payment-amount", "ItemFees"),
)

_V1_AMOUNT_COLS = tuple((t, a) for t, a, _ in _V1_FAMILIES)
_V1_BARE_AMOUNT_COLS = ("misc-fee-amount", "other-fee-amount", "other-amount")
_KNOWN_AMOUNT_COLUMNS = frozenset(
    {"amount", "total-amount", *(a for _, a in _V1_AMOUNT_COLS), *_V1_BARE_AMOUNT_COLS}
)


def _parse_date_value(value: str | None) -> date | None:
    if not value:
        return None
    s = value.strip()
    m = _DATE_YMD.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = _DATE_DMY.match(s)
        if not m:
            return None
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def settlement_meta(text: str) -> dict:
    """解析 (settlement-id, settlement-end-date, deposit-date) 原始字符串。

    settlement-id 每行都有；两个日期只出现在首行（TransactionTotalAmount），缺失返回 None。
    """
    out = {"settlement_id": None, "settlement_end_raw": None, "deposit_raw": None}
    lines = text.splitlines()
    if not lines:
        return out
    header = lines[0].split("\t")
    idx = {name: (header.index(name) if name in header else None) for name in _META_COLS}
    id_idx = idx["settlement-id"] if idx["settlement-id"] is not None else 0
    end_idx, dep_idx = idx["settlement-end-date"], idx["deposit-date"]

    for line in lines[1:]:
        cols = line.split("\t")
        if out["settlement_id"] is None and len(cols) > id_idx and cols[id_idx].strip():
            out["settlement_id"] = cols[id_idx].strip()
        if out["settlement_end_raw"] is None and end_idx is not None and len(cols) > end_idx and cols[end_idx].strip():
            out["settlement_end_raw"] = cols[end_idx].strip()
        if out["deposit_raw"] is None and dep_idx is not None and len(cols) > dep_idx and cols[dep_idx].strip():
            out["deposit_raw"] = cols[dep_idx].strip()
        if out["settlement_id"] is not None and (
            (end_idx is None or out["settlement_end_raw"] is not None)
            and (dep_idx is None or out["deposit_raw"] is not None)
        ):
            break
    return out


def parse_settlement_meta(text: str) -> tuple[str | None, str | None]:
    """(settlement-id, settlement-end-date) 原始字符串。"""
    meta = settlement_meta(text)
    return meta["settlement_id"], meta["settlement_end_raw"]


def settlement_end_date(text: str) -> date | None:
    """内部 settlement-end-date → date；缺失或非法返回 None。"""
    return _parse_date_value(settlement_meta(text)["settlement_end_raw"])


def settlement_window_date(text: str) -> tuple[date | None, date | None, date | None]:
    """返回 (窗口判定日期, settlement_end_date, deposit_date)。

    账期桶是 OA 的「账期日期」4 号→次月 3 号窗口，对应 Amazon 结算的 **deposit-date**
    （打款日）。用 deposit-date 判定才不会把「7/20–8/3 结算、8/5 打款」的 8 月正常结算误判成跨期；
    deposit-date 缺失时退回 settlement-end-date。
    """
    meta = settlement_meta(text)
    end = _parse_date_value(meta["settlement_end_raw"])
    dep = _parse_date_value(meta["deposit_raw"])
    return (dep or end), end, dep


# ---------------------------------------------------------------- schema (R02)


def _first_non_empty_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line
    return ""


def detect_schema(text: str) -> str:
    """识别 txt schema：``v2`` / ``v1`` / ``xml`` / ``unknown`` / ``empty``。"""
    if text is None:
        return "empty"
    first = _first_non_empty_line(text).lstrip("﻿").strip()
    if not first:
        return "empty"
    if first.startswith("<"):
        return "xml"
    header = [h.strip() for h in first.split("\t")]
    if "amount-type" in header:
        return "v2"
    if "price-type" in header:
        return "v1"
    return "unknown"


def _header_columns(text: str) -> list[str]:
    return [h.strip() for h in _first_non_empty_line(text).split("\t")]


def missing_required_columns(header: list[str], schema: str) -> list[str]:
    """返回缺失的必需列（空列表=通过）。"""
    if schema == "v2":
        return [c for c in V2_REQUIRED_COLUMNS if c not in header]
    if schema == "v1":
        missing = [c for c in V1_REQUIRED_COLUMNS if c not in header]
        has_pair = any(t in header and a in header for t, a in _V1_AMOUNT_COLS)
        has_bare = any(a in header for a in _V1_BARE_AMOUNT_COLS)
        if not (has_pair or has_bare):
            missing.append("至少一组成对金额列（price-type/price-amount 等）")
        return missing
    return ["未知 schema（无法校验列）"]


def unknown_amount_columns(header: list[str]) -> list[str]:
    """未知金额族列（R03）：任何 ``*-amount``/``amount`` 未登记都不得被静默漏掉。"""
    return [
        c
        for c in header
        if (c.endswith("-amount") or c == "amount") and c not in _KNOWN_AMOUNT_COLUMNS
    ]


def _v1_rows_with_amount_but_no_type(raw_df: pd.DataFrame) -> list[str]:
    problems: list[str] = []
    for pos in range(len(raw_df)):
        for type_col, amount_col in _V1_AMOUNT_COLS:
            if type_col not in raw_df.columns or amount_col not in raw_df.columns:
                continue
            amount = raw_df[amount_col].iloc[pos]
            label = raw_df[type_col].iloc[pos]
            if not is_blank_value(amount) and is_blank_value(label):
                problems.append(f"行{pos + 2} {amount_col}={amount!r} 有金额但 {type_col} 为空")
    return problems


def _v1_amount_total_raw(raw_df: pd.DataFrame) -> float:
    """V1 原始金额族总额（严格解析；用于展开前后守恒）。"""
    total = 0.0
    for _, amount_col in _V1_AMOUNT_COLS:
        if amount_col not in raw_df.columns:
            continue
        for value in raw_df[amount_col].tolist():
            parsed = parse_amount_strict(value, decimal_separator="auto")
            if parsed is not None:
                total += parsed
    for amount_col in _V1_BARE_AMOUNT_COLS:
        if amount_col not in raw_df.columns:
            continue
        for value in raw_df[amount_col].tolist():
            parsed = parse_amount_strict(value, decimal_separator="auto")
            if parsed is not None:
                total += parsed
    return total


# ------------------------------------------------------- 跨期白名单（R08）


def _load_period_exceptions(bucket_dir: Path) -> dict[str, dict]:
    """读取显式跨期白名单：``{桶父目录}/_period_exceptions/{桶名}.txt``。

    每行：
    - ``人名夹/文件名``：沿用「纳入」语义（历史例外，无 hash）；
    - ``人名夹/文件名#sha256=<hex>``：纳入，且文件内容变化后例外失效；
    - ``exclude:人名夹/文件名#sha256=<hex>``：经批准**排除**（``approved_excluded``）。

    ``#`` 开头整行为注释。缺 hash 的 ``exclude:`` 视为未核实 → needs_review。
    """
    p = bucket_dir.parent / "_period_exceptions" / f"{bucket_dir.name}.txt"
    out: dict[str, dict] = {}
    if not p.is_file():
        return out
    for raw in p.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        action = "include"
        if s.lower().startswith("exclude:"):
            action = "exclude"
            s = s[len("exclude:") :].strip()
        digest = None
        if "#sha256=" in s:
            s, digest = s.split("#sha256=", 1)
            digest = digest.strip().lower() or None
        path = s.replace("\\", "/").lstrip("./")
        if path:
            out[path] = {"action": action, "sha256": digest}
    return out


def _load_out_of_period_allowlist(bucket_dir: Path) -> set[str]:
    """兼容旧调用：只返回「纳入」语义的路径集合。"""
    return {
        path
        for path, spec in _load_period_exceptions(bucket_dir).items()
        if spec.get("action") == "include"
    }


def check_for_issues(lines: list[str]) -> bool:
    if not lines:
        return False
    header_tabs = lines[0].count("\t")
    for line in lines[1:]:
        if line.count("\t") > header_tabs:
            return True
    return False


def fix_issues_in_txt(lines: list[str]) -> list[str]:
    """多余 tab 修复：**按表头列数截断行尾**，不猜测中间位置、不移动列。

    旧实现删「倒数第 3 个 tab」，会把 ``amount-description`` 与 ``amount-type`` 拼成
    一个字段（审计 R05：删 tab 造成移列）。这里只丢弃超出行尾的额外字段：
    ``settlement-id``/金额/描述/类型等**已映射列保持不变**，列数与表头一致。
    """
    if not lines:
        return lines
    n_cols = lines[0].count("\t") + 1
    fixed_lines = [lines[0]]
    for line in lines[1:]:
        eol = "\n" if line.endswith("\n") else ""
        body = line[: -len(eol)] if eol else line
        fields = body.split("\t")
        if len(fields) > n_cols:
            body = "\t".join(fields[:n_cols])
        fixed_lines.append(body + eol)
    return fixed_lines


def _account_from_filename(file_name: str) -> str:
    stem = preprocess_stem(Path(file_name).stem)
    raw = account_prefix_from_stem(stem)
    if not raw.upper().startswith("AMZ"):
        legacy = re.sub(r"\s*[-–]\s*", "-", file_name).split("-")[0].strip()
        legacy = re.sub(r"\d+$", "", legacy)
        raw = legacy
    return canonical_account(raw) or raw


def convert_amz_last2letter_upper(x: str) -> str:
    x = str(x or "")
    if x[:3].upper() == "AMZ":
        return x[:3].upper() + x[3:-2] + x[-2:].upper()
    return x


def looks_like_amz_settlement(text: str) -> bool:
    """内容是否像 Amazon 结算表（用于识别命名/位置错误的疑似结算文件）。"""
    first = _first_non_empty_line(text).lstrip("﻿")
    if not first:
        return False
    for sep in ("\t", ",", ";"):
        header = [h.strip().strip('"') for h in first.split(sep)]
        if "settlement-id" in header and ("amount-type" in header or "price-type" in header):
            return True
    return False


def _normalize_v1_schema(df: pd.DataFrame) -> pd.DataFrame:
    """旧版 V1 结算表（price-type/price-amount 族）→ V2 长表。

    V1 没有 amount-type/amount-description/amount；直接按 V2 读会把金额变成 NaN，
    Tax/FBA 静默少算。按 Amazon 的 V1→V2 语义把各金额族展开成一行一条:
    ``MarketplaceFacilitator*`` 是代扣税，归 ItemWithheldTax，不得混入 ItemPrice。
    """
    if "amount-type" in df.columns or "price-type" not in df.columns:
        return df
    # 汇总行在展开时会被丢掉；先把只有汇总行才有的币种/结算号前向填充到每条明细。
    df = df.copy()
    for carry in ("currency", "settlement-id"):
        if carry in df.columns:
            df[carry] = df[carry].ffill()
    rows: list[dict] = []
    for _, src in df.iterrows():
        base = src.to_dict()

        def emit(amount_type: str, description: str, amount) -> None:
            if amount is None or (isinstance(amount, str) and amount.strip() == ""):
                return
            try:
                if pd.isna(amount):
                    return
            except (TypeError, ValueError):
                pass
            row = dict(base)
            row["amount-type"] = amount_type
            row["amount-description"] = description
            row["amount"] = amount
            rows.append(row)

        for type_col, amt_col, amount_type in _V1_FAMILIES:
            if type_col not in df.columns or amt_col not in df.columns:
                continue
            label = src.get(type_col)
            if label is None or (isinstance(label, str) and label.strip() == ""):
                continue
            try:
                if pd.isna(label):
                    continue
            except (TypeError, ValueError):
                pass
            desc = str(label).strip()
            at = "ItemWithheldTax" if amount_type == "ItemPrice" and desc.startswith("MarketplaceFacilitator") else amount_type
            emit(at, desc, src.get(amt_col))
        for amt_col, desc in (
            ("misc-fee-amount", "MiscFee"),
            ("other-fee-amount", "OtherFee"),
            ("other-amount", "Other"),
        ):
            if amt_col in df.columns:
                emit("ItemFees", desc, src.get(amt_col))
    return pd.DataFrame(rows) if rows else df


def expected_parsed_rows(text: str) -> int:
    """读取前的行数对账基准。

    V2：非空行数 − 1（首行表头；其余每行一条）。
    V1：一行会展开成多条金额行，按「非空金额单元格」计数，不能用源行数。
    """
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return 0
    hdr = [h.strip() for h in lines[0].split("\t")]
    if "amount-type" in hdr or "price-type" not in hdr:
        return max(len(lines) - 1, 0)
    n = 0
    for line in lines[1:]:
        cols = line.split("\t")
        for type_col, amt_col in _V1_AMOUNT_COLS:
            if type_col not in hdr or amt_col not in hdr:
                continue
            ti, ai = hdr.index(type_col), hdr.index(amt_col)
            if ti < len(cols) and ai < len(cols) and cols[ti].strip() and cols[ai].strip():
                n += 1
        for amt_col in _V1_BARE_AMOUNT_COLS:
            if amt_col in hdr:
                ai = hdr.index(amt_col)
                if ai < len(cols) and cols[ai].strip():
                    n += 1
    return n


def read_amz_txt_file(
    file_path: Path,
    *,
    repair_dir: Path | None = None,
    text: str | None = None,
    write_repairs: bool = True,
) -> pd.DataFrame | None:
    file_name = file_path.name
    if not (file_name.upper().startswith("AMZ") and file_name.lower().endswith(".txt")):
        return None
    orig_path = file_path
    if_file_with_issue = False
    repaired_in_memory = False
    if text is None:
        try:
            text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = file_path.read_text(encoding="latin-1")
    lines = text.splitlines(keepends=True)
    if not lines:
        return None
    if check_for_issues(lines):
        if_file_with_issue = True
        fixed_lines = fix_issues_in_txt(lines)
        if write_repairs:
            repair_dir = repair_dir or (file_path.parent / "自动修复sku")
            repair_dir.mkdir(parents=True, exist_ok=True)
            fixed_name = file_name.replace(".txt", "_自动修复sku.txt")
            fixed_path = repair_dir / fixed_name
            fixed_path.write_text("".join(fixed_lines), encoding="utf-8")
            file_path = fixed_path
            file_name = fixed_name
            text = "".join(fixed_lines)
        else:
            # R05：只读模式纯内存修复，不落缓存。
            text = "".join(fixed_lines)
            repaired_in_memory = True

    schema = detect_schema(text)
    if schema in ("xml", "unknown", "empty"):
        raise ValueError(f"{file_name} schema={schema} 无法解析（XML/未知/空文件显式拒绝）")
    header = _header_columns(text)
    missing = missing_required_columns(header, schema)
    if missing:
        raise ValueError(f"{file_name} schema={schema} 缺必需列: {missing}")
    unknown_amount = unknown_amount_columns(header)
    if unknown_amount:
        raise ValueError(f"{file_name} 存在未知金额族列: {unknown_amount}")

    raw_df = pd.read_csv(io.StringIO(text), sep="\t")
    if schema == "v1":
        bad = _v1_rows_with_amount_but_no_type(raw_df)
        if bad:
            head = "; ".join(bad[:5])
            more = f"（另有 {len(bad) - 5} 处）" if len(bad) > 5 else ""
            raise ValueError(f"{file_name} V1 有金额但缺 type {len(bad)} 处: {head}{more}")
    df = _normalize_v1_schema(raw_df)
    amount_cols = [c for c in ("total-amount", "amount") if c in df.columns]
    raw_amounts = {c: df[c].tolist() for c in amount_cols}
    # 区域格式按**单元格**判定（Amazon 欧洲站同一文件会混用 0,04 与 -16.64）。
    for col, raws in raw_amounts.items():
        parsed: list[float | None] = []
        problems: list[str] = []
        for pos, raw in enumerate(raws):
            try:
                parsed.append(parse_amount_strict(raw, decimal_separator="auto"))
            except ValueError as e:
                problems.append(f"行{pos + 2} 原值={raw!r}: {e}")
        if problems:
            head = "; ".join(problems[:5])
            more = f"（另有 {len(problems) - 5} 处）" if len(problems) > 5 else ""
            raise ValueError(f"{file_name} [{col}] 金额解析失败 {len(problems)} 处: {head}{more}")
        df[col] = pd.Series(parsed, index=df.index, dtype="float64")
    amount_format = infer_decimal_format(v for raws in raw_amounts.values() for v in raws)

    # R03：V1 展开前后金额总额守恒（行数由 expected_parsed_rows 另查）。
    if schema == "v1" and not df.empty:
        raw_total = _v1_amount_total_raw(raw_df)
        parsed_total = float(df["amount"].sum())
        if not math.isclose(raw_total, parsed_total, rel_tol=1e-9, abs_tol=1e-6):
            raise ValueError(
                f"{file_name} V1 展开金额不守恒 raw={raw_total:.6f} parsed={parsed_total:.6f}"
            )

    if "currency" in df.columns and df["currency"].notnull().any():
        df["currency"] = df["currency"].ffill()

    account = _account_from_filename(orig_path.name)
    account = convert_amz_last2letter_upper(account)

    if if_file_with_issue:
        sub_folder = orig_path.parent.name
        parent_folder = orig_path.parent.parent.name
    else:
        sub_folder = file_path.parent.name
        parent_folder = file_path.parent.parent.name

    df.insert(0, "父文件夹名", parent_folder)
    df.insert(1, "子文件夹名", sub_folder)
    df.insert(2, "文件名", file_name)
    df.insert(3, "渠道账号", account)
    df.attrs["amount_format"] = amount_format
    df.attrs["amount_cols"] = amount_cols
    df.attrs["schema"] = schema
    df.attrs["repaired_in_memory"] = repaired_in_memory
    return df


# ------------------------------------------------------------ 读桶 + 总账


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def _sniff_is_amz(path: Path) -> bool:
    """读前 64KB 判断是否像 Amazon 结算（二进制文件直接判否）。"""
    try:
        raw = path.read_bytes()[:65536]
    except OSError:
        return False
    if b"\x00" in raw:
        return False
    return looks_like_amz_settlement(_decode(raw))


def _record_tree(ledger: SourceLedger, folder: Path, bucket_dir: Path, *, scope: str) -> None:
    """把一个目录整棵树登记为库存（排除夹/隐藏目录），每个文件都有终态。"""
    rel_dir = str(folder.relative_to(bucket_dir)).replace("\\", "/")
    ledger.add_inventory(rel_dir, kind=KIND_DIR, scope=SCOPE_DIR)
    for p in sorted(folder.rglob("*")):
        rel = str(p.relative_to(bucket_dir)).replace("\\", "/")
        if p.is_dir():
            ledger.add_inventory(rel, kind=KIND_DIR, scope=SCOPE_DIR)
        else:
            try:
                size = p.stat().st_size
            except OSError:
                size = 0
            kind = KIND_NON_AMZ_TXT if p.suffix.lower() == ".txt" else KIND_NON_TXT
            ledger.add_inventory(rel, kind=kind, scope=scope, size=size)


def read_bucket_amz_txts(
    bucket_dir: Path,
    *,
    exclude_folders: tuple[str, ...] = DEFAULT_EXCLUDE_FOLDERS,
    include_folders: tuple[str, ...] | None = None,
    repair_dir: Path | None = None,
    stats_out: dict | None = None,
    period_range: tuple[date, date] | None = None,
    allow_out_of_period: bool = False,
    write_repairs: bool = True,
    ledger_out: SourceLedger | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """扫描一个账期桶，返回 (合并 df, 报告行) 并把文件总账写入 ``stats_out``。

    - 完整枚举根目录 / 一级人名夹 / 更深文件 / 排除夹 / 隐藏目录（R01）；非 AMZ、非 txt
      进 ``INVENTORY`` 清单，疑似结算误名文件记 ``needs_review`` 并阻断发布。
    - 同 md5 同账号只读一份（``SKIP-DUP``）；同 md5 不同账号 → ``needs_review``（R06）。
    - 按 txt 内部 settlement-end-date/deposit-date 的**自然月**判账期：
      错期默认排除（``OUT-OF-PERIOD``），``allow_out_of_period=True`` 强制纳入；
      无内部日期保留行但标记 ``no_period_date``（阻断发布）。
      显式白名单 ``_period_exceptions/{桶名}.txt`` 支持 ``#sha256=`` 绑定与 ``exclude:``。
    - 同 settlement-id 不同字节 / V1+V2 双份 → ``needs_review``（R07）。
    - ``write_repairs=False``：tab 修复纯内存，dry-run 不落任何缓存（R05）。
    - 终态守恒：``files_total = used+dup+failed+out_of_period+approved_excluded+needs_review``。
    """
    import hashlib

    reports: list[str] = []
    dfs: list[pd.DataFrame] = []
    ledger = SourceLedger(bucket_dir.name, str(bucket_dir))
    stats: dict = {
        "bucket": bucket_dir.name,
        "files_total": 0,
        "files_used": 0,
        "files_dup": 0,
        "files_failed": 0,
        "files_out_of_period": 0,
        "files_approved_excluded": 0,
        "files_needs_review": 0,
        "files_no_period_date": 0,
        "rows_total": 0,
        "rows_mismatch": 0,
    }
    if not bucket_dir.is_dir():
        raise FileNotFoundError(bucket_dir)
    if period_range is None:
        period_range = bucket_period_range(bucket_dir.name)
    if period_range is None:
        reports.append(
            f"NO-PERIOD-BUCKET {bucket_dir.name}: 桶名不含账期YYYYMMDD-YYYYMMDD，未做内部结算日窗口校验"
        )
    start = period_range[0] if period_range else None
    bucket_month = start.strftime("%Y%m") if start is not None else None
    cache = repair_dir if repair_dir is not None else (bucket_dir.parent / f".repair_cache_{bucket_dir.name}")
    exceptions = _load_period_exceptions(bucket_dir)

    seen_md5: dict[str, tuple[str, str]] = {}  # md5 -> (rel, account)
    used_sid: dict[str, tuple[str, str, str]] = {}  # sid -> (md5, schema, rel)
    out_of_period_judged = 0

    def _finish(rec: SourceRecord, *, state: str, reason: str | None = None) -> None:
        rec.state = state
        rec.reason = reason
        ledger.add(rec)

    def _classify_outside(path: Path, *, scope: str, scope_reason: str) -> None:
        rel = str(path.relative_to(bucket_dir)).replace("\\", "/")
        suspected = _sniff_is_amz(path)
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        if suspected or (path.name.upper().startswith("AMZ") and path.suffix.lower() == ".txt"):
            rec = SourceRecord(
                bucket=bucket_dir.name,
                rel=rel,
                kind=KIND_AMZ_TXT if path.suffix.lower() == ".txt" else KIND_NON_TXT,
                scope=scope,
                size=size,
                suspected_amz=suspected,
            )
            _finish(
                rec,
                state="needs_review",
                reason=scope_reason if not suspected else f"{scope_reason}+疑似 Amazon 结算内容",
            )
            reports.append(f"NEEDS-REVIEW {rel}: {rec.reason}")
        else:
            kind = KIND_NON_AMZ_TXT if path.suffix.lower() == ".txt" else KIND_NON_TXT
            ledger.add_inventory(rel, kind=kind, scope=scope, size=size)

    def _process_candidate(path: Path, sub_name: str) -> pd.DataFrame | None:
        nonlocal out_of_period_judged
        rel = f"{sub_name}/{path.name}"
        try:
            raw = path.read_bytes()
            size = len(raw)
        except OSError as e:
            rec = SourceRecord(bucket=bucket_dir.name, rel=rel, scope=SCOPE_IN_SCOPE)
            _finish(rec, state=STATE_FAILED, reason=str(e))
            reports.append(f"FAIL {rel}: {e}")
            return None
        account = convert_amz_last2letter_upper(_account_from_filename(path.name))
        rec = SourceRecord(
            bucket=bucket_dir.name,
            rel=rel,
            kind=KIND_AMZ_TXT,
            scope=SCOPE_IN_SCOPE,
            size=size,
            account=account,
        )
        if size == 0 or not raw.strip():
            _finish(rec, state=STATE_FAILED, reason="EMPTY-FILE")
            reports.append(f"FAIL {rel}: 空文件")
            return None
        text = _decode(raw)
        schema = detect_schema(text)
        rec.schema = schema
        if schema in ("xml", "unknown", "empty"):
            _finish(rec, state=STATE_FAILED, reason=f"SCHEMA-{schema.upper()}")
            reports.append(f"FAIL {rel}: schema={schema} 显式拒绝")
            return None
        header = _header_columns(text)
        missing = missing_required_columns(header, schema)
        if missing:
            _finish(rec, state=STATE_FAILED, reason=f"MISSING-COLUMNS {missing}")
            reports.append(f"FAIL {rel} 缺必需列: {missing}")
            return None
        unknown_amount = unknown_amount_columns(header)
        if unknown_amount:
            _finish(rec, state=STATE_FAILED, reason=f"UNKNOWN-AMOUNT-COLS {unknown_amount}")
            reports.append(f"FAIL {rel} 未知金额族列: {unknown_amount}")
            return None

        md5 = hashlib.md5(raw).hexdigest()
        rec.md5 = md5
        rec.sha256 = hashlib.sha256(raw).hexdigest()
        meta = settlement_meta(text)
        rec.settlement_id = meta["settlement_id"]

        # R08 跨期 / 无内部日期
        window_date, end_date, deposit_date = settlement_window_date(text)
        check_date = end_date or deposit_date
        if bucket_month is not None:
            if check_date is None:
                rec.no_period_date = True
                reports.append(
                    f"NO-PERIOD-DATE {rel}（内部 settlement-end-date / deposit-date 缺失，无法校验账期月）"
                )
            elif check_date.strftime("%Y%m") != bucket_month:
                spec = exceptions.get(rel)
                if spec:
                    bound = spec.get("sha256")
                    hash_ok = bound is None or bound == rec.sha256
                    if not hash_ok:
                        out_of_period_judged += 1
                        _finish(
                            rec,
                            state="needs_review",
                            reason=(
                                f"PERIOD-EXCEPTION-HASH-MISMATCH month={bucket_month} "
                                f"end={end_date.isoformat() if end_date else '-'}"
                            ),
                        )
                        reports.append(
                            f"NEEDS-REVIEW {rel}: 跨期例外绑定的 sha256 与当前文件不符（例外失效）"
                        )
                        return None
                    if spec.get("action") == "exclude":
                        if not bound:
                            _finish(
                                rec,
                                state="needs_review",
                                reason="EXCLUDE-WITHOUT-HASH（批准排除必须绑定文件 sha256）",
                            )
                            reports.append(
                                f"NEEDS-REVIEW {rel}: exclude 例外未绑定 sha256，视为未核实"
                            )
                            return None
                        out_of_period_judged += 1
                        _finish(
                            rec,
                            state=STATE_APPROVED_EXCLUDED,
                            reason="approved exclude（跨期白名单）",
                        )
                        rec.approval = f"period_exception:exclude:{bound or 'no-hash'}"
                        reports.append(
                            f"APPROVED-EXCLUDED {rel} month={bucket_month} "
                            f"end={end_date.isoformat() if end_date else '-'}（显式排除）"
                        )
                        return None
                    rec.approval = f"period_exception:include:{bound or 'no-hash'}"
                    reports.append(
                        f"OUT-OF-PERIOD-ALLOWED {rel} month={bucket_month} "
                        f"end={end_date.isoformat() if end_date else '-'}（显式白名单）"
                    )
                elif not allow_out_of_period:
                    out_of_period_judged += 1
                    _finish(
                        rec,
                        state=STATE_OUT_OF_PERIOD,
                        reason=(
                            f"OUT-OF-PERIOD month={bucket_month} "
                            f"end={end_date.isoformat() if end_date else '-'} "
                            f"deposit={deposit_date.isoformat() if deposit_date else '-'}"
                        ),
                    )
                    reports.append(
                        f"OUT-OF-PERIOD {rel} month={bucket_month} "
                        f"end={end_date.isoformat() if end_date else '-'} "
                        f"deposit={deposit_date.isoformat() if deposit_date else '-'}"
                    )
                    return None
                else:
                    out_of_period_judged += 1
                    rec.out_of_period = True
                    reports.append(
                        f"OUT-OF-PERIOD-ALLOWED {rel} month={bucket_month} "
                        f"end={end_date.isoformat() if end_date else '-'}（--allow-out-of-period）"
                    )

        # R06 md5 去重 + 不同账号同内容
        prior = seen_md5.get(md5)
        if prior is not None:
            prior_rel, prior_account = prior
            if prior_account == account:
                _finish(rec, state=STATE_DUP, reason=f"SKIP-DUP == {prior_rel}")
                reports.append(f"SKIP-DUP {rel} == {prior_rel}")
                return None
            _finish(
                rec,
                state="needs_review",
                reason=f"SAME-MD5-DIFFERENT-ACCOUNT {prior_rel}({prior_account}) vs {account}",
            )
            reports.append(f"NEEDS-REVIEW {rel}: 与 {prior_rel} 内容相同但渠道账号不同")
            return None

        # R07 同 settlement-id 多版本 / V1+V2 双份
        sid = rec.settlement_id
        if sid and sid in used_sid:
            prior_md5, prior_schema, prior_rel = used_sid[sid]
            if prior_md5 != md5:
                tag = "V1+V2-DUAL" if {prior_schema, schema} == {"v1", "v2"} else "SID-MULTIPLE-VERSIONS"
                _finish(
                    rec,
                    state="needs_review",
                    reason=f"{tag} settlement-id={sid} 先前={prior_rel} md5={prior_md5[:8]}",
                )
                reports.append(f"NEEDS-REVIEW {rel}: 同结算号 {sid} 不同内容（{tag}）")
                return None

        try:
            df = read_amz_txt_file(path, repair_dir=cache, text=text, write_repairs=write_repairs)
        except Exception as e:
            _finish(rec, state=STATE_FAILED, reason=str(e))
            reports.append(f"FAIL {rel}: {e}")
            return None
        if df is None:
            _finish(rec, state=STATE_FAILED, reason="无法解析（非 AMZ 结算 txt）")
            reports.append(f"FAIL {rel}: 无法解析")
            return None
        if df.empty:
            _finish(rec, state=STATE_FAILED, reason="NO-DATA-ROWS")
            reports.append(f"FAIL {rel}: 无数据行")
            return None

        seen_md5[md5] = (rel, account)
        if sid:
            used_sid[sid] = (md5, schema, rel)
        rec.currency = (
            str(df["currency"].dropna().iloc[0]) if "currency" in df.columns and df["currency"].notna().any() else None
        )
        rec.rows_expected = expected_parsed_rows(text)
        rec.rows_parsed = int(len(df))
        if "amount" in df.columns:
            rec.amount_total = float(df["amount"].fillna(0).sum())
        rec.state = STATE_USED
        ledger.add(rec)
        if rec.rows_expected != rec.rows_parsed:
            stats["rows_mismatch"] += 1
            reports.append(
                f"FAIL {rel} rows-mismatch file={rec.rows_expected} parsed={rec.rows_parsed}"
            )
        stats["rows_total"] += len(df)
        fmt = df.attrs.get("amount_format") or "?"
        extra = " (内存修复 tab，未落缓存)" if df.attrs.get("repaired_in_memory") else ""
        reports.append(f"OK {rel} rows={len(df)} acct={account} fmt={fmt}{extra}")
        return df

    for entry in sorted(bucket_dir.iterdir()):
        if entry.is_dir():
            if entry.name.startswith("."):
                _record_tree(ledger, entry, bucket_dir, scope=SCOPE_HIDDEN_DIR)
                continue
            if (exclude_folders and entry.name in exclude_folders) or (
                include_folders and entry.name not in include_folders
            ):
                _record_tree(ledger, entry, bucket_dir, scope=SCOPE_EXCLUDED_FOLDER)
                continue
            for p in sorted(entry.rglob("*")):
                if p.is_dir():
                    continue
                depth = len(p.relative_to(entry).parts)
                if depth > 1:
                    _classify_outside(p, scope=SCOPE_NESTED_FILE, scope_reason="深层目录文件，未按一级人名夹读取")
                elif p.is_file():
                    if p.name.lower().endswith(".txt") and p.name.upper().startswith("AMZ"):
                        df = _process_candidate(p, entry.name)
                        if df is not None:
                            dfs.append(df)
                    else:
                        _classify_outside(p, scope=SCOPE_OTHER_FILE, scope_reason="非 AMZ txt（命名不符）")
        elif entry.is_file():
            _classify_outside(entry, scope=SCOPE_ROOT_FILE, scope_reason="根目录文件（不在人名夹内）")

    # 冻结统计（终态守恒强校验）
    part = ledger.partition()
    no_date = sum(1 for r in ledger.candidates if r.no_period_date and r.state == STATE_USED)
    blockers = ledger.publish_blockers()
    if stats["rows_mismatch"]:
        blockers.append(f"rows_mismatch={stats['rows_mismatch']}")
    stats.update(
        {
            "files_total": len(ledger.candidates),
            "files_used": part[STATE_USED],
            "files_dup": part[STATE_DUP],
            "files_failed": part[STATE_FAILED],
            "files_out_of_period": out_of_period_judged,
            "files_approved_excluded": part[STATE_APPROVED_EXCLUDED],
            "files_needs_review": part["needs_review"],
            "files_no_period_date": no_date,
            "partition": part,
            "inventory": ledger.inventory_partition(),
            "publish_blockers": blockers,
        }
    )
    ledger.assert_conservation()
    reports.extend(ledger.summary_lines())
    if stats_out is not None:
        stats_out.update(stats)
    if ledger_out is not None:
        # 让调用方持有同一份账本（对象，不进入 JSON 报告）
        ledger_out.bucket = ledger.bucket
        ledger_out.bucket_dir = ledger.bucket_dir
        ledger_out.records = ledger.records

    if not dfs:
        return pd.DataFrame(), reports
    return pd.concat(dfs, axis=0, ignore_index=True, sort=False), reports
