"""NEXUS：静态页面、只读 Prometheus 代理和只读事件统计接口。"""
import json
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

PORT = int(os.getenv("DASHBOARD_PORT", "3001"))
PROMETHEUS = os.getenv("PROMETHEUS_URL", "http://prometheus:9090").rstrip("/")
EVENT_DB = os.getenv("EVENT_DB_PATH", "/app/events/events.db")
ROOT = Path("/app/dashboard")
PROM_SESSION = requests.Session()
for scheme in ("http://", "https://"):
    PROM_SESSION.mount(scheme, requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=32))
FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/events": ("events.html", "text/html; charset=utf-8"),
    "/events.html": ("events.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/events.css": ("events.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/events.js": ("events.js", "application/javascript; charset=utf-8"),
}


def rows(cursor):
    return [dict(row) for row in cursor.fetchall()]


def event_stats():
    db = sqlite3.connect(f"file:{EVENT_DB}?mode=ro", uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    try:
        roam = dict(db.execute(
            """SELECT COUNT(*) AS count,AVG(duration_s) AS avgDuration,
               AVG(CASE WHEN trigger_rssi NOT IN (0,-95,-99) THEN trigger_rssi END) AS avgRssi,
               COUNT(duration_s) AS durationSamples
               FROM roam_events"""
        ).fetchone())
        roam["apStats"] = rows(db.execute(
            """WITH ap_names(name) AS (
                   SELECT DISTINCT name FROM ap_state WHERE name IS NOT NULL AND name!=''
               ), directional_counts AS (
                   SELECT to_ap AS name,COUNT(*) AS joins,0 AS leaves
                   FROM roam_events WHERE to_ap IS NOT NULL AND to_ap!='' GROUP BY to_ap
                   UNION ALL
                   SELECT from_ap AS name,0 AS joins,COUNT(*) AS leaves
                   FROM roam_events WHERE from_ap IS NOT NULL AND from_ap!='' GROUP BY from_ap
               ), ap_counts AS (
                   SELECT name,SUM(joins) AS joinCount,SUM(leaves) AS leaveCount
                   FROM directional_counts GROUP BY name
               )
               SELECT n.name,COALESCE(c.joinCount,0) AS joinCount,
                   COALESCE(c.leaveCount,0) AS leaveCount
               FROM ap_names n LEFT JOIN ap_counts c ON c.name=n.name
               ORDER BY (joinCount+leaveCount) DESC,n.name"""
        ))
        anomalies = dict(db.execute(
            """SELECT COUNT(*) AS total,
               SUM(CASE WHEN entity_type='client' THEN 1 ELSE 0 END) AS clientCount,
               SUM(CASE WHEN entity_type='ap' THEN 1 ELSE 0 END) AS apCount,
               SUM(CASE WHEN status='open' THEN 1 ELSE 0 END) AS active
               FROM offline_events WHERE excluded=0"""
        ).fetchone())
        for key in ("total", "clientCount", "apCount", "active"):
            anomalies[key] = anomalies[key] or 0
        reasons = rows(db.execute(
            """SELECT COALESCE(cause,reason,'设备未上报原因') AS reason,COUNT(*) AS count
               FROM offline_events WHERE excluded=0
               GROUP BY COALESCE(cause,reason,'设备未上报原因') ORDER BY count DESC"""
        ))
        recent_roams = rows(db.execute(
            """SELECT r.ts,r.mac,COALESCE(n.name,r.client) AS client,
               r.from_ap,r.to_ap,r.trigger_rssi,r.duration_s,r.source
               FROM roam_events r LEFT JOIN client_names n ON n.mac=r.mac
               ORDER BY r.ts DESC LIMIT 40"""
        ))
        recent_offline = rows(db.execute(
            """SELECT o.id,o.start_ts,o.end_ts,o.entity_type,o.entity_id,
               COALESCE(n.name,o.name) AS name,o.ap,
               COALESCE(o.cause,o.reason,'设备未上报原因') AS reason,
               COALESCE(o.conclusion,'非漫游离线') AS conclusion,
               o.last_rssi,o.status,o.source FROM offline_events o
               LEFT JOIN client_names n ON o.entity_type='client' AND n.mac=o.entity_id
               WHERE o.excluded=0 ORDER BY o.start_ts DESC LIMIT 50"""
        ))
        event_ids = [event["id"] for event in recent_offline]
        if event_ids:
            placeholders = ",".join("?" for _ in event_ids)
            evidence_rows = rows(db.execute(
                f"""SELECT event_id,ts,kind,label,detail,raw FROM event_evidence
                    WHERE event_id IN ({placeholders}) ORDER BY ts,id""",
                event_ids,
            ))
            evidence_by_event = {}
            for evidence in evidence_rows:
                evidence_by_event.setdefault(evidence.pop("event_id"), []).append(evidence)
            for event in recent_offline:
                event["evidence"] = evidence_by_event.get(event["id"], [])
        else:
            for event in recent_offline:
                event["evidence"] = []
        since = db.execute("SELECT value FROM meta WHERE key='events_since'").fetchone()
        return {
            "since": since[0] if since else None,
            "roam": {**roam, "recent": recent_roams},
            "anomalies": {**anomalies, "reasons": reasons, "recent": recent_offline},
        }
    finally:
        db.close()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def send_bytes(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status, payload):
        self.send_bytes(status, json.dumps(payload, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def proxy_query(self, endpoint, allowed):
        parsed = urlparse(self.path)
        incoming = parse_qs(parsed.query)
        params = {key: incoming[key][0] for key in allowed if key in incoming}
        if "query" not in params:
            self.send_bytes(400, b'{"error":"missing query"}', "application/json")
            return
        try:
            response = PROM_SESSION.get(f"{PROMETHEUS}/api/v1/{endpoint}", params=params, timeout=10)
            self.send_bytes(response.status_code, response.content, "application/json; charset=utf-8")
        except requests.RequestException as exc:
            self.send_json(502, {"status": "error", "error": type(exc).__name__})

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/query":
            self.proxy_query("query", {"query"})
            return
        if path == "/api/query_range":
            self.proxy_query("query_range", {"query", "start", "end", "step"})
            return
        if path == "/api/events":
            try:
                self.send_json(200, event_stats())
            except (OSError, sqlite3.Error) as exc:
                self.send_json(503, {"error": type(exc).__name__})
            return
        if path == "/api/health":
            self.send_json(200, {"status": "ok"})
            return
        item = FILES.get(path)
        if not item:
            self.send_bytes(404, "Not Found".encode(), "text/plain; charset=utf-8")
            return
        filename, content_type = item
        try:
            self.send_bytes(200, (ROOT / filename).read_bytes(), content_type)
        except OSError:
            self.send_bytes(500, "Dashboard asset unavailable".encode(), "text/plain; charset=utf-8")

    def log_request(self, code="-", size="-"):
        if isinstance(code, int) and code < 400:
            return
        self.log_message('"%s" %s %s', self.requestline, str(code), str(size))

    def log_message(self, fmt, *args):
        print(f"[dashboard] {self.client_address[0]} {fmt % args}", flush=True)


if __name__ == "__main__":
    print(f"[dashboard] NEXUS 已启动 :{PORT}，Prometheus={PROMETHEUS}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
