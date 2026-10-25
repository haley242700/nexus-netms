"""NEXUS 生产只读健康检查：页面、API、事件口径与连续采集周期。"""
import json
import time

import requests

BASE = "http://192.168.110.54:3002"
METRICS = "http://192.168.110.54:9108/metrics"
session = requests.Session()


def timestamp(text):
    for line in text.splitlines():
        if line.startswith("reyee_exporter_last_collect_timestamp_seconds "):
            return float(line.rsplit(" ", 1)[1])
    raise AssertionError("缺少最近采集时间戳")


for path in ("/", "/events", "/app.js", "/events.js", "/styles.css", "/events.css", "/api/health", "/api/events"):
    response = session.get(BASE + path, timeout=15)
    assert response.status_code == 200, (path, response.status_code)

payload = session.get(BASE + "/api/events", timeout=15).json()
roam = payload["roam"]
assert sum(ap["joinCount"] for ap in roam["apStats"]) == roam["count"]
assert sum(ap["leaveCount"] for ap in roam["apStats"]) == roam["count"]
assert all(row["from_ap"] and row["to_ap"] and row["from_ap"] != row["to_ap"] for row in roam["recent"])
assert all(row["to_ap"] != "00:00:00:00:00:00" for row in roam["recent"])

stamps = []
deadline = time.monotonic() + 13
while time.monotonic() < deadline:
    response = session.get(METRICS, timeout=10)
    response.raise_for_status()
    assert "reyee_exporter_collect_success 1" in response.text
    current = timestamp(response.text)
    if not stamps or current != stamps[-1]:
        stamps.append(current)
    time.sleep(0.7)

deltas = [round(b - a, 3) for a, b in zip(stamps, stamps[1:])]
assert len(deltas) >= 3, f"有效采集样本不足：{stamps}"
assert all(2 <= delta <= 4 for delta in deltas), f"采集周期偏离 3 秒：{deltas}"
print(json.dumps({
    "routes_ok": 8,
    "roam_events": roam["count"],
    "ap_stats": len(roam["apStats"]),
    "recent_roam_pairs_ok": True,
    "collection_timestamps": len(stamps),
    "collection_deltas_seconds": deltas,
}, ensure_ascii=False, indent=2))
