"""测速信息集成服务。

一个轻量反向代理：
- 把请求转发给 Librespeed（默认 http://192.168.110.54:8088），
  并注入 X-Forwarded-For，使 Librespeed 看到真实客户端 IP；
- 对 HTML 页面注入一小段脚本：测速前显示当前连接的 AP 信息，
  并通过 telemetry_extra 把 AP 信息写入测速遥测记录；
- /api/ap-info?ip=<客户端IP> 反查锐捷睿易无线终端列表。

凭据只从环境变量读取，任何日志不输出密码 / token / sid。
"""
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import requests

UPSTREAM = os.getenv("LIBRESPEED_URL", "http://192.168.110.54:8088").rstrip("/")
LISTEN_PORT = int(os.getenv("AP_SERVER_PORT", "8090"))
ROAM_LOG_DIR = os.getenv("ROAM_LOG_DIR", "/app/logs")
ROAM_LOG_FILE = os.path.join(ROAM_LOG_DIR, "roam_log.jsonl")
ROAM_POLL_INTERVAL = int(os.getenv("ROAM_POLL_INTERVAL", "300"))  # 秒

HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "content-length",
    "content-encoding", "host",
}

from ap_lookup import ReyeeClient, _clean  # noqa: E402

CLIENT = ReyeeClient()


def roam_poller() -> None:
    """后台每 ROAM_POLL_INTERVAL 秒记录一次全网无线终端的 AP 归属。"""
    while True:
        time.sleep(ROAM_POLL_INTERVAL)
        if not CLIENT.ready():
            continue
        try:
            stas = CLIENT.get_sta_list()
        except Exception:
            continue  # 查询失败（如后台维护中）则跳过本轮
        try:
            os.makedirs(ROAM_LOG_DIR, exist_ok=True)
            ts = time.strftime("%Y-%m-%dT%H:%M:%S")
            with open(ROAM_LOG_FILE, "a", encoding="utf-8") as handle:
                for sta in stas:
                    handle.write(json.dumps({
                        "ts": ts,
                        "ip": sta.get("userIp"),
                        "mac": sta.get("mac"),
                        "host": _clean(sta.get("hostName")) or None,
                        "ssid": sta.get("ssid"),
                        "apSn": sta.get("sn"),
                        "apName": _clean(sta.get("deviceAliasName")),
                        "band": sta.get("band"),
                        "channel": sta.get("channel"),
                        "rssi": sta.get("rssi"),
                        "rate": sta.get("rxrate"),
                    }, ensure_ascii=False) + "\n")
        except OSError:
            pass


def read_roam_log(limit: int) -> list:
    """读取最近 limit 条漫游日志（按时间正序返回）。"""
    if not os.path.exists(ROAM_LOG_FILE):
        return []
    with open(ROAM_LOG_FILE, "r", encoding="utf-8") as handle:
        lines = handle.readlines()[-limit:]
    records = []
    for line in lines:
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except ValueError:
                pass
    return records


class QuietServer(ThreadingHTTPServer):
    """对客户端主动断连（浏览器取消请求等）保持安静，不打印堆栈。"""

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (BrokenPipeError, ConnectionResetError)):
            return
        super().handle_error(request, client_address)

INJECT = """
<div id="apInfoBanner" style="margin:12px auto;max-width:800px;padding:10px 16px;border-radius:8px;background:#16324f;color:#eaf4ff;font-size:14px;text-align:center;font-family:sans-serif;">正在获取 AP 信息…</div>
<script>
(function(){
  var banner = document.getElementById('apInfoBanner');
  function setText(t){ if (banner) banner.textContent = t; }
  function hide(){ if (banner) banner.style.display = 'none'; }
  fetch('backend/getIP.php').then(function(r){return r.json();}).then(function(g){
    var ip = g.processedString;
    return fetch('api/ap-info?ip=' + encodeURIComponent(ip)).then(function(r){return r.json();}).then(function(a){
      window.__apInfo = { ip: ip, ap: a };
      if (a && a.connected) {
        var dev = (a.hostName && a.hostName.toUpperCase() !== 'NULL') ? a.hostName : ip;
        setText('\\uD83D\\uDCF6 测速设备 ' + dev + ' 当前连接：' + a.apName + '（SSID ' + a.ssid + ' · ' + a.band + ' · 信道 ' + a.channel + ' · 信号 ' + a.rssi + ' dBm）');
      } else {
        setText('\\uD83D\\uDD17 设备 IP ' + ip + ' 未接入无线（有线连接或不在本网络）');
      }
      try {
        if (typeof s !== 'undefined' && s && typeof s.setParameter === 'function' && typeof s.start === 'function') {
          var origStart = s.start.bind(s);
          s.start = function(){
            try { s.setParameter('telemetry_extra', JSON.stringify({ clientIp: ip, apInfo: a })); } catch(e){}
            origStart();
          };
        }
      } catch(e){}
    });
  }).catch(function(){ setText('AP 信息获取失败（不影响测速）'); setTimeout(hide, 8000); });
})();
</script>
"""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # 静音默认日志，避免刷日志
        pass

    def _log(self, msg):
        if os.getenv("AP_DEBUG"):
            print(msg, flush=True)

    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _ap_info(self, query):
        ip = (parse_qs(query).get("ip") or [""])[0]
        if not CLIENT.ready():
            return self._send_json({"connected": False, "note": "服务端未配置锐捷凭据"}, status=500)
        try:
            self._send_json(CLIENT.lookup_by_ip(ip))
        except Exception as exc:  # 不泄露内部细节给前端
            self._send_json({"connected": False, "note": "查询失败"}, status=502)

    def _proxy(self, inject=False):
        parsed = urlparse(self.path)
        url = UPSTREAM + parsed.path
        if parsed.query:
            url += "?" + parsed.query
        length = self.headers.get("Content-Length")
        body = self.rfile.read(int(length)) if length else None
        if os.getenv("AP_DEBUG") and body and len(body) < 4096:
            preview = body.decode("utf-8", "ignore")
            self._log(f"PROXY {self.command} {parsed.path} body={preview[:800]}")
        else:
            self._log(f"PROXY {self.command} {parsed.path} body_len={len(body) if body else 0}")
        headers = {
            k: v for k, v in self.headers.items()
            if k.lower() not in HOP_BY_HOP and k.lower() != "accept-encoding"
        }
        headers["X-Forwarded-For"] = self.client_address[0]
        try:
            resp = requests.request(
                self.command, url, headers=headers, data=body,
                stream=True, timeout=120, allow_redirects=False,
            )
        except requests.RequestException:
            self.send_error(502, "上游 Librespeed 不可达")
            return
        content = b""
        if self.command != "HEAD":
            content = resp.raw.read()
        ctype = resp.headers.get("Content-Type", "")
        if inject and "text/html" in ctype.lower() and content:
            lower = content.lower()
            pos = lower.rfind(b"</body>")
            snippet = INJECT.encode("utf-8")
            content = content[:pos] + snippet + content[pos:] if pos >= 0 else content + snippet
        self.send_response(resp.status_code)
        for k, v in resp.headers.items():
            if k.lower() not in HOP_BY_HOP:
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(content)
            except (BrokenPipeError, ConnectionResetError):
                pass  # 客户端提前断开（如浏览器取消重复请求），无需处理

    def _dispatch(self, inject=False):
        parsed = urlparse(self.path)
        if parsed.path == "/api/ap-info":
            return self._ap_info(parsed.query)
        if parsed.path == "/api/health":
            return self._send_json({"ok": True, "upstream": UPSTREAM, "reyee_configured": CLIENT.ready()})
        if parsed.path == "/api/roam-log":
            limit = (parse_qs(parsed.query).get("limit") or ["200"])[0]
            try:
                limit = min(int(limit), 5000)
            except ValueError:
                limit = 200
            return self._send_json({"file": ROAM_LOG_FILE, "records": read_roam_log(limit)})
        self._proxy(inject=inject)

    do_GET = lambda self: self._dispatch(inject=True)
    do_POST = lambda self: self._dispatch(inject=False)
    do_HEAD = lambda self: self._dispatch(inject=False)


def main() -> int:
    if not CLIENT.ready():
        print("警告：未配置 EG_URL / EG_PASSWORD，AP 查询将不可用", flush=True)
    if os.getenv("ROAM_LOG_DISABLE") != "1":
        threading.Thread(target=roam_poller, daemon=True).start()
        print(f"漫游日志已启用：每 {ROAM_POLL_INTERVAL} 秒记录 -> {ROAM_LOG_FILE}", flush=True)
    server = QuietServer(("0.0.0.0", LISTEN_PORT), Handler)
    print(f"AP 信息集成服务已启动：http://0.0.0.0:{LISTEN_PORT} -> {UPSTREAM}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
