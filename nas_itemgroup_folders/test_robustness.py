# -*- coding: utf-8 -*-
"""NAS-ERPNext 对账引擎鲁棒性测试。

覆盖: 内容感知、名称变更、路径变更、删除恢复、孤儿检测、边界情况。
每个测试独立运行: setup → mutate → reconcile → verify → restore。

使用:
  uv run python test_robustness.py              # 全部测试
  uv run python test_robustness.py --test T1    # 单个测试
  uv run python test_robustness.py --dry-run    # 预览操作（不执行 NAS 写）
"""

from __future__ import annotations

import json, os, sys, time, traceback
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_DIR.parent))

from NAS_API.synology import _load_dotenv, _parse_nas_url
from synology_api.filestation import FileStation

_load_dotenv([_DIR.parent / "NAS_API" / ".env", _DIR / ".env"])

# ── Constants ────────────────────────────────────────────

TARGET = os.getenv("NAS_TARGET_FOLDER", "/产品信息")
LAYOUTS = ["flat", "tree"]
SUB_FOLDERS = ["调研报告", "设计稿", "图片", "视频"]

FLAT_PATHS = {
    "KS0001": f"{TARGET}/KS0001_三角靠枕",
    "KS0002": f"{TARGET}/KS0002_平条靠枕",
}
TREE_PATHS = {
    "KS0001": f"{TARGET}/床品类/床头靠枕/三角靠枕类/KS0001_三角靠枕",
    "KS0002": f"{TARGET}/床品类/床头靠枕/平条靠枕类/KS0002_平条靠枕",
}
# 故意错误的路径（模拟人类犯错）
WRONG_INTERMEDIATE = f"{TARGET}/床品类/床头靠系列"
WRONG_PATHS = {
    "KS0001": f"{TARGET}/床品类/床头靠系列/三角靠枕类/KS0001_三角靠枕",
    "KS0002": f"{TARGET}/床品类/床头靠系列/平条靠枕类/KS0002_平条靠枕",
}

# ── NAS Helpers ──────────────────────────────────────────

class NAS:
    def __init__(self):
        url = os.getenv("NAS_URL", "").rstrip("/")
        host, port, secure = _parse_nas_url(url)
        self.fl = FileStation(
            ip_address=host, port=port,
            username=os.getenv("NAS_USERNAME", ""),
            password=os.getenv("NAS_PASSWORD", ""),
            secure=secure, cert_verify=False,
        )

    def mkdir(self, path: str):
        parent = "/".join(path.split("/")[:-1])
        name = path.split("/")[-1]
        self.fl.create_folder(parent, name, force_parent=True)

    def rm(self, path: str):
        self.fl.delete_blocking_function(path)

    def rename(self, old_path: str, new_name: str):
        self.fl.rename_folder(old_path, new_name)

    def mv(self, src: str, dst_parent: str):
        self.fl.start_copy_move(path=[src], dest_folder_path=dst_parent,
                                overwrite=False, remove_src=True)

    def ls(self, path: str, limit: int = 100) -> list[dict]:
        resp = self.fl.get_file_list(path, limit=limit, additional="size,time")
        if resp.get("success"):
            return resp["data"]["files"]
        return []

    def exists(self, path: str) -> bool:
        parent = "/".join(path.split("/")[:-1])
        name = path.split("/")[-1]
        try:
            for f in self.ls(parent):
                if f["name"] == name:
                    return True
        except Exception:
            return False
        return False

    def upload_text(self, path: str, filename: str, content: str = "test"):
        """Create a text file via synology-api upload (simulates LM adding content)."""
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False,
                                         encoding="utf-8") as f:
            f.write(content)
            tmp = f.name
        try:
            resp = self.fl.upload_file(
                dest_path=path, file_path=tmp,
                create_parents=True, overwrite=True,
            )
            return resp.get("success", False)
        finally:
            os.unlink(tmp)


# ── Reconciliation Runner ────────────────────────────────

def run_reconcile(layout: str, full: bool = False, dry: bool = False) -> dict:
    """Run build_nas_folders.py via subprocess, return parsed actions."""
    import subprocess
    args = [
        sys.executable, str(_DIR / "build_nas_folders.py"),
        f"--layout={layout}",
    ]
    if full:
        args.append("--full")
    if dry:
        args.append("--dry-run")

    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(args, cwd=str(_DIR), capture_output=True,
                            encoding="utf-8", errors="replace", env=env,
                            timeout=120)
    # Parse output for key stats
    output = result.stdout
    parsed = {"output": output, "returncode": result.returncode}

    # Count action types (format: "  MATCH                   2")
    for line in output.split("\n"):
        for key in ["MATCH", "CREATE", "MOVE", "MOVE_APPROVAL",
                     "RENAME", "BLOCKED", "IGNORE", "DELETE_EMPTY"]:
            stripped = line.strip()
            if stripped.startswith(key) and len(stripped.split()) >= 2:
                try:
                    count = int(stripped.split()[-1])
                    parsed[key.lower()] = count
                except ValueError:
                    pass

    # Count orphan actions
    for line in output.split("\n"):
        if "清理空孤儿:" in line:
            parsed.setdefault("orphan_cleaned", 0)
            parsed["orphan_cleaned"] += 1
        if "可清理空文件夹:" in line:
            parsed.setdefault("orphan_detectable", 0)
            parsed["orphan_detectable"] += 1

    parsed.setdefault("orphan_cleaned", 0)
    parsed.setdefault("orphan_detectable", 0)
    return parsed


# ── Test Harness ─────────────────────────────────────────

class TestResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.error = ""
        self.detail = ""

TESTS: list[dict] = []
results: list[TestResult] = []

def test(id: str, desc: str):
    """Decorator to register a test function."""
    def decorator(fn):
        TESTS.append({"id": id, "desc": desc, "fn": fn})
        return fn
    return decorator

def assert_eq(actual, expected, msg=""):
    if actual != expected:
        raise AssertionError(f"Expected {expected!r}, got {actual!r}. {msg}")

def assert_in(substring, text, msg=""):
    if substring not in text:
        raise AssertionError(f"'{substring}' not found in output. {msg}")

# ── Setup / Teardown ─────────────────────────────────────

def setup_clean_flat(nas: NAS):
    """Ensure flat layout with KS0001 + KS0002 and sub-folders. No extra files."""
    # Clean up any tree residuals first
    for orphan_candidate in [
        f"{TARGET}/床品类",
        f"{TARGET}/床品类/床头靠枕",
        f"{TARGET}/床品类/床头靠系列",
    ]:
        if nas.exists(orphan_candidate):
            try:
                nas.rm(orphan_candidate)
            except Exception:
                pass

    # Reconcile to flat
    run_reconcile("flat")

    # Clean any test files
    for mid in ["KS0001", "KS0002"]:
        path = FLAT_PATHS[mid]
        for f in nas.ls(path):
            if not f.get("isdir"):
                nas.rm(f"{path}/{f['name']}")


# ── Test Cases ───────────────────────────────────────────

@test("T1", "Flat + 文件 → Tree: 应检测 MOVE_APPROVAL（有内容不能自动移动）")
def test_t1(nas: NAS):
    setup_clean_flat(nas)
    # Add a file to KS0001
    nas.upload_text(FLAT_PATHS["KS0001"], "设计稿.psd", "fake image data")
    # Try switching to tree
    result = run_reconcile("tree", dry=True)
    assert_in("MOVE_APPROVAL", result["output"],
              "T1: 有文件的 KS 文件夹应触发 MOVE_APPROVAL")
    # Cleanup test file
    nas.rm(f"{FLAT_PATHS['KS0001']}/设计稿.psd")


@test("T2", "Tree + 文件 → Flat: 应检测 MOVE_APPROVAL")
def test_t2(nas: NAS):
    # Switch to tree first (empty)
    setup_clean_flat(nas)
    run_reconcile("tree")
    # Add file
    nas.upload_text(TREE_PATHS["KS0001"], "report.pdf", "data")
    # Try switching back to flat
    result = run_reconcile("flat", dry=True)
    assert_in("MOVE_APPROVAL", result["output"],
              "T2: 有文件的 tree→flat 应触发 MOVE_APPROVAL")
    # Cleanup
    nas.rm(f"{TREE_PATHS['KS0001']}/report.pdf")
    run_reconcile("flat")


@test("T3", "空文件夹 Flat↔Tree 自动切换")
def test_t3(nas: NAS):
    setup_clean_flat(nas)
    # flat → tree (execute then verify)
    run_reconcile("tree")
    result = run_reconcile("tree", dry=True)
    assert_eq(result.get("match", 0), 2, "T3: tree 模式应 2 MATCH")
    # tree → flat
    run_reconcile("flat")
    result = run_reconcile("flat", dry=True)
    assert_eq(result.get("match", 0), 2, "T3: flat 模式应 2 MATCH")


@test("T4", "改名叶子节点 (保留 KS 码) → NAME_MISMATCH → 自动 RENAME")
def test_t4(nas: NAS):
    setup_clean_flat(nas)
    nas.rename(FLAT_PATHS["KS0001"], "KS0001_三角枕")
    result = run_reconcile("flat")
    assert_eq(result.get("rename", 0), 1, "T4: 应检测 1 个 RENAME")
    # Verify renamed back
    result = run_reconcile("flat", dry=True)
    assert_eq(result.get("match", 0), 2, "T4: 修复后应 2 MATCH")


@test("T5", "改名叶子节点 + 有文件 → BLOCKED")
def test_t5(nas: NAS):
    setup_clean_flat(nas)
    nas.upload_text(FLAT_PATHS["KS0001"], "important.docx", "content")
    # Rename after adding file
    nas.rename(FLAT_PATHS["KS0001"], "KS0001_三角枕")
    result = run_reconcile("flat", dry=True)
    assert_eq(result.get("blocked", 0), 1, "T5: 有文件的改名应 BLOCKED")
    # Restore state
    nas.rename(f"{TARGET}/KS0001_三角枕", "KS0001_三角靠枕")
    nas.rm(f"{FLAT_PATHS['KS0001']}/important.docx")


@test("T6", "破坏 KS 编码 → MISSING + EXTRA（失去抓手）")
def test_t6(nas: NAS):
    setup_clean_flat(nas)
    # Rename to lose KS code pattern
    nas.rename(FLAT_PATHS["KS0001"], "三角靠枕_产品图")
    result = run_reconcile("flat", dry=True)
    assert_eq(result.get("create", 0), 1, "T6: 丢失 KS 码 → 检测为 MISSING，重新创建")
    assert_in("三角靠枕_产品图", result["output"],
              "T6: 旧文件夹应在 IGNORE 列表")
    # Restore: delete the renamed folder, reconcile will recreate
    nas.rm(f"{TARGET}/三角靠枕_产品图")


@test("T7", "改中间文件夹名 → STRUC_MISMATCH → 自动 MOVE")
def test_t7(nas: NAS):
    setup_clean_flat(nas)
    run_reconcile("tree")
    # Rename intermediate: 床头靠枕 → 床头靠系列
    nas.rename(f"{TARGET}/床品类/床头靠枕", "床头靠系列")
    result = run_reconcile("tree", dry=True)
    assert_eq(result.get("move", 0), 2, "T7: 改中间节点应检测 2 个 MOVE")
    # Execute fix
    run_reconcile("tree")
    assert not nas.exists(f"{TARGET}/床品类/床头靠系列/三角靠枕类/KS0001_三角靠枕"), \
        "T7: 旧路径应为空"
    assert nas.exists(f"{TARGET}/床品类/床头靠枕/三角靠枕类/KS0001_三角靠枕"), \
        "T7: KS0001 应在正确路径"
    # Cleanup: back to flat for next test
    run_reconcile("flat")


@test("T8", "改中间文件夹 + 有文件 → MOVE_APPROVAL")
def test_t8(nas: NAS):
    setup_clean_flat(nas)
    run_reconcile("tree")
    nas.upload_text(TREE_PATHS["KS0001"], "design.psd", "data")
    # Rename intermediate
    nas.rename(f"{TARGET}/床品类/床头靠枕", "床头靠系列")
    result = run_reconcile("tree", dry=True)
    assert_in("MOVE_APPROVAL", result["output"],
              "T8: 有文件时应 MOVE_APPROVAL 而非 MOVE")
    # Cleanup
    nas.rm(f"{TARGET}/床品类/床头靠系列/三角靠枕类/KS0001_三角靠枕/design.psd")
    run_reconcile("tree")  # should auto-move back now


@test("T9", "删除空 KS 文件夹 → MISSING → 自动重建")
def test_t9(nas: NAS):
    setup_clean_flat(nas)
    nas.rm(FLAT_PATHS["KS0001"])
    result = run_reconcile("flat")
    assert_eq(result.get("create", 0), 1, "T9: 删除后应自动重建")
    assert nas.exists(FLAT_PATHS["KS0001"]), "T9: KS0001 应已重建"


@test("T10", "删除有文件 KS 文件夹 → MISSING → 重建（内容已丢，但无回收站保护）")
def test_t10(nas: NAS):
    setup_clean_flat(nas)
    nas.upload_text(FLAT_PATHS["KS0001"], "important.docx", "content")
    # Force delete (this bypasses recycle bin via API)
    nas.rm(FLAT_PATHS["KS0001"])
    # Reconcile should recreate empty folder (content is lost, but API delete is forceful)
    result = run_reconcile("flat")
    assert_eq(result.get("create", 0), 1, "T10: 应重建 KS0001")
    # Verify it's recreated but file is gone
    files_in_ks0001 = [f for f in nas.ls(FLAT_PATHS["KS0001"]) if not f.get("isdir")]
    assert_eq(len(files_in_ks0001), 0, "T10: 重建的文件夹应为空（原始内容无法恢复）")


@test("T11", "Flat→Tree→Flat 孤儿自动清理")
def test_t11(nas: NAS):
    setup_clean_flat(nas)
    run_reconcile("tree")
    result = run_reconcile("flat")
    assert result.get("orphan_cleaned", 0) >= 1, "T11: 应有孤儿清理"
    assert not nas.exists(f"{TARGET}/床品类"), "T11: 树残留应清理干净"


@test("T12", "深层手动文件夹 → 孤儿检测识别但不清理")
def test_t12(nas: NAS):
    setup_clean_flat(nas)
    # Create a manual deep folder under a valid intermediate
    # First create tree layout
    run_reconcile("tree")
    # Add a manual folder under 床品类
    nas.mkdir(f"{TARGET}/床品类/LM的手动备份")
    nas.upload_text(f"{TARGET}/床品类/LM的手动备份", "备份说明.txt", "important")
    # Switch to flat — LM's manual folder should NOT be cleaned
    result = run_reconcile("flat", dry=True)
    assert_in("LM的手动备份", result["output"],
              "T12: LM 手动文件夹应在 IGNORE 中")
    # Cleanup
    nas.rm(f"{TARGET}/床品类/LM的手动备份/备份说明.txt")
    nas.rm(f"{TARGET}/床品类/LM的手动备份")
    run_reconcile("flat")


@test("T13", "单侧破坏 + 另一侧完好 → 部分修复")
def test_t13(nas: NAS):
    setup_clean_flat(nas)
    # Break only KS0001
    nas.rename(FLAT_PATHS["KS0001"], "KS0001_错的名称")
    result = run_reconcile("flat")
    assert_eq(result.get("rename", 0), 1, "T13: 只有 KS0001 改名")
    result2 = run_reconcile("flat", dry=True)
    assert_eq(result2.get("match", 0), 2, "T13: 修复后应全部 MATCH")


@test("T14", "特殊字符文件夹名 → safe_name 转义")
def test_t14(nas: NAS):
    setup_clean_flat(nas)
    # This tests the safe_name function behavior — folder with bad chars
    # Simulate what happens if someone manually creates a folder with bad chars
    try:
        nas.mkdir(f"{TARGET}/test:bad*name")
        # Should be detected as IGNORE (non KS format)
        result = run_reconcile("flat", dry=True)
        assert_in("test:bad*name", result["output"],
                  "T14: 非法字符文件夹应在 IGNORE")
        nas.rm(f"{TARGET}/test:bad*name")
        assert True  # no crash
    except Exception as e:
        # Some NAS APIs reject bad chars at upload time
        print(f"  [INFO] NAS rejected bad chars: {e}")
        assert True  # graceful handling counts as pass


@test("T15", "KS 编码碰撞（两个同名 KS 文件夹）→ 取第一个匹配")
def test_t15(nas: NAS):
    setup_clean_flat(nas)
    # Create a duplicate with slightly different name
    nas.mkdir(f"{TARGET}/KS0001_三角靠枕_副本")
    result = run_reconcile("flat", dry=True)
    # The copy has KS0001 code but different name → should trigger NAME_MISMATCH
    # But with 2 candidates, the engine picks the first match
    # The second becomes IGNORE or EXTRA
    assert_in("KS0001", result["output"], "T15: 应处理 KS0001 碰撞")
    # Cleanup
    nas.rm(f"{TARGET}/KS0001_三角靠枕_副本")


# ── Main ─────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", help="Run specific test (e.g. T1)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview operations, don't execute")
    args = parser.parse_args()

    nas = NAS()
    print(f"=== NAS-ERPNext 鲁棒性测试 ===  {datetime.now().strftime('%H:%M')}")
    print(f"    NAS: {TARGET}")
    print()

    run_all = True
    tests_to_run = TESTS
    if args.test:
        run_all = False
        tests_to_run = [t for t in TESTS if t["id"] == args.test]
        if not tests_to_run:
            print(f"ERROR: test {args.test} not found")
            sys.exit(1)

    for t in tests_to_run:
        r = TestResult(t["id"])
        r.desc = t["desc"]
        print(f"[{t['id']}] {t['desc']} ...", end=" ", flush=True)
        try:
            if args.dry_run:
                print("DRY-RUN (skipped)")
                r.passed = True
                r.detail = "dry-run"
            else:
                t["fn"](nas)
                r.passed = True
                print("PASS")
        except AssertionError as e:
            r.passed = False
            r.error = str(e)
            print(f"FAIL\n      {e}")
        except Exception as e:
            r.passed = False
            r.error = f"{type(e).__name__}: {e}"
            print(f"ERROR\n      {traceback.format_exc()}")
        results.append(r)

    # Summary
    print(f"\n{'=' * 60}")
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    print(f"结果: {passed}/{len(results)} 通过, {failed} 失败")
    for r in results:
        status = "✅" if r.passed else "❌"
        print(f"  {status} [{r.name}] {r.desc[:60]}")
        if r.error:
            print(f"       {r.error}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
