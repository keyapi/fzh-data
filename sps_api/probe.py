#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SPS Commerce Transaction API 探测脚本。

探测沙盒里实际暴露了哪些目录/文件，验证 Transaction API 通道可用性。
按官方 Startup Guide：沙盒样例订单位于 out/PO/。

用法:
  python probe.py                # 列根目录
  python probe.py out/PO/        # 列指定目录
  python probe.py out/PO/ --download   # 列出并下载第一个文件到 ./downloads/
  python probe.py --token-only   # 只拿 token，不做 API 调用
"""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from config import API_BASE
from oauth import get_token


def api_get(token, url_path):
    url = API_BASE + url_path
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def list_dir(token, directory=''):
    """列目录。directory 必须以 '/' 结尾（根目录传 ''）。"""
    url_path = f'/transactions/v5/data/{directory}'
    raw = api_get(token, url_path)
    return json.loads(raw.decode('utf-8'))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    download = '--download' in sys.argv
    token_only = '--token-only' in sys.argv

    token = get_token()
    if token_only:
        print(f"[OK] token 可用: {token[:20]}...")
        return

    directory = args[0] if args else ''
    if directory and not directory.endswith('/'):
        directory += '/'

    print(f"=== 列出目录: /{directory} ===")
    try:
        data = list_dir(token, directory)
    except urllib.error.HTTPError as e:
        print(f"[错误] HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:500]}")
        return

    entries = data.get('results', data) if isinstance(data, dict) else data
    print(json.dumps(data, indent=2, ensure_ascii=False)[:2000])

    if download and entries:
        first = entries[0]
        file_key = first.get('path') or first.get('fileKey') or first.get('name') or first
        print(f"\n=== 下载第一个文件: {file_key} ===")
        out_dir = Path(__file__).resolve().parent / 'downloads'
        out_dir.mkdir(exist_ok=True)
        raw = api_get(token, f'/transactions/v5/data/{file_key}')
        out_path = out_dir / Path(file_key).name
        out_path.write_bytes(raw)
        print(f"已保存: {out_path}（{len(raw)} 字节）")
        print(raw[:500].decode('utf-8', 'replace'))


if __name__ == '__main__':
    main()
