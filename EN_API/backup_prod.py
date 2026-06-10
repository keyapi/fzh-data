# -*- coding: utf-8 -*-
"""EN 生产系统物料组完整备份 + 结构报告。

功能:
  1. 全量备份所有物料组（JSON，含完整字段）
  2. 生成树结构报告（Excel 多维度）
  3. 生成可恢复的 RESTORE 脚本

使用:
  python backup_prod.py                           # 备份 + 报告
  python backup_prod.py --restore-script          # 仅从已有备份生成恢复脚本
"""
from __future__ import annotations

import json
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pandas as pd
import requests
from requests.adapters import HTTPAdapter

_DIR = Path(__file__).resolve().parent
os.chdir(_DIR)
_DIR_OUT = _DIR / "out"
_DIR_OUT.mkdir(parents=True, exist_ok=True)


def _load_dotenv(candidates: list[Path]) -> None:
    for p in candidates:
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                v = v[1:-1]
            os.environ.setdefault(k, v)


_load_dotenv([
    _DIR / ".env", _DIR.parent / ".env", _DIR.parent.parent / ".env",
    _DIR.parent / "tongtool_bundle_to_en" / ".env",
])


class _NoExpectAdapter(HTTPAdapter):
    def send(self, request, **kwargs):
        request.headers.pop("Expect", None)
        return super().send(request, **kwargs)


class ErpnextClient:
    def __init__(self, base_url: str, api_key: str, api_secret: str,
                 label: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.label = label or base_url
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"token {api_key}:{api_secret}"
        self.session.mount("https://", _NoExpectAdapter())
        self.session.mount("http://", _NoExpectAdapter())

    def fetch_all(self, fields: list[str] | None = None) -> list[dict[str, Any]]:
        """获取全部物料组。fields=None 返回全部字段。"""
        url = f"{self.base_url}/api/resource/Item Group"
        params: dict = {"limit_page_length": "0"}
        if fields is not None:
            params["fields"] = json.dumps(fields)
        else:
            params["limit"] = "0"  # 全部字段
        resp = self._request("GET", url, params=params)
        return resp.json().get("data", [])

    def _request(self, method: str, url: str, *,
                 retries: int = 2, retry_delay: float = 3.0,
                 **kwargs: Any) -> requests.Response:
        timeout = kwargs.pop("timeout", (60, 120))
        last = None
        for a in range(retries + 1):
            try:
                r = self.session.request(method, url, timeout=timeout, **kwargs)
                r.raise_for_status()
                return r
            except requests.RequestException as e:
                last = e
                if a < retries:
                    time.sleep(retry_delay)
        raise last


# ── 工具 ──
def build_index(data: list[dict]) -> dict[str, dict]:
    return {d["name"]: d for d in data if d.get("name")}


def get_tree_depth(node_name: str, idx: dict[str, dict]) -> int:
    depth = 1
    parent = idx.get(node_name, {}).get("parent_item_group", "")
    visited = set()
    while parent and parent in idx and parent not in visited:
        depth += 1
        visited.add(parent)
        parent = idx[parent].get("parent_item_group", "")
    return depth


def get_ancestors(node_name: str, idx: dict[str, dict]) -> list[str]:
    parts = [node_name]
    parent = idx.get(node_name, {}).get("parent_item_group", "")
    visited = set()
    while parent and parent in idx and parent not in visited:
        parts.insert(0, parent)
        visited.add(parent)
        parent = idx[parent].get("parent_item_group", "")
    return parts


def get_descendants(parent_name: str, idx: dict[str, dict],
                    data: list[dict]) -> list[dict]:
    result = []
    stack = [parent_name]
    while stack:
        name = stack.pop()
        node = idx.get(name)
        if node:
            result.append(node)
            for d in data:
                if d.get("parent_item_group") == name and d["name"] != name:
                    stack.append(d["name"])
    return result


# ── 备份 ──
def backup_production(client: ErpnextClient, out_dir: Path) -> dict[str, Any]:
    """全量备份生产系统物料组（两步：先轻量字段列表，再补充全部字段）。"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"\n── 备份 {client.label} ──")

    # Step 1: 获取关键字段列表（快速）
    core_fields = [
        "name", "item_group_name", "parent_item_group", "is_group",
        "image", "custom_model_id",
    ]
    data = client.fetch_all(core_fields)
    print(f"  物料组总数: {len(data)}")

    # Step 2: 分批获取更多字段（避免 URL 超长）
    extra_field_batches = [
        ["name", "icon", "color", "route", "is_website_route", "slideshow"],
        ["name", "description", "is_attribute_item_group", "website_image", "website_banner"],
        ["name", "website_specifications", "section_header", "item_group_defaults"],
        ["name", "taxes", "payment_terms", "creation", "modified", "modified_by", "owner", "idx", "docstatus"],
    ]
    all_field_map: dict[str, dict] = {}
    for batch in extra_field_batches:
        try:
            batch_data = client.fetch_all(batch)
            for d in batch_data:
                all_field_map.setdefault(d["name"], {}).update(d)
        except requests.RequestException:
            pass  # 降级，忽略该批次
    print(f"  扩展字段记录: {len(all_field_map)}")

    # 合并：核心字段 + 扩展字段
    merged = []
    for d in data:
        full = all_field_map.get(d["name"], {})
        merged.append({**full, **d})

    # Step 3: 写入备份 JSON
    backup = {
        "metadata": {
            "backup_time": datetime.now().isoformat(),
            "environment": client.label,
            "total_count": len(merged),
            "fields_included": list(merged[0].keys()) if merged else [],
            "description": "EN 生产系统物料组全量备份",
        },
        "records": merged,
    }
    backup_file = out_dir / f"生产系统备份_全量_{ts}.json"
    with open(backup_file, "w", encoding="utf-8") as f:
        json.dump(backup, f, ensure_ascii=False, indent=2)
    print(f"  备份文件: {backup_file.name} ({os.path.getsize(backup_file) / 1024:.0f} KB)")

    return {
        "backup_file": backup_file,
        "total": len(merged),
        "data": merged,
        "timestamp": ts,
        "all_fields": list(merged[0].keys()) if merged else [],
    }


# ── 报告 ──
def generate_report(result: dict[str, Any], out_dir: Path,
                    label: str = "生产系统") -> Path:
    """生成树结构报告。"""
    data = result["data"]
    idx = build_index(data)
    ts = result["timestamp"]

    by_parent: dict[str, list[dict]] = {}
    for d in data:
        by_parent.setdefault(d.get("parent_item_group") or "", []).append(d)

    groups = [d for d in data if d.get("is_group")]
    leaves = [d for d in data if not d.get("is_group")]
    roots = [d for d in data if not d.get("parent_item_group")]
    with_model = [d for d in data if d.get("custom_model_id")]
    without_model = [d for d in data if not d.get("custom_model_id")]

    summary = [
        {"指标": "环境", "值": label},
        {"指标": "物料组总数", "值": len(data)},
        {"指标": "组节点 (is_group=1)", "值": len(groups)},
        {"指标": "叶子节点 (is_group=0)", "值": len(leaves)},
        {"指标": "根节点数", "值": len(roots)},
        {"指标": "有 custom_model_id", "值": len(with_model)},
        {"指标": "无 custom_model_id", "值": len(without_model)},
        {"指标": "备份字段数", "值": len(result.get("all_fields", []))},
        {"指标": "报告生成时间", "值": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
    ]
    for r in roots:
        sub = get_descendants(r["name"], idx, data)
        summary.append({"指标": f"  子树「{r['name']}」", "值": f"{len(sub)} 个节点"})

    # 节点清单
    rows = []
    for d in data:
        depth = get_tree_depth(d["name"], idx)
        path = " / ".join(get_ancestors(d["name"], idx))
        children = [x for x in data if x.get("parent_item_group") == d["name"]]

        model_id = str(d.get("custom_model_id") or "")
        if model_id.lower() in ("nan", "none", ""):
            model_id = ""

        rows.append({
            "名称": d["name"],
            "物料组名": d.get("item_group_name", ""),
            "父级": d.get("parent_item_group", ""),
            "深度": depth,
            "完整路径": path,
            "类型": "组" if d.get("is_group") else "叶子",
            "custom_model_id": model_id,
            "有图片": "是" if d.get("image") else "否",
            "子节点数": len(children),
            "组子节点": len([c for c in children if c.get("is_group")]),
            "叶子子节点": len([c for c in children if not c.get("is_group")]),
        })

    # 深度分布
    depth_stats: dict = {}
    for d in data:
        dep = get_tree_depth(d["name"], idx)
        depth_stats.setdefault(dep, {"组": 0, "叶子": 0})
        depth_stats[dep]["组" if d.get("is_group") else "叶子"] += 1

    depth_rows = [
        {"深度": d, "组节点": v["组"], "叶子节点": v["叶子"], "合计": v["组"] + v["叶子"]}
        for d, v in sorted(depth_stats.items())
    ]

    # 父级分组
    parent_rows = []
    for p, children in sorted(by_parent.items()):
        parent_name = p if p else "(根)"
        parent_rows.append({
            "父级": parent_name, "子节点数": len(children),
            "组": len([c for c in children if c.get("is_group")]),
            "叶子": len([c for c in children if not c.get("is_group")]),
        })

    report_path = out_dir / f"{label}物料组结构报告_{ts}.xlsx"
    with pd.ExcelWriter(report_path, engine="openpyxl") as writer:
        pd.DataFrame(summary).to_excel(writer, sheet_name="汇总", index=False)
        pd.DataFrame(rows).to_excel(writer, sheet_name="节点清单", index=False)
        pd.DataFrame(depth_rows).to_excel(writer, sheet_name="深度分布", index=False)
        pd.DataFrame(parent_rows).to_excel(writer, sheet_name="父级分组", index=False)

    print(f"  结构报告: {report_path.name}")
    return report_path


# ── 恢复脚本生成 ──
def generate_restore_script(backup_file: Path, out_dir: Path, ts: str) -> Path:
    """从备份 JSON 生成独立可执行的恢复脚本。"""
    with open(backup_file, "r", encoding="utf-8") as f:
        backup = json.load(f)

    records = backup.get("records", [])
    record_map = {r["name"]: r for r in records}

    # 给每条记录计算深度（用于排序）
    for r in records:
        depth = 1
        parent = r.get("parent_item_group", "")
        visited = set()
        while parent and parent in record_map and parent not in visited:
            depth += 1
            visited.add(parent)
            parent = record_map[parent].get("parent_item_group", "")
        r["_sort_depth"] = depth

    # 按深度排序（根先叶后）
    records_sorted = sorted(records, key=lambda r: (r["_sort_depth"], r.get("item_group_name", "")))

    # 嵌入 JSON 数据到脚本
    data_json = json.dumps(records_sorted, ensure_ascii=False)

    script_path = out_dir / f"restore_prod_to_test_{ts}.py"
    script_content = f'''# -*- coding: utf-8 -*-
"""恢复脚本：将生产系统备份恢复到目标环境。

用法:
  python restore_prod_to_test_{ts}.py              # 恢复到测试系统
  python restore_prod_to_test_{ts}.py --dry-run     # 预览
  python restore_prod_to_test_{ts}.py --target URL   # 指定目标

备份信息:
  生成时间: {backup["metadata"]["backup_time"]}
  源环境: {backup["metadata"]["environment"]}
  节点数: {len(records_sorted)}
"""

from __future__ import annotations
import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter

_DIR = Path(__file__).resolve().parent
os.chdir(_DIR)


class _NoExpectAdapter(HTTPAdapter):
    def send(self, request, **kwargs):
        request.headers.pop("Expect", None)
        return super().send(request, **kwargs)


class ErpnextClient:
    def __init__(self, base_url, api_key, api_secret):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"token {{api_key}}:{{api_secret}}"
        self.session.mount("https://", _NoExpectAdapter())

    def create_item_group(self, data):
        return self._request("POST",
            f"{{self.base_url}}/api/resource/Item Group",
            json=data).json().get("data", {{}})

    def update_item_group(self, name, fields):
        safe = quote(name, safe="")
        return self._request("PUT",
            f"{{self.base_url}}/api/resource/Item Group/{{safe}}",
            json=fields).json().get("data", {{}})

    def _request(self, method, url, **kwargs):
        kwargs.setdefault("timeout", (30, 120))
        for a in range(3):
            try:
                r = self.session.request(method, url, **kwargs)
                r.raise_for_status()
                return r
            except requests.RequestException as e:
                if a < 2:
                    time.sleep(3)
                else:
                    raise


def load_env():
    for p in [_DIR / ".env", _DIR.parent / ".env",
              _DIR.parent.parent / ".env"]:
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
                v = v[1:-1]
            os.environ.setdefault(k, v)


def main():
    import argparse
    ap = argparse.ArgumentParser(description="恢复生产系统备份")
    ap.add_argument("--dry-run", action="store_true", help="预览操作")
    ap.add_argument("--target", default="https://ensh.vilavi.cn",
                    help="目标环境 URL（默认测试系统）")
    ap.add_argument("--batch-delay", type=float, default=0.3,
                    help="请求间隔秒数")
    args = ap.parse_args()

    load_env()
    api_key = os.getenv("TEST_ERP_API_KEY", "")
    api_secret = os.getenv("TEST_ERP_API_SECRET", "")
    if not api_key or not api_secret:
        print("错误: 请设置 TEST_ERP_API_KEY / TEST_ERP_API_SECRET")
        return 1

    client = ErpnextClient(args.target, api_key, api_secret)

    # 读取嵌入的备份数据
    records = _load_records()
    print(f"待处理节点: {{len(records)}}")
    print(f"目标环境: {{args.target}}")
    if args.dry_run:
        print("模式: DRY-RUN\\n")

    ok = fail = 0
    for i, r in enumerate(records):
        name = r.get("name", "")
        ig_name = r.get("item_group_name", "")
        parent = r.get("parent_item_group", "")
        is_group = r.get("is_group", 0)

        if args.dry_run:
            if i < 5 or i >= len(records) - 2:
                print(f"  [DRY] {{'组' if is_group else '叶'}} {{ig_name}} "
                      f"(parent={{parent or '无'}})")
            elif i == 5:
                print(f"  ... 共 {{len(records)}} 个, 仅显示首尾")
            continue

        try:
            payload = {{
                "item_group_name": ig_name,
                "parent_item_group": parent,
                "is_group": is_group,
            }}
            if r.get("custom_model_id"):
                payload["custom_model_id"] = r["custom_model_id"]
            if r.get("image"):
                payload["image"] = r["image"]

            try:
                client.create_item_group(payload)
            except requests.RequestException:
                # 已存在，更新字段
                client.update_item_group(name, payload)

            if i == 0 or (i + 1) % 500 == 0 or i == len(records) - 1:
                print(f"    进度: {{i+1}}/{{len(records)}}")
            ok += 1
            time.sleep(args.batch_delay)
        except Exception as e:
            print(f"  [FAIL] {{ig_name}} ({{name}}): {{e}}")
            fail += 1

    print(f"\\n完成: 成功={{ok}}, 失败={{fail}}")
    return 0 if fail == 0 else 1


def _load_records():
    """从脚本内嵌的 JSON 数据加载记录。"""
    # 数据在 # RECORDS_START / # RECORDS_END 之间
    lines = __doc__.split("\\n")
    # 实际数据通过文件尾部嵌入
    import inspect
    src = inspect.getsource(_load_records)
    # 直接读取自身文件
    with open(__file__, "r", encoding="utf-8") as f:
        content = f.read()
    start = content.find("# RECORDS_START")
    end = content.find("# RECORDS_END")
    if start == -1 or end == -1:
        print("错误: 未找到嵌入的备份数据")
        return []
    return json.loads(content[start + len("# RECORDS_START"):end])


if __name__ == "__main__":
    raise SystemExit(main())


# RECORDS_START
{data_json}
# RECORDS_END
'''
    script_path.write_text(script_content, encoding="utf-8")
    print(f"  恢复脚本: {script_path.name}")
    return script_path


# ── 主入口 ──
def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="生产系统物料组备份 + 报告")
    ap.add_argument("--restore-script", type=Path, default=None,
                    help="从已有备份 JSON 生成恢复脚本（跳过备份）")
    args = ap.parse_args()

    out_dir = _DIR_OUT
    out_dir.mkdir(parents=True, exist_ok=True)

    # 从已有备份生成恢复脚本
    if args.restore_script:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        if not args.restore_script.exists():
            print(f"错误: 备份文件不存在: {args.restore_script}")
            return 1
        generate_restore_script(args.restore_script, out_dir, ts)
        return 0

    # 完整备份流程
    prod_key = os.getenv("PROD_ERP_API_KEY", "")
    prod_secret = os.getenv("PROD_ERP_API_SECRET", "")
    if not prod_key or not prod_secret:
        print("错误: 请设置 PROD_ERP_API_KEY / PROD_ERP_API_SECRET")
        return 1

    prod_client = ErpnextClient(
        "https://erpnext.vilavi.cn", prod_key, prod_secret, label="生产系统",
    )

    # 1. 备份
    result = backup_production(prod_client, out_dir)

    # 2. 生成结构报告
    generate_report(result, out_dir, "生产系统")

    # 3. 归档备份
    backup_dir = out_dir / "备份归档"
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(result["backup_file"], backup_dir / result["backup_file"].name)

    # 4. 生成恢复脚本
    generate_restore_script(result["backup_file"], out_dir, result["timestamp"])

    print(f"\n[OK] 备份完成！")
    print(f"  备份文件: {result['backup_file'].name}")
    print(f"  恢复脚本: restore_prod_to_test_{result['timestamp']}.py")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
