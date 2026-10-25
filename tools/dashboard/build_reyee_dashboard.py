"""生成睿易 Wi-Fi 专属 Grafana 看板（数据源由只读 exporter 提供）。"""
import json
from tools.common import NEXUS_DIR

DS = {"type": "prometheus", "uid": "prometheus"}


def target(expr, legend="", refid="A", instant=False):
    return {
        "expr": expr,
        "legendFormat": legend,
        "refId": refid,
        "datasource": DS,
        "instant": instant,
    }


def panel(pid, title, ptype, x, y, w, h):
    return {
        "id": pid,
        "title": title,
        "type": ptype,
        "datasource": DS,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "transparent": True,
        "fieldConfig": {"defaults": {}, "overrides": []},
        "options": {},
        "targets": [],
    }


def thresholds(steps):
    return {"mode": "absolute", "steps": [{"color": color, "value": value} for color, value in steps]}


def stat(pid, title, x, expr, color="#64D2FF", unit="none", steps=None):
    p = panel(pid, title, "stat", x, 0, 4, 4)
    p["targets"] = [target(expr, instant=True)]
    p["fieldConfig"]["defaults"] = {
        "unit": unit,
        "decimals": 0,
        "color": {"mode": "thresholds" if steps else "fixed", "fixedColor": color},
        "thresholds": thresholds(steps or [("#30D158", None)]),
    }
    p["options"] = {
        "colorMode": "value",
        "graphMode": "none",
        "justifyMode": "center",
        "textMode": "auto",
        "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
    }
    return p


def timeseries(pid, title, x, y, queries, unit, w=12, h=8, stack=False, min_value=None):
    p = panel(pid, title, "timeseries", x, y, w, h)
    p["targets"] = [target(expr, legend, chr(65 + i)) for i, (expr, legend) in enumerate(queries)]
    p["fieldConfig"]["defaults"] = {
        "unit": unit,
        "min": min_value,
        "color": {"mode": "palette-classic"},
        "custom": {
            "drawStyle": "line",
            "lineWidth": 2,
            "fillOpacity": 14,
            "lineInterpolation": "smooth",
            "showPoints": "never",
            "spanNulls": False,
            "gradientMode": "opacity",
            "stacking": {"mode": "normal" if stack else "off"},
            "axisPlacement": "auto",
        },
        "thresholds": thresholds([]),
    }
    p["options"] = {
        "legend": {
            "displayMode": "table",
            "placement": "bottom",
            "showLegend": True,
            "calcs": ["last", "max"],
            "sortBy": "Last",
            "sortDesc": True,
        },
        "tooltip": {"mode": "multi", "sort": "desc"},
    }
    return p


def ap_table():
    p = panel(9, "AP 清单与在线状态", "table", 0, 12, 12, 9)
    p["targets"] = [
        dict(target('reyee_ap_online{kind="ap"} * on(ap, sn) group_left(model, ip) reyee_ap_info', refid="A", instant=True), format="table"),
    ]
    p["transformations"] = [
        {"id": "organize", "options": {
            "excludeByName": {"Time": True, "__name__": True, "sn": True, "kind": True, "instance": True, "job": True},
            "renameByName": {
                "ap": "AP",
                "model": "型号",
                "ip": "IP 地址",
                "Value": "在线",
                "Value (A)": "在线",
            },
        }},
    ]
    p["fieldConfig"]["defaults"] = {"custom": {"align": "auto", "cellOptions": {"type": "auto"}}}
    p["fieldConfig"]["overrides"] = [{
        "matcher": {"id": "byName", "options": "在线"},
        "properties": [
            {"id": "mappings", "value": [
                {"type": "value", "options": {"0": {"text": "离线", "color": "#FF453A", "index": 0}}},
                {"type": "value", "options": {"1": {"text": "在线", "color": "#30D158", "index": 1}}},
            ]},
            {"id": "custom.cellOptions", "value": {"type": "color-background"}},
        ],
    }]
    p["options"] = {"showHeader": True, "sortBy": [{"displayName": "AP", "desc": False}]}
    return p


def weakest_clients():
    p = panel(11, "弱信号终端 TOP 10（越负越差）", "bargauge", 0, 21, 12, 10)
    p["targets"] = [target("bottomk(10, reyee_client_rssi_dbm)", "{{client}} · {{ap}}", instant=True)]
    p["fieldConfig"]["defaults"] = {
        "unit": "dBm",
        "min": -100,
        "max": -30,
        "decimals": 0,
        "color": {"mode": "thresholds"},
        "thresholds": thresholds([("#FF453A", None), ("#FF9F0A", -75), ("#FFD60A", -67), ("#30D158", -60)]),
    }
    p["options"] = {
        "displayMode": "gradient",
        "orientation": "horizontal",
        "showUnfilled": True,
        "valueMode": "color",
        "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
    }
    return p


panels = [
    stat(1, "在线 AP", 0, 'sum(reyee_ap_online{kind="ap"})'),
    stat(2, "无线终端", 4, "reyee_clients_total", "#BF5AF2"),
    stat(3, "5 GHz 终端", 8, 'count(reyee_client_rssi_dbm{band="5G"}) or vector(0)', "#0A84FF"),
    stat(4, "弱信号终端 < -75 dBm", 12, "count(reyee_client_rssi_dbm < -75) or vector(0)", steps=[("#30D158", None), ("#FFD60A", 1), ("#FF453A", 3)]),
    stat(5, "MLO 终端", 16, "sum(reyee_client_mlo_enabled) or vector(0)", "#5E5CE6"),
    stat(6, "采集状态", 20, "reyee_exporter_collect_success", steps=[("#FF453A", None), ("#30D158", 1)]),
    timeseries(7, "各 AP 关联终端数", 0, 4, [
        ('sum by(ap)(reyee_ap_clients{kind="ap"})', "{{ap}}"),
    ], "none", stack=True),
    timeseries(8, "信道利用率", 12, 4, [
        ("reyee_ap_channel_utilization_percent", "{{ap}} · {{band}}"),
    ], "percent"),
    ap_table(),
    timeseries(10, "噪声底", 12, 12, [
        ("reyee_ap_noise_floor_dbm", "{{ap}} · {{band}}"),
    ], "dBm", h=9),
    weakest_clients(),
    timeseries(12, "最差终端信号趋势", 12, 21, [
        ("bottomk(6, reyee_client_rssi_dbm)", "{{client}} · {{ap}}"),
    ], "dBm", h=10),
    timeseries(13, "终端实时流量 TOP 8", 0, 31, [
        ("topk(8, rate(reyee_client_traffic_bytes_total[5m]) * 8)", "{{client}} · {{direction}}"),
    ], "bps", h=9),
    timeseries(14, "各 Wi-Fi 终端数量", 12, 31, [
        ("count by(ssid, band)(reyee_client_rssi_dbm)", "{{ssid}} · {{band}}"),
    ], "none", h=9),
    timeseries(15, "AP 发射功率", 0, 40, [
        ("reyee_ap_txpower_percent", "{{ap}} · {{band}}"),
    ], "percent", w=24, h=8),
    timeseries(16, "AP Ping 延迟", 0, 48, [
        ('probe_duration_seconds{job="ap_ping"} * 1000', "{{name}}"),
    ], "ms", h=8),
    timeseries(17, "AP Ping 丢包率（5 分钟）", 12, 48, [
        ('(1 - avg_over_time(probe_success{job="ap_ping"}[5m])) * 100', "{{name}}"),
    ], "percent", h=8),
]

# 固定关键纵轴，避免少量历史数据让 Grafana 自动缩放到难以阅读的范围。
for p in panels:
    if p["id"] in (7, 14, 16):
        p["fieldConfig"]["defaults"]["min"] = 0
    elif p["id"] in (8, 15, 17):
        p["fieldConfig"]["defaults"]["min"] = 0
        p["fieldConfig"]["defaults"]["max"] = 100
    elif p["id"] in (10, 12):
        p["fieldConfig"]["defaults"]["min"] = -100
        p["fieldConfig"]["defaults"]["max"] = 0

dashboard = {
    "uid": "reyee-wifi",
    "title": "Reyee · 全屋 Wi-Fi 运行状态",
    "description": "每 30 秒通过睿易管理后台只读采集；不调用任何配置修改接口。",
    "tags": ["reyee", "wifi", "homelab"],
    "timezone": "browser",
    "refresh": "30s",
    "schemaVersion": 36,
    "version": 1,
    "editable": True,
    "graphTooltip": 1,
    "time": {"from": "now-6h", "to": "now"},
    "panels": panels,
}

path = NEXUS_DIR / "grafana" / "dashboards" / "reyee.json"
with path.open("w", encoding="utf-8") as f:
    json.dump(dashboard, f, ensure_ascii=False, indent=2)
print(f"dashboard json written: {path}, panels: {len(panels)}")
