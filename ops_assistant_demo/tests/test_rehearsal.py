import tempfile
import collections
import unittest
from pathlib import Path
from unittest.mock import patch

import server
import test_bank_task_http as helper
from feedback_store import FeedbackStore


class RehearsalHttpTests(unittest.TestCase):
    def setUp(self):
        helper.BankTaskHttpTests.setUp(self)
        self.buckets_patch = patch.object(server, 'BUCKETS', collections.defaultdict(collections.deque))
        self.buckets_patch.start()

    def tearDown(self):
        self.buckets_patch.stop()
        helper.BankTaskHttpTests.tearDown(self)
    raw = helper.BankTaskHttpTests.raw
    call = helper.BankTaskHttpTests.call

    def test_fresh_isolates_workspace_and_preserves_feedback_and_old_audit(self):
        feedback = FeedbackStore(Path(self.tmp.name)/'feedback.sqlite3')
        try:
            with patch.object(server, 'FEEDBACK', feedback):
                body={'receipt':'a'*64,'scene':'排练','title':'疑问','steps':'准备','impact':'建议优化'}
                ticket=feedback.submit(body)
                status, old=self.call('/api/login',{'username':'operator','password':'demo2026'})
                self.assertEqual(status,200)
                workspace=old['workspace']
                status, proposal=self.call('/api/propose',{'scenario':'counter','changes':[{'field':'limit','value':200000}],'reason':'排练','submit':False})
                self.assertEqual(status,200,proposal)
                proposal=proposal['proposal']
                status,new=self.call('/api/rehearsal/fresh',{})
                self.assertEqual(status,200,new)
                self.assertNotEqual(new['state']['workspace'],workspace)
                self.assertEqual(new['state']['proposals'],[])
                self.assertTrue(self.store.audit(workspace,'operator'))
                self.assertEqual(feedback.get(ticket['id'],body['receipt'])['status'],'new')
                self.assertEqual(self.call('/api/execute',{'proposal_id':proposal['id'],'digest':proposal['digest']})[0],404)
        finally:
            feedback.db.close()

    def test_fresh_requires_operator_and_script_is_public(self):
        self.assertEqual(self.call('/api/rehearsal/fresh',{})[0],401)
        self.assertEqual(self.call('/api/login',{'username':'reader','password':'demo2026'})[0],200)
        self.assertEqual(self.call('/api/rehearsal/fresh',{})[0],403)
        self.assertEqual(self.raw('/rehearsal_ui.js')[0],200)
