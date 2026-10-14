import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import server
from domain import Store


class JudgingExperienceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(str(Path(self.temp.name) / "experience.sqlite3"))
        self.store_patch = patch.object(server, "STORE", self.store)
        self.store_patch.start()
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:" + str(self.http.server_port)

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=3)
        self.store_patch.stop()
        self.store.db.close()
        self.temp.cleanup()

    def test_projection_page_keeps_knowledge_and_control_boundaries_visible(self):
        with urllib.request.urlopen(self.base + "/show.html") as response:
            body = response.read().decode("utf-8")
        self.assertEqual(response.status, 200)
        self.assertIn("知识辅助与受控办理", body)
        self.assertIn("人工确认", body)
        self.assertIn("财资助手", body)
        self.assertIn("未自动共享知识或联通接口", body)
        self.assertIn("人工审核机制仍需在试点前完善", body)
        self.assertIn("生产只可准备申请", body)
        self.assertNotIn("分行自主实施", body)
        self.assertNotIn("全辖", body)

    def test_ticket_switch_clears_old_local_task_before_analysis(self):
        source = Path(server.ROOT, "bank_task_ui.js").read_text(encoding="utf-8")
        self.assertIn("el('bank-task-ticket').onchange=selectTicket", source)
        self.assertIn("currentTask=task&&task.ticket_id===selectedTicket?task:null", source)
        self.assertIn("for(const op of proposal.operations.filter(op=>op.entity===entity))", source)
        self.assertIn("请在对应业务页选择要确认的方案", Path(server.ROOT, "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
