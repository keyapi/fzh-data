import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import http.cookiejar
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer

import server
from domain import DomainError, Store


class DeskDomainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(str(Path(self.temp.name) / "desk.sqlite3"))

    def tearDown(self):
        self.store.db.close()
        self.temp.cleanup()

    def test_reader_cannot_see_prod_rows_or_prepare_writes(self):
        self.store.load_params("desk", "operator")
        operator = self.store.snapshot("desk", "operator")
        reader = self.store.snapshot("desk", "reader")
        self.assertTrue(any(row["env"] == "prod" for row in operator["params"]))
        self.assertTrue(any(row["env"] == "prod" for row in operator["ips"]))
        self.assertFalse(any(row["env"] == "prod" for row in reader["params"]))
        self.assertFalse(any(row["env"] == "prod" for row in reader["ips"]))
        self.assertEqual(operator["terminal"]["name"], "对公结算演示终端")
        with self.assertRaises(DomainError) as raised:
            self.store.propose_desk("desk", "reader", "terminal", "save", {"name": "不该写成"}, "越权", False)
        self.assertEqual(raised.exception.code, "FORBIDDEN")
        self.assertEqual(self.store.snapshot("desk", "operator")["terminal"]["name"], "对公结算演示终端")

    def test_confirm_then_readback_and_noop_and_prod_reject(self):
        self.store.load_params("desk", "operator")
        pending = self.store.propose_desk("desk", "operator", "param", "update",
                                          {"name": "demo.sftp.port", "value": "8022", "note": "电子回单-端口"}, "改端口", False)
        self.assertEqual(self.store.snapshot("desk", "operator")["params"][3]["value"], "8021")
        done = self.store.execute("desk", "operator", pending["id"], pending["digest"])
        self.assertEqual(done["code"], "EXECUTED")
        self.assertEqual(done["readback"]["params"][3]["value"], "8022")
        again = self.store.propose_desk("desk", "operator", "param", "update",
                                        {"name": "demo.sftp.port", "value": "8022", "note": "电子回单-端口"}, "重复", True)
        noop = self.store.execute("desk", "operator", again["id"], again["digest"])
        self.assertEqual(noop["code"], "NO_CHANGE")
        self.assertIsNone(noop["ticket"])
        with self.assertRaises(DomainError) as raised:
            self.store.propose_desk("desk", "operator", "param", "delete", {"name": "demo.prod.gateway"}, "删生产", False)
        self.assertEqual(raised.exception.code, "INVALID_CHANGE")
        with self.assertRaises(DomainError):
            self.store.propose_desk("desk", "operator", "ip", "add", {
                "tenant": "X", "merchant": "M", "terminal": "TN", "proxy": "192.168.7.132", "proxy_port": 1,
                "client": "10.8.2.31", "client_port": 1}, "照片地址", False)
        before = len(self.store.snapshot("desk", "operator")["ips"])
        suggested = self.store.suggest_client("desk", "operator")
        self.assertEqual(suggested["client"], "10.8.2.31")
        self.assertEqual(len(self.store.snapshot("desk", "operator")["ips"]), before)

    def test_terminal_save_and_stale_confirmation(self):
        first = self.store.propose_desk("desk", "operator", "terminal", "save", {"name": "夜班演示终端"}, "改名", False)
        second = self.store.propose_desk("desk", "operator", "terminal", "save", {"concurrency": 4}, "改并发", False)
        self.store.execute("desk", "operator", first["id"], first["digest"])
        with self.assertRaises(DomainError) as raised:
            self.store.execute("desk", "operator", second["id"], second["digest"])
        self.assertEqual(raised.exception.code, "STALE")
        self.assertEqual(self.store.snapshot("desk", "operator")["terminal"]["name"], "夜班演示终端")
        self.assertEqual(self.store.snapshot("desk", "operator")["terminal"]["concurrency"], 3)


class DeskHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(str(Path(self.temp.name) / "desk.sqlite3"))
        self.patch = patch.object(server, "STORE", self.store)
        self.patch.start()
        self.http = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:" + str(self.http.server_port)
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.role = None

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=3)
        self.patch.stop()
        self.store.db.close()
        self.temp.cleanup()

    def call(self, path, body=None, role="operator"):
        if self.role != role:
            login = urllib.request.Request(self.base + "/api/login", data=json.dumps({"username": role, "password": "demo2026"}).encode(),
                                           headers={"Content-Type": "application/json", "X-Demo-Request": "1"})
            with self.opener.open(login) as resp:
                resp.read()
            self.role = role
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, headers={"Content-Type": "application/json", "X-Demo-Request": "1"},
                                     method="GET" if body is None else "POST")
        try:
            with self.opener.open(req) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode())

    def test_http_load_confirm_and_reader_omission(self):
        status, loaded = self.call("/api/ops/desk/load", {})
        self.assertEqual(status, 200)
        self.assertTrue(any(row["name"] == "demo.prod.gateway" for row in self.call("/api/ops/state")[1]["params"]))
        status, proposal = self.call("/api/ops/desk/propose", {
            "kind": "param", "action": "update",
            "payload": {"name": "demo.sftp.port", "value": "8022", "note": "电子回单-端口"},
            "reason": "页面确认前不写入", "submit": False})
        self.assertEqual(status, 200)
        self.assertEqual(next(row["value"] for row in self.call("/api/ops/state")[1]["params"] if row["name"] == "demo.sftp.port"), "8021")
        status, done = self.call("/api/ops/execute", {"proposal_id": proposal["id"], "digest": proposal["digest"]})
        self.assertEqual(done["readback"]["params"] and next(row["value"] for row in done["readback"]["params"] if row["name"] == "demo.sftp.port"), "8022")
        page = Path(server.ROOT, "index.html").read_text(encoding="utf-8")
        self.assertIn("终端注册信息管理", page)
        self.assertIn("固定地址配置", page)
        self.assertIn("+ 加载配置参数", page)
        reader = self.call("/api/ops/state", role="reader")[1]
        self.assertFalse(any(row["name"] == "demo.prod.gateway" for row in reader["params"]))
        self.assertFalse(any(row["env"] == "prod" for row in reader["ips"]))
        denied = self.call("/api/ops/desk/propose", {
            "kind": "ip", "action": "delete", "payload": {"id": "ip-test-1"}, "reason": "越权删除", "submit": False}, role="reader")
        self.assertEqual(denied[0], 403)


if __name__ == "__main__":
    unittest.main()
