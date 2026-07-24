from __future__ import annotations

import argparse
import http.client
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
}


class ProxyHandler(BaseHTTPRequestHandler):
    upstream_base: str = ""
    upstream_api_key: str = ""

    def do_GET(self) -> None:
        self._proxy()

    def do_POST(self) -> None:
        self._proxy()

    def do_PUT(self) -> None:
        self._proxy()

    def do_PATCH(self) -> None:
        self._proxy()

    def do_DELETE(self) -> None:
        self._proxy()

    def do_OPTIONS(self) -> None:
        self._proxy()

    def _proxy(self) -> None:
        upstream = urlsplit(self.upstream_base)
        target_path = self.path
        body = None
        if "content-length" in self.headers:
            length = int(self.headers.get("content-length", "0"))
            body = self.rfile.read(length) if length else None

        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in HOP_BY_HOP_HEADERS
        }
        headers["Host"] = upstream.netloc
        if self.upstream_api_key and "authorization" not in {key.lower() for key in headers}:
            headers["Authorization"] = f"Bearer {self.upstream_api_key}"

        connection = http.client.HTTPConnection(
            upstream.hostname,
            upstream.port or (443 if upstream.scheme == "https" else 80),
            timeout=120,
        )
        if upstream.scheme == "https":
            connection = http.client.HTTPSConnection(
                upstream.hostname,
                upstream.port or 443,
                timeout=120,
            )

        try:
            connection.request(self.command, target_path, body=body, headers=headers)
            response = connection.getresponse()
            payload = response.read()

            self.send_response(response.status, response.reason)
            for key, value in response.getheaders():
                if key.lower() not in HOP_BY_HOP_HEADERS:
                    self.send_header(key, value)
            self.end_headers()
            self.wfile.write(payload)
        except Exception as exc:  # pragma: no cover - manual operator path
            self.send_error(502, f"Upstream proxy error: {exc}")
        finally:
            connection.close()

    def log_message(self, format: str, *args: object) -> None:
        sys.stdout.write("%s - - [%s] %s\n" % (self.client_address[0], self.log_date_time_string(), format % args))
        sys.stdout.flush()


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


def main() -> int:
    parser = argparse.ArgumentParser(description="Small LAN reverse proxy for CLIProxyAPI")
    parser.add_argument("--listen-host", default="0.0.0.0")
    parser.add_argument("--listen-port", type=int, default=3000)
    parser.add_argument("--upstream", required=True, help="Upstream base URL, e.g. http://100.85.49.112:8317/v1")
    parser.add_argument("--api-key", default=os.environ.get("CLIPROXYAPI_API_KEY", ""), help="Upstream API key; defaults to CLIPROXYAPI_API_KEY")
    args = parser.parse_args()

    ProxyHandler.upstream_base = args.upstream.rstrip("/")
    ProxyHandler.upstream_api_key = args.api_key.strip()
    server = ReusableThreadingHTTPServer((args.listen_host, args.listen_port), ProxyHandler)
    print(json.dumps({"listen": f"{args.listen_host}:{args.listen_port}", "upstream": ProxyHandler.upstream_base}, ensure_ascii=False))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
