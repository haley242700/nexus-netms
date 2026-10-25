import time
from urllib.parse import quote

import requests

BASE = "http://192.168.110.54"
session = requests.Session()


def get(path):
    response = session.get(BASE + path, timeout=15)
    response.raise_for_status()
    return response


def sample(name, text):
    prefix = name + "{"
    return [line for line in text.splitlines() if line.startswith(prefix)]


def timestamp(text):
    for line in text.splitlines():
        if line.startswith("reyee_exporter_last_collect_timestamp_seconds "):
            return float(line.rsplit(" ", 1)[1])
    raise AssertionError("缺少采集时间戳")


first = get(":9108/metrics").text
time.sleep(4)
second = get(":9108/metrics").text
assert "reyee_exporter_collect_success 1" in second, "采集状态异常"
delta = timestamp(second) - timestamp(first)
assert 2 <= delta <= 7, f"采集时间戳未按 3 秒更新：{delta}"
for metric in (
    "reyee_gateway_traffic_bytes_total",
    "reyee_ap_traffic_bytes_total",
    "reyee_client_traffic_bytes_total",
):
    rows = sample(metric, second)
    assert rows and any(float(row.rsplit(" ", 1)[1]) > 0 for row in rows), f"{metric} 无非零数据"
    query = get(":3002/api/query?query=" + quote(metric)).json()
    assert query["status"] == "success" and query["data"]["result"], f"Prometheus 无 {metric}"
    print(metric, len(rows), "条，Prometheus 查询正常")

app = get(":3002/app.js").text
html = get(":3002/").text
assert "const REFRESH_INTERVAL = 3000" in app
assert "requestAnimationFrame" in app
assert 'id="gateway-history"' in html
print(f"采集时间戳间隔 {delta:.0f} 秒；页面为 3 秒刷新，累计与滚动代码已生效")

events = get(":3002/api/events").json()
assert events["since"] == "2026-10-25"
assert events["roam"]["count"] > 0
assert sum(ap["joinCount"] for ap in events["roam"]["apStats"]) == events["roam"]["count"]
assert sum(ap["leaveCount"] for ap in events["roam"]["apStats"]) == events["roam"]["count"]
assert "recent" in events["roam"] and "recent" in events["anomalies"]
events_html = get(":3002/events").text
assert 'id="roam-list"' in events_html and 'id="anomaly-list"' in events_html
print(
    f"事件页面正常：{events['roam']['count']} 次漫游，"
    f"{events['anomalies']['total']} 次异常（终端 {events['anomalies']['clientCount']}，"
    f"AP {events['anomalies']['apCount']}），历史始于 {events['since']}"
)
