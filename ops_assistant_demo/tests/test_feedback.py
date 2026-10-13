import json
import base64
import io
import zipfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server
import test_bank_task_http as helper
from domain import DomainError
from feedback_store import FeedbackStore


class FeedbackTests(unittest.TestCase):
    def test_attachment_privacy_and_portable_export(self):
        png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jUioAAAAASUVORK5CYII=')
        store = FeedbackStore(':memory:')
        body = {'receipt':'e'*64,'scene':'路由','title':'截图问题','steps':'分析','expected':'成功','impact':'影响演示',
                'attachments':[{'data':base64.b64encode(png).decode()}], 'context':{'fake':'client log'}}
        result = store.submit(body, {'recent_operations':[{'http_status':400,'code':'NEED_BUSINESS'}]})
        record = store.get(result['id'],body['receipt'])
        meta = record['content']['attachments'][0]
        self.assertNotIn('fake',record['content']['context'])
        self.assertEqual(store.attachment(result['id'], meta['id'],body['receipt'])[1],png)
        with self.assertRaises(DomainError):
            store.attachment(result['id'],meta['id'],'f'*64)
        bundle = zipfile.ZipFile(io.BytesIO(store.export(result['id'])))
        self.assertEqual(bundle.read(result['id']+'/screenshot-1.png'),png)
        self.assertNotIn(body['receipt'],bundle.read('index.json').decode())
        self.assertTrue(store.submit(body)['duplicate'])
        store.db.close()

    def test_attachment_limits_and_file_type(self):
        store = FeedbackStore(':memory:')
        base = {'receipt':'a'*64,'scene':'路由','title':'测试','steps':'测试','expected':'测试','impact':'建议优化'}
        for files in ([{'data':'not-base64'}], [{'data':base64.b64encode(b'<html>script</html>').decode()}], [{}]*4):
            with self.assertRaises(DomainError):
                store.submit({**base,'attachments':files})
        store.db.close()

    def test_persistence_receipt_isolation_and_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'feedback.sqlite3'
            store = FeedbackStore(path)
            body = {'receipt': 'a'*64, 'scene': '路由', 'title': '选择已有适配器', 'steps': '点击分析', 'expected': '复用', 'impact': '业务逻辑错误'}
            result = store.submit(body)
            self.assertTrue(store.submit(body)['duplicate'])
            with self.assertRaises(DomainError):
                store.get(result['id'], 'b'*64)
            with self.assertRaises(DomainError):
                store.submit({**body, 'title': '不同内容'})
            store.db.close()
            reopened = FeedbackStore(path)
            self.assertEqual(reopened.get(result['id'], body['receipt'])['content']['title'], body['title'])
            reopened.db.close()


class FeedbackHttpTests(unittest.TestCase):
    setUp = helper.BankTaskHttpTests.setUp
    tearDown = helper.BankTaskHttpTests.tearDown
    raw = helper.BankTaskHttpTests.raw
    call = helper.BankTaskHttpTests.call

    def test_anonymous_submit_and_private_lookup(self):
        store = FeedbackStore(Path(self.tmp.name) / 'feedback.sqlite3')
        try:
            with patch.object(server, 'FEEDBACK', store):
                status, result = self.call('/api/feedback', {'receipt':'c'*64,'scene':'路由','title':'验证','steps':'点击','expected':'成功','impact':'建议优化'})
                self.assertEqual(status, 200, result)
                feedback_id = result['feedback']['id']
                self.assertEqual(self.call('/api/feedback?id='+feedback_id)[0], 400)
                import urllib.request
                req = urllib.request.Request(self.base+'/api/feedback?id='+feedback_id, headers={'X-Feedback-Receipt':'c'*64})
                with self.client.open(req) as response:
                    record = json.loads(response.read())
                self.assertEqual(record['feedback']['content']['title'],'验证')
                self.assertEqual(self.call('/api/feedback', {'receipt':'d'*64})[0], 400)
        finally:
            store.db.close()
