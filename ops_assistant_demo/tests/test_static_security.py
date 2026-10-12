import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer

import server


class StaticSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'index.html').write_text('demo', encoding='utf-8')
        (self.root / '.env').write_text('fixture-only-not-a-credential', encoding='utf-8')
        (self.root / 'server.py').write_text('private source', encoding='utf-8')
        self.patch = patch.object(server, 'ROOT', self.root)
        self.patch.start()
        self.http = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:' + str(self.http.server_port)

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.patch.stop()
        self.temp.cleanup()

    def status(self, path, data=None):
        req = urllib.request.Request(self.base + path, data=data,
                                     headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status
        except urllib.error.HTTPError as exc:
            return exc.code

    def test_static_allowlist_never_serves_config_or_source(self):
        for path in ('/.env', '/%2eenv', '/server.py', '/.git/config', '/data/demo.sqlite3'):
            with self.subTest(path=path):
                self.assertEqual(self.status(path), 404)
        self.assertEqual(self.status('/'), 200)

    def test_public_generic_model_proxy_is_removed(self):
        self.assertEqual(self.status('/v1/chat/completions', b'{}'), 404)

    def test_unauthenticated_model_and_legacy_writes_are_denied(self):
        self.assertEqual(self.status('/api/chat', b'{}'), 403)
        self.assertEqual(self.status('/api/change', b'{"env":"drill","text":"fixture"}'), 404)


if __name__ == '__main__':
    unittest.main()
