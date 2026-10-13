"""Real POC feedback, independent of demo resets and public demo roles."""
import hashlib
import json
import re
import sqlite3
import threading
import time
import uuid

from domain import DomainError


class FeedbackStore:
    def __init__(self, path):
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS feedback (id TEXT PRIMARY KEY, receipt_hash TEXT UNIQUE NOT NULL, content TEXT NOT NULL, created REAL NOT NULL, status TEXT NOT NULL, reply TEXT NOT NULL)')
        self.db.commit()

    @staticmethod
    def _receipt(receipt):
        if not isinstance(receipt, str) or not re.fullmatch(r'[a-f0-9]{64}', receipt):
            raise DomainError('INVALID_RECEIPT', '反馈查询凭证无效。')
        return hashlib.sha256(receipt.encode()).hexdigest()

    def submit(self, body):
        fields = ('scene', 'title', 'steps', 'expected', 'actual', 'rule', 'impact')
        data = {}
        for field in fields:
            value = body.get(field, '')
            if not isinstance(value, str) or len(value) > (200 if field in ('scene', 'title', 'impact') else 4000):
                raise DomainError('INVALID_INPUT', '反馈字段格式无效或内容过长。')
            data[field] = value.strip()
        if not all(data[k] for k in ('scene', 'title', 'steps', 'expected', 'impact')):
            raise DomainError('INVALID_INPUT', '请填写场景、标题、步骤、预期行为和影响。')
        receipt_hash = self._receipt(body.get('receipt'))
        serialized = json.dumps(data, ensure_ascii=False, sort_keys=True)
        with self.lock:
            row = self.db.execute('SELECT id, content FROM feedback WHERE receipt_hash=?', (receipt_hash,)).fetchone()
            if row:
                if row[1] != serialized:
                    raise DomainError('RECEIPT_REUSED', '该提交凭证已用于其他内容，请新建一条反馈。', 409)
                return {'id': row[0], 'status': self.get(row[0], body['receipt'])['status'], 'duplicate': True}
            if self.db.execute('SELECT COUNT(*) FROM feedback').fetchone()[0] >= 5000:
                raise DomainError('CAPACITY', '反馈容量已满，请联系项目负责人。', 429)
            feedback_id = 'FB-' + uuid.uuid4().hex[:16].upper()
            self.db.execute('INSERT INTO feedback VALUES (?,?,?,?,?,?)', (feedback_id, receipt_hash, serialized, time.time(), 'new', ''))
            self.db.commit()
            return {'id': feedback_id, 'status': 'new', 'duplicate': False}

    def get(self, feedback_id, receipt):
        hashed = self._receipt(receipt)
        with self.lock:
            row = self.db.execute('SELECT content, created, status, reply FROM feedback WHERE id=? AND receipt_hash=?', (feedback_id, hashed)).fetchone()
        if not row:
            raise DomainError('NOT_FOUND', '反馈不存在或查询凭证不匹配。', 404)
        return {'id': feedback_id, 'content': json.loads(row[0]), 'created_at': row[1], 'status': row[2], 'reply': row[3]}


if __name__ == '__main__':
    # Operator access is via host filesystem/SSH, never a public demo role.
    import argparse
    parser = argparse.ArgumentParser(description='反馈维护（仅服务器管理员）')
    parser.add_argument('--db', default='data/feedback.sqlite3')
    parser.add_argument('--id')
    parser.add_argument('--status', choices=('new', 'triaged', 'in_progress', 'resolved', 'needs_info'))
    parser.add_argument('--reply', default='')
    args = parser.parse_args()
    store = FeedbackStore(args.db)
    if args.status:
        if not args.id:
            parser.error('更新需要 --id')
        with store.lock:
            changed = store.db.execute('UPDATE feedback SET status=?, reply=? WHERE id=?', (args.status, args.reply, args.id)).rowcount
            store.db.commit()
        print(json.dumps({'updated': changed}, ensure_ascii=False))
    else:
        rows = store.db.execute('SELECT id, content, created, status, reply FROM feedback ORDER BY created DESC').fetchall()
        print(json.dumps([{'id': r[0], 'content': json.loads(r[1]), 'created_at': r[2], 'status': r[3], 'reply': r[4]} for r in rows], ensure_ascii=False, indent=2))
