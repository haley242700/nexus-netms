"""生成 Home Lab 总览 Grafana 仪表盘 JSON。"""
import json
from tools.common import NEXUS_DIR

DS = {"type": "prometheus", "uid": "prometheus"}
PALETTE = ["#0A84FF", "#64D2FF", "#BF5AF2", "#30D158", "#FFD60A", "#FF9F0A", "#FF453A", "#5E5CE6"]


def target(expr, legend="", refid="A"):
    return {"expr": expr, "legendFormat": legend, "refId": refid, "datasource": DS}


def base(pid, title, x, y, w, h, ptype):
    return {
        "id": pid, "title": title, "type": ptype, "datasource": DS,
        "gridPos": {"x": x, "y": y, "w": w, "h": h},
        "transparent": True,
        "fieldConfig": {"defaults": {}, "overrides": []},
        "options": {},
        "targets": [],
    }


def gauge(pid, title, x, expr, unit="percent"):
    p = base(pid, title, x, 0, 6, 5, "gauge")
    p["targets"] = [target(expr)]
    p["fieldConfig"]["defaults"] = {
        "unit": unit, "min": 0, "max": 100, "decimals": 1,
        "color": {"mode": "thresholds"},
        "thresholds": {"mode": "absolute", "steps": [
            {"color": "#30D158", "value": None},
            {"color": "#FFD60A", "value": 70},
            {"color": "#FF453A", "value": 90}]},
    }
    p["options"] = {
        "showThresholdLabels": False, "showThresholdMarkers": True,
        "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
    }
    return p


def stat(pid, title, x, expr, unit, color="#64D2FF"):
    p = base(pid, title, x, 0, 6, 5, "stat")
    p["targets"] = [target(expr)]
    p["fieldConfig"]["defaults"] = {"unit": unit, "color": {"mode": "fixed", "fixedColor": color}}
    p["options"] = {
        "colorMode": "value", "graphMode": "none", "justifyMode": "center",
        "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
    }
    return p


def timeseries(pid, title, x, y, queries, unit, stack=False):
    p = base(pid, title, x, y, 12, 8, "timeseries")
    p["targets"] = [target(e, l, refid=chr(65 + i)) for i, (e, l) in enumerate(queries)]
    p["fieldConfig"]["defaults"] = {
        "unit": unit,
        "color": {"mode": "palette-classic"},
        "custom": {
            "drawStyle": "line", "lineWidth": 2, "fillOpacity": 14,
            "lineInterpolation": "smooth", "showPoints": "never",
            "spanNulls": True, "gradientMode": "opacity",
            "stacking": {"mode": "normal" if stack else "off"},
            "axisPlacement": "auto",
        },
        "thresholds": {"mode": "absolute", "steps": []},
    }
    p["options"] = {
        "legend": {"displayMode": "table", "placement": "bottom", "showLegend": True,
                   "calcs": ["last", "max"], "sortBy": "Last", "sortDesc": True},
        "tooltip": {"mode": "multi", "sort": "desc"},
    }
    return p


panels = [
    gauge(1, "NAS CPU 使用率", 0,
          '100 - (avg(irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)'),
    gauge(2, "内存使用率", 6,
          '(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100'),
    gauge(3, "存储池使用率", 12,
          '100 - (node_filesystem_avail_bytes{mountpoint="/volume1"} / node_filesystem_size_bytes{mountpoint="/volume1"}) * 100'),
    stat(4, "NAS 运行时间", 18, 'time() - node_boot_time_seconds', "s"),
    timeseries(5, "CPU 负载与使用率", 0, 5, [
        ('100 - (avg(irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)', "CPU 使用率 %"),
        ("node_load1", "1 分钟负载"),
        ("node_load5", "5 分钟负载"),
    ], "percent"),
    timeseries(6, "内存", 12, 5, [
        ("node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes", "已用"),
        ("node_memory_MemAvailable_bytes", "可用"),
        ("node_memory_Cached_bytes", "缓存"),
    ], "bytes"),
    timeseries(7, "NAS 网络吞吐", 0, 13, [
        ('irate(node_network_receive_bytes_total{device!~"lo|docker.*|veth.*|br-.*"}[5m]) * 8', "{{device}} ↓ 接收"),
        ('irate(node_network_transmit_bytes_total{device!~"lo|docker.*|veth.*|br-.*"}[5m]) * 8', "{{device}} ↑ 发送"),
    ], "bps"),
    timeseries(8, "磁盘读写", 12, 13, [
        ('irate(node_disk_read_bytes_total{device=~"sd.|nvme.*"}[5m])', "{{device}} 读取"),
        ('irate(node_disk_written_bytes_total{device=~"sd.|nvme.*"}[5m])', "{{device}} 写入"),
    ], "Bps"),
    timeseries(9, "网络延迟（ICMP）", 0, 21, [
        ('probe_duration_seconds{job="ping"} * 1000', "{{name}}"),
    ], "ms"),
    timeseries(10, "丢包率", 12, 21, [
        ('(1 - probe_success{job="ping"}) * 100', "{{name}}"),
    ], "percent"),
    timeseries(11, "Docker 容器 CPU TOP", 0, 29, [
        ('topk(8, sum by (name)(irate(container_cpu_usage_seconds_total{name!=""}[5m]))) * 100', "{{name}}"),
    ], "percent"),
    timeseries(12, "Docker 容器内存 TOP", 12, 29, [
        ('topk(8, container_memory_usage_bytes{name!=""})', "{{name}}"),
    ], "bytes"),
]

dashboard = {
    "uid": "homelab-overview",
    "title": "Home Lab · 家庭网络总览",
    "tags": ["homelab", "nas"],
    "timezone": "browser",
    "refresh": "30s",
    "schemaVersion": 36,
    "version": 1,
    "editable": True,
    "graphTooltip": 1,
    "time": {"from": "now-6h", "to": "now"},
    "panels": panels,
}

with (NEXUS_DIR / "grafana" / "dashboards" / "homelab.json").open("w", encoding="utf-8") as f:
    json.dump({"dashboard": dashboard, "overwrite": True} if False else dashboard, f, ensure_ascii=False, indent=2)
print("dashboard json written, panels:", len(panels))
