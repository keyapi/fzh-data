"""
赛狐 API 文档批量下载脚本
从 llms.txt 解析文档结构，用 cookie 认证后下载所有 .md 文件，按原文结构保存。

用法:
  python download_sellfox_docs.py --dry-run          # 仅下载前 10 个（默认）
  python download_sellfox_docs.py --max 10            # 下载前 N 个
  python download_sellfox_docs.py --all               # 下载全部
  python download_sellfox_docs.py --parse-only        # 仅解析 llms.txt，不下载
  python download_sellfox_docs.py --cookie-file PATH  # 指定 cookie 文件路径
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

# ---- paths ----
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT = SCRIPT_DIR / "docs" / "api-reference"
LLMS_FILE = DEFAULT_OUTPUT / "llms.txt"
PARSED_CACHE = DEFAULT_OUTPUT / "llms_parsed.json"
DOWNLOAD_LOG = DEFAULT_OUTPUT / "download_log.json"
DEFAULT_COOKIE_FILE = DEFAULT_OUTPUT / "cookie.txt"

# ---- llms.txt parser ----

def parse_llms(llms_path: Path) -> dict:
    """Parse llms.txt into structured document tree. Returns:
    {
        "source": "https://sellfoxapi.apifox.cn/llms.txt",
        "fetched_at": "2026-07-01T...",
        "sections": {
            "开发指南": {
                "docs": [
                    {"path": ["开发指南"], "title": "...", "url": "..."},
                    {"path": ["开发指南", "数据结构"], "title": "...", "url": "..."},
                ]
            },
            "API 参考": {
                "商品": {
                    "商品列表": [
                        {"path": ["商品", "商品列表"], "title": "创建SKU", "url": "..."},
                    ]
                }
            }
        },
        "flat_list": [...],  # All unique docs in order
        "total_unique": 447
    }
    """
    text = llms_path.read_text(encoding="utf-8")

    sections: dict = {}
    seen_base_urls: set = set()
    flat_list: list = []
    current_section: Optional[str] = None
    current_module: Optional[str] = None
    current_submodule: Optional[str] = None

    for line in text.splitlines():
        stripped = line.strip()

        # Section headers
        if stripped == "## Docs":
            current_section = "开发指南"
            if current_section not in sections:
                sections[current_section] = []
            continue
        elif stripped == "## API Docs":
            current_section = "API 参考"
            if current_section not in sections:
                sections[current_section] = {}
            continue
        elif stripped.startswith("#"):
            continue

        if not stripped.startswith("- "):
            continue

        # Parse: - [module > submodule] [title](url): desc
        entry = stripped[2:]  # Remove "- "

        # Extract hierarchy prefix before [
        bracket_idx = entry.find(" [")
        if bracket_idx == -1:
            continue
        hierarchy_str = entry[:bracket_idx].strip()
        rest = entry[bracket_idx + 1:]  # "title](url): desc"

        # Extract title and url
        m = re.match(r"(.+?)\]\((.+?)\)", rest)
        if not m:
            continue
        title = m.group(1).strip().lstrip("[")
        full_url = m.group(2).strip()
        # description after ):  (optional)
        desc = rest[m.end():].lstrip(": ").strip()

        # Strip ?nav= param for dedup
        base_url = re.sub(r"\?nav=.*$", "", full_url)

        if base_url in seen_base_urls:
            continue
        seen_base_urls.add(base_url)

        # Parse hierarchy levels
        levels = [x.strip() for x in hierarchy_str.split(">")]

        if current_section == "开发指南":
            doc_entry = {
                "path": levels,  # e.g., ["开发指南"] or ["开发指南", "数据结构"]
                "title": title,
                "url": base_url,
                "description": desc,
            }
            sections["开发指南"].append(doc_entry)
            flat_list.append(doc_entry)
        else:
            # API 参考: 3-level structure
            if len(levels) >= 1:
                current_module = levels[0]
            if len(levels) >= 2:
                current_submodule = levels[1]
            else:
                current_submodule = ""

            path = levels.copy()  # e.g., ["商品", "商品列表"]

            if current_module not in sections["API 参考"]:
                sections["API 参考"][current_module] = {}

            if current_submodule:
                if current_submodule not in sections["API 参考"][current_module]:
                    sections["API 参考"][current_module][current_submodule] = []
                sections["API 参考"][current_module][current_submodule].append({
                    "path": path,
                    "title": title,
                    "url": base_url,
                    "description": desc,
                })
            else:
                # No submodule - store under module directly
                if "_direct" not in sections["API 参考"][current_module]:
                    sections["API 参考"][current_module]["_direct"] = []
                sections["API 参考"][current_module]["_direct"].append({
                    "path": path,
                    "title": title,
                    "url": base_url,
                    "description": desc,
                })

            flat_list.append({
                "path": path,
                "title": title,
                "url": base_url,
                "description": desc,
            })

    return {
        "source": "https://sellfoxapi.apifox.cn/llms.txt",
        "parsed_at": datetime.now(timezone.utc).isoformat(),
        "sections": sections,
        "flat_list": flat_list,
        "total_unique": len(flat_list),
    }


def safe_filename(name: str) -> str:
    """Sanitize a string for use as a windows-safe filename."""
    # Replace characters not allowed in Windows filenames
    name = re.sub(r'[<>:"/\\|?*]', "-", name)
    name = name.strip(". ")
    # Trim to reasonable length
    if len(name) > 120:
        name = name[:120]
    return name


def build_output_path(doc: dict, base_dir: Path) -> Path:
    """Build output file path from document path hierarchy + title."""
    parts = [safe_filename(p) for p in doc["path"]]
    filename = safe_filename(doc["title"]) + ".md"
    return base_dir.joinpath(*parts) / filename


# ---- downloader ----

def load_cookie(cookie_path: Path) -> str:
    """Load cookie string from file."""
    if not cookie_path.exists():
        print(f"ERROR: Cookie file not found: {cookie_path}")
        print("Make sure to save the browser cookie first.")
        sys.exit(1)
    return cookie_path.read_text(encoding="utf-8").strip()


def download_doc(url: str, cookie: str, timeout: int = 30) -> tuple[int, str]:
    """Download a single document. Returns (status_code, content)."""
    headers = {
        "Cookie": cookie,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        return r.status_code, r.text
    except requests.RequestException as e:
        return -1, str(e)


def is_valid_markdown(content: str) -> bool:
    """Quick check if content looks like markdown (not HTML login page)."""
    if not content:
        return False
    # If it starts with HTML, it's likely the password page
    stripped = content.strip()
    if stripped.startswith("<!DOCTYPE") or stripped.startswith("<html"):
        return False
    return True


def download_all(
    flat_list: list,
    cookie: str,
    output_dir: Path,
    max_count: Optional[int] = None,
    delay: float = 1.0,
) -> list:
    """Download all documents from flat_list. Records results to download_log."""
    log: list = []
    total = min(len(flat_list), max_count) if max_count else len(flat_list)
    downloaded = 0
    failed = 0
    skipped = 0

    output_dir.mkdir(parents=True, exist_ok=True)

    for i, doc in enumerate(flat_list):
        if max_count and i >= max_count:
            break

        url = doc["url"]
        title = doc["title"]
        path_str = " > ".join(doc["path"])

        out_path = build_output_path(doc, output_dir)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        entry = {
            "index": i + 1,
            "title": title,
            "path": path_str,
            "url": url,
            "file": str(out_path.relative_to(output_dir)),
            "status": None,
            "size": 0,
        }

        # Skip if already downloaded (optional: could re-download)
        if out_path.exists():
            entry["status"] = "skipped"
            entry["size"] = out_path.stat().st_size
            skipped += 1
        else:
            print(f"[{i+1}/{total}] {path_str} > {title}")
            status, content = download_doc(url, cookie)

            if status == 200 and is_valid_markdown(content):
                out_path.write_text(content, encoding="utf-8")
                entry["status"] = "ok"
                entry["size"] = len(content.encode("utf-8"))
                downloaded += 1
                print(f"  OK ({entry['size']} bytes) -> {entry['file']}")
            else:
                entry["status"] = f"error_{status}"
                failed += 1
                print(f"  FAIL (HTTP {status})")

            if delay > 0:
                time.sleep(delay)

        log.append(entry)

    # Save log
    log_data = {
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "total": total,
        "downloaded": downloaded,
        "failed": failed,
        "skipped": skipped,
        "entries": log,
    }
    DOWNLOAD_LOG.write_text(json.dumps(log_data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n=== Summary ===")
    print(f"Total: {total}, OK: {downloaded}, Failed: {failed}, Skipped: {skipped}")
    print(f"Log: {DOWNLOAD_LOG}")

    return log


# ---- main ----

def main():
    parser = argparse.ArgumentParser(description="Download 赛狐 API docs from Apifox")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Download first 10 docs (default)")
    parser.add_argument("--max", type=int, dest="max_count",
                        help="Download first N docs")
    parser.add_argument("--all", action="store_true",
                        help="Download all docs")
    parser.add_argument("--parse-only", action="store_true",
                        help="Only parse llms.txt, don't download")
    parser.add_argument("--cookie-file", type=str,
                        help="Path to cookie file")
    parser.add_argument("--output-dir", type=str,
                        help="Output directory")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="Delay between requests in seconds (default: 1.0)")
    args = parser.parse_args()

    # Determine cookie path
    cookie_path = Path(args.cookie_file) if args.cookie_file else DEFAULT_COOKIE_FILE

    # Determine output directory
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT

    # Step 1: Parse llms.txt
    print("Parsing llms.txt...")
    if not LLMS_FILE.exists():
        print(f"ERROR: {LLMS_FILE} not found. Download it first.")
        sys.exit(1)

    parsed = parse_llms(LLMS_FILE)

    # Save parsed cache
    PARSED_CACHE.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Parsed {parsed['total_unique']} unique documents -> {PARSED_CACHE}")

    # Print structure summary
    api_ref = parsed["sections"].get("API 参考", {})
    dev_guide = parsed["sections"].get("开发指南", [])
    print(f"  开发指南: {len(dev_guide)} docs")
    print(f"  API 参考: {sum(len(subs) if isinstance(subs, list) else sum(len(v) for v in subs.values()) for subs in api_ref.values())} docs in {len(api_ref)} modules")

    if args.parse_only:
        return

    # Step 2: Load cookie
    cookie = load_cookie(cookie_path)

    # Step 3: Download
    if args.max_count:
        max_count = args.max_count
    elif args.all:
        max_count = None
    else:
        max_count = 10  # dry-run default

    print(f"\nDownloading {'first ' + str(max_count) if max_count else 'ALL'} documents...")
    print(f"Output: {output_dir}")
    print(f"Delay: {args.delay}s between requests\n")

    download_all(parsed["flat_list"], cookie, output_dir, max_count, args.delay)


if __name__ == "__main__":
    main()
