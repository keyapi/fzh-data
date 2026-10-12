import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
import http.cookiejar
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer

import server
from domain import Store


class OpsPageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(str(Path(self.temp.name) / "ops.sqlite3"))
        self.patch = patch.object(server, "STORE", self.store)
        self.patch.start()
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:" + str(self.http.server_port)
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.current_role = None

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=3)
        self.patch.stop()
        self.store.db.close()
        self.temp.cleanup()

    def call(self, path, body=None, role="operator"):
        if self.current_role != role:
            login = urllib.request.Request(self.base + '/api/login', data=json.dumps({'username': role, 'password': 'demo2026'}).encode(),
                headers={'Content-Type': 'application/json', 'X-Demo-Request': '1'})
            with self.opener.open(login) as resp:
                resp.read()
            self.current_role = role
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            self.base + path,
            data=data,
            headers={"Content-Type": "application/json", "X-Demo-Request": "1"},
            method="GET" if body is None else "POST",
        )
        try:
            with self.opener.open(req) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def config(self, snap, scenario, env):
        return next(c for c in snap["configs"] if c["scenario"] == scenario and c["environment"] == env)

    def test_new_pages_keep_cloud_shell_and_controlled_write(self):
        status, snap = self.call("/api/ops/state")
        self.assertEqual(status, 200)
        self.assertEqual(self.config(snap, "integration", "test")["values"], {"timeout": 30, "retries": 2})
        self.assertEqual(self.config(snap, "integration", "prod")["values"], {"timeout": 30, "retries": 2})
        self.assertIn("联调配置", Path(server.ROOT, "index.html").read_text(encoding="utf-8"))
        self.assertIn("柜面参数 · 对公结算", Path(server.ROOT, "index.html").read_text(encoding="utf-8"))

        status, denied = self.call("/api/ops/propose", {
            "role": "operator",
            "scenario": "integration",
            "changes": [{"field": "timeout", "value": 60}, {"field": "retries", "value": 1}],
            "reason": "越权正文不能升岗",
            "submit": True,
        }, role="reader")
        self.assertEqual(status, 403)
        self.assertEqual(denied["code"], "FORBIDDEN")

        status, proposal = self.call("/api/ops/propose", {
            "scenario": "integration",
            "changes": [{"field": "timeout", "value": 60}, {"field": "retries", "value": 1}],
            "reason": "联调超时，重试降到 1 次",
            "submit": True,
        })
        self.assertEqual(proposal["status"], "pending")
        _, before = self.call("/api/ops/state")
        self.assertEqual(self.config(before, "integration", "test")["values"]["timeout"], 30)

        status, done = self.call("/api/ops/execute", {"proposal_id": proposal["id"], "digest": proposal["digest"]})
        self.assertEqual(status, 200)
        self.assertEqual(done["readback"]["values"], {"timeout": 60, "retries": 1})
        self.assertEqual(done["ticket"]["status"], "pending_review")
        _, after = self.call("/api/ops/state")
        self.assertEqual(self.config(after, "integration", "prod")["values"], {"timeout": 30, "retries": 2})

        status, reviewed = self.call("/api/ops/review", {"ticket_id": done["ticket"]["id"], "approve": True}, role="reviewer")
        self.assertEqual(reviewed["code"], "REVIEWED")
        _, final = self.call("/api/ops/state")
        self.assertEqual(self.config(final, "integration", "prod")["values"], {"timeout": 30, "retries": 2})

        status, safety = self.call("/api/ops/safety", {"case": "unauthorized"})
        self.assertEqual(status, 200)
        self.assertTrue(safety["passed"])
        self.assertEqual(safety["actual"], "FORBIDDEN")
        _, still = self.call("/api/ops/state")
        self.assertEqual(self.config(still, "integration", "test")["values"], {"timeout": 60, "retries": 1})

        docs = self.call("/api/ops/knowledge?q=" + urllib.parse.quote("超时"))[1]["documents"]
        self.assertTrue(any(d["id"] == "RULE-01" and d["version"] == "2.0" for d in docs))
        self.assertEqual(self.call("/v1/chat/completions", {})[0], 404)


if __name__ == "__main__":
    unittest.main()
