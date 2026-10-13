import unittest
from unittest.mock import patch
import test_bank_task_http as helper
import server

class RouteHttpTests(unittest.TestCase):
    setUp = helper.BankTaskHttpTests.setUp
    tearDown = helper.BankTaskHttpTests.tearDown
    raw = helper.BankTaskHttpTests.raw
    call = helper.BankTaskHttpTests.call
    login = helper.BankTaskHttpTests.login

    def test_model_to_confirmation_and_readback(self):
        self.login()
        with patch.object(server, 'model_call', return_value=helper.reply(calls=[('select_services', {'services':['balance','statement','bill']})])):
            status, result = self.call('/api/routes/plan', {'text':'开通余额查询、明细查询和票据查询'})
        self.assertEqual(status, 200, result)
        p = result['route']['proposal']
        self.assertEqual(result['route']['routes'], [])
        status, saved = self.call('/api/routes/execute', {'proposal_id':p['id'],'digest':p['digest']})
        self.assertEqual(status, 200, saved)
        self.assertTrue(saved['readback']['passed'])
        self.assertTrue(saved['route']['report']['passed'])
        self.assertEqual(self.call('/api/routes/execute', {'proposal_id':p['id'],'digest':p['digest']})[0],409)

    def test_reader_denied_before_model_and_negation(self):
        self.login('reader')
        with patch.object(server, 'model_call') as model:
            self.assertEqual(self.call('/api/routes/plan', {'text':'开通余额查询'})[0],403)
            model.assert_not_called()
        self.login()
        self.assertEqual(self.call('/api/routes/plan', {'text':'开通余额但不要开通票据'})[0],400)
