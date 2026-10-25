"""测速页与内部代理离线集成测试；全部服务仅绑定 127.0.0.1。"""
import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "apps" / "nexus" / "network-dashboard"


class UpstreamHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    received = []

    def reply(self, body, content_type="application/json"):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self):
        type(self).received.append((self.command, self.path))
        if self.path.startswith("/backend/getIP.php"):
            self.reply(json.dumps({"processedString": self.headers.get("X-Forwarded-For")}).encode())
        elif self.path.startswith("/speedtest.js"):
            self.reply(b"function Speedtest(){}", "application/javascript")
        elif self.path.startswith("/backend/garbage.php"):
            self.reply(b"x" * (1024 * 1024), "application/octet-stream")
        else:
            self.reply(b"ok", "text/plain")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        remaining = length
        while remaining:
            chunk = self.rfile.read(min(65536, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
        type(self).received.append((self.command, self.path, length, remaining))
        self.reply(json.dumps({"received": length - remaining}).encode())

    def log_message(self, *_args):
        pass


class FakeApClient:
    def __init__(self):
        self.seen = []

    def ready(self):
        return True

    def lookup_by_ip(self, ip):
        self.seen.append(ip)
        return {"connected": True, "clientIp": ip, "clientMac": "AA:BB:CC:DD:EE:FF", "hostName": "iPhone", "apName": "书房AP", "ssid": "Ubiquiti", "band": "5 GHz", "channel": "149", "rssi": "-52", "rxRate": "1201M"}


spec = importlib.util.spec_from_file_location("dashboard_speedtest", DASHBOARD / "dashboard_server.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.ROOT = DASHBOARD
module.AP_CLIENT = FakeApClient()
name_db = ROOT / "artifacts" / "tmp" / "speedtest-names.db"
name_db.parent.mkdir(parents=True, exist_ok=True)
db = __import__("sqlite3").connect(name_db)
db.execute("CREATE TABLE IF NOT EXISTS client_names(mac TEXT PRIMARY KEY,name TEXT)")
db.execute("INSERT OR REPLACE INTO client_names(mac,name) VALUES('AA:BB:CC:DD:EE:FF','我的手机')")
db.commit()
db.close()
module.EVENT_DB = str(name_db)

upstream = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
dashboard = ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
for server in (upstream, dashboard):
    threading.Thread(target=server.serve_forever, daemon=True).start()

module.LIBRESPEED = f"http://127.0.0.1:{upstream.server_address[1]}"
base = f"http://127.0.0.1:{dashboard.server_address[1]}"
client = requests.Session()
client.trust_env = False
try:
    for path in ("/speedtest", "/speedtest.css", "/speedtest-app.js", "/navigation.js"):
        response = client.get(base + path, timeout=5)
        assert response.status_code == 200, (path, response.status_code)
        assert response.headers["Cache-Control"] == "no-cache"
        cached = client.get(base + path, headers={"If-None-Match": response.headers["ETag"]}, timeout=5)
        assert cached.status_code == 304 and not cached.content, (path, cached.status_code)
    page = client.get(base + "/speedtest", timeout=5).text
    assert 'href="/speedtest"' in page and "当前测速环境" in page

    ap = client.get(base + "/api/ap-info", timeout=5).json()
    assert ap["connected"] and ap["apName"] == "书房AP"
    assert ap["displayName"] == "我的手机", ap
    assert module.AP_CLIENT.seen == ["127.0.0.1"], module.AP_CLIENT.seen

    engine = client.get(base + "/speedtest/engine/speedtest.js", timeout=5)
    assert engine.status_code == 200 and engine.text == "function Speedtest(){}"
    ip = client.get(base + "/speedtest/engine/backend/getIP.php", timeout=5).json()
    assert ip["processedString"] == "127.0.0.1", ip
    download = client.get(base + "/speedtest/engine/backend/garbage.php?ckSize=1", timeout=10)
    assert download.status_code == 200 and len(download.content) == 1024 * 1024
    payload = b"z" * (2 * 1024 * 1024)
    upload = client.post(base + "/speedtest/engine/backend/empty.php", data=payload, timeout=10)
    assert upload.status_code == 200 and upload.json()["received"] == len(payload), upload.text
    assert UpstreamHandler.received[-1][2:] == (len(payload), 0), UpstreamHandler.received[-1]

    module.LIBRESPEED = "http://127.0.0.1:1"
    unavailable = client.get(base + "/speedtest/engine/backend/getIP.php", timeout=5)
    assert unavailable.status_code == 502, unavailable.status_code
    print("测速集成验证通过：页面、AP 身份、真实 IP、1 MiB 下载、2 MiB 上传及故障降级均正常。")
finally:
    client.close()
    module.SPEED_SESSION.close()
    dashboard.shutdown()
    upstream.shutdown()
    dashboard.server_close()
    upstream.server_close()
