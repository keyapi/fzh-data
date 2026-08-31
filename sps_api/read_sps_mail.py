#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
读取 SPS Commerce 相关邮件（IMAP）。凭据从环境变量读取，不写进代码。

用法（凭据经环境变量传入）:
  IMAP_USER='pb@icentrade.com' IMAP_PASS='xxx' IMAP_SERVER='imap.exmail.qq.com' \\
  python read_sps_mail.py                          # 列出 SPS 相关邮件（日期/主题/摘要）
  python read_sps_mail.py --sender amkudrle@spscommerce.com   # 指定发件人
  python read_sps_mail.py --full 5                  # 打印第 5 封的完整正文
  python read_sps_mail.py --since 30-Jun-2025 --before 03-Jul-2025   # 日期过滤
"""
import html
import imaplib
import os
import re
import sys
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser


def env(name):
    val = os.getenv(name)
    if not val:
        raise SystemExit(f"缺少环境变量 {name}")
    return val


def fetch_uids(imap, criteria):
    typ, data = imap.uid('search', None, *criteria)
    if typ != 'OK':
        return []
    return data[0].split()


def get_message(imap, uid):
    typ, data = imap.uid('fetch', uid, '(RFC822)')
    if typ != 'OK' or not data or data[0] is None:
        return None, None
    if isinstance(data[0], tuple):
        raw = data[0][1]
    else:
        raw = data[0]
    if not raw:
        return None, None
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    subj = str(msg.get('subject', ''))
    frm = str(msg.get('from', ''))
    date = msg.get('date', '')
    return msg, {'uid': uid, 'subject': subj, 'from': frm, 'date': date}


def decode_part(part):
    cte = part.get_content_charset() or 'utf-8'
    payload = part.get_payload(decode=True)
    if payload is None:
        return ''
    for enc in (cte, 'utf-8', 'gbk', 'gb18030'):
        try:
            return payload.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return payload.decode('utf-8', 'replace')


def body_text(msg):
    """提取正文纯文本；HTML 部分用 html.parser 简单去标签。"""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == 'text/plain':
                return decode_part(part)
        for part in msg.walk():
            if part.get_content_type() == 'text/html':
                raw = decode_part(part)
                return html_to_text(raw)
    elif msg.get_content_type() == 'text/plain':
        return decode_part(msg)
    elif msg.get_content_type() == 'text/html':
        return html_to_text(decode_part(msg))
    return ''


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
    def handle_data(self, d):
        if d.strip():
            self.parts.append(d.strip())
    def handle_starttag(self, tag, attrs):
        if tag in ('p', 'br', 'div', 'tr', 'li', 'h1', 'h2', 'h3'):
            self.parts.append('\n')


def html_to_text(raw):
    p = _TextExtractor()
    p.feed(raw)
    text = '\n'.join(p.parts)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def main():
    args = sys.argv[1:]
    sender = None
    full_index = None
    since = None
    before = None
    i = 0
    while i < len(args):
        if args[i] == '--sender' and i + 1 < len(args):
            sender = args[i + 1]; i += 2
        elif args[i] == '--full' and i + 1 < len(args):
            full_index = int(args[i + 1]); i += 2
        elif args[i] == '--since' and i + 1 < len(args):
            since = args[i + 1]; i += 2
        elif args[i] == '--before' and i + 1 < len(args):
            before = args[i + 1]; i += 2
        else:
            i += 1

    user = env('IMAP_USER')
    pwd = env('IMAP_PASS')
    server = env('IMAP_SERVER')
    port = int(os.getenv('IMAP_PORT', '993'))

    imap = imaplib.IMAP4_SSL(server, port)
    imap.login(user, pwd)
    imap.select('INBOX')

    criteria = []
    if sender:
        criteria.append(f'FROM "{sender}"')
    if since:
        criteria.append(f'SINCE "{since}"')
    if before:
        criteria.append(f'BEFORE "{before}"')

    uids = fetch_uids(imap, criteria)
    print(f"匹配邮件数: {len(uids)}")
    print(f"{'#':>3} {'日期':<20} {'主题'}")
    print('-' * 90)

    msgs = []
    for idx, uid in enumerate(uids, 1):
        msg, meta = get_message(imap, uid)
        if msg is None or meta is None:
            continue
        try:
            d = parsedate_to_datetime(meta['date']).strftime('%Y-%m-%d %H:%M')
        except Exception:
            d = str(meta['date'])[:16]
        subj = meta['subject'][:60]
        print(f"{idx:>3} {d:<20} {subj}")
        msgs.append((msg, meta))

    if full_index and 1 <= full_index <= len(msgs):
        msg, meta = msgs[full_index - 1]
        print(f"\n===== 邮件 #{full_index} 完整正文 =====")
        print(f"From: {meta['from']}")
        print(f"Date: {meta['date']}")
        print(f"Subject: {meta['subject']}")
        print('-' * 60)
        print(body_text(msg))

    imap.logout()


if __name__ == '__main__':
    main()
