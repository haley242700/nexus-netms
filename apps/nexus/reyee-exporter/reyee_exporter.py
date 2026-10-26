"""锐捷睿易 Prometheus exporter（只读，绝不调用任何配置接口）。

每 COLLECT_INTERVAL 秒通过 ap_lookup.ReyeeClient 采集 ap_list + sta_list，
/metrics 输出最近一次快照。采集失败保留旧数据并置 collect_success=0。
凭据从环境变量（EG_URL/EG_USERNAME/EG_PASSWORD）读取，绝不打印。
"""
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

from ap_lookup import ReyeeClient, _clean
from event_store import EventStore

PORT = int(os.getenv("EXPORTER_PORT", "9108"))
INTERVAL = float(os.getenv("COLLECT_INTERVAL", "3"))
STATIC_INTERVAL = float(os.getenv("STATIC_COLLECT_INTERVAL", "30"))
SYSLOG_INTERVAL = float(os.getenv("SYSLOG_COLLECT_INTERVAL", "30"))

# 用户确认的看板显示名，仅影响监控展示，不回写睿易后台。
LOCAL_NAME_OVERRIDES = {
    "f4:9d:8a:75:a2:af": "安克充电站",
    "a0:85:e3:e0:4a:34": "空调远程控制模块",
    "a0:85:e3:f6:b6:f0": "空调远程控制模块",
    "cc:ba:97:0e:2f:b4": "空调远程控制模块",
    "78:2e:03:85:5b:e3": "又又手表",
    "86:ff:81:81:b5:be": "我的手机",
    "de:51:44:74:80:1e": "阿姨手机",
    "7c:9e:bd:af:8d:14": "书房炫彩板",
}

_client = ReyeeClient()
_events = EventStore()
_lock = threading.Lock()
_metrics_text = "# 尚未完成首次采集\n"
_collect_success = 0
_collect_duration = 0.0
_last_collect_ts = 0.0
_last_syslog_collect = 0.0


def esc(value) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def num(value, default=None):
    """把接口返回的数字字符串安全转 float；空/异常返回 default。"""
    try:
        v = str(value).strip().rstrip("M").strip()
        if v.upper() in {"NULL", "UNDEFINED", "NONE", ""}:
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def normalize_mac(value) -> str:
    """统一冒号、横线和锐捷点分 MAC 格式，只按完整 MAC 匹配。"""
    compact = re.sub(r"[^0-9A-Fa-f]", "", _clean(value)).lower()
    return ":".join(compact[i:i + 2] for i in range(0, 12, 2)) if len(compact) == 12 else ""


def get_readonly_data(method: str, module: str, data=None, no_parse=False) -> dict:
    """调用只读接口，认证失效时自动重登一次。"""
    _client._ensure_session()
    params = {"module": module}
    if data is not None:
        params["data"] = data
    if no_parse:
        params["noParse"] = True
    body = {"method": method, "params": params}
    for _ in range(2):
        try:
            response = _client._sess.post(
                f"{_client.eg_url}/cgi-bin/luci/api/cmd?auth={_client._sid}",
                json=body,
                verify=False,
                timeout=_client.timeout,
                headers={
                    "Referer": f"{_client.eg_url}/cgi-bin/luci/",
                    "Origin": _client.eg_url,
                },
            )
            result = response.json()
        except (requests.RequestException, ValueError):
            result = {}
        if result.get("code") == 0:
            return result.get("data") or {}
        _client._sess = None
        _client._login()
    raise RuntimeError(f"只读接口 {method}/{module} 查询失败")


def get_remark_map() -> dict[str, str]:
    """只读获取用户在睿易后台设置的终端备注。"""
    data = get_readonly_data("devConfig.get", "devRemark")
    if "list" not in data:
        raise RuntimeError("终端备注接口缺少 list，保留上一份监控快照")
    return {
        mac: name
        for row in data.get("list") or []
        if (mac := normalize_mac(row.get("mac"))) and (name := _clean(row.get("name")))
    }


class Snapshot:
    def __init__(self):
        self.lines = []

    def add(self, name, value, labels=None, help_text=None, mtype="gauge"):
        if help_text:
            self.lines.append(f"# HELP {name} {help_text}")
            self.lines.append(f"# TYPE {name} {mtype}")
            # HELP/TYPE 只写一次
            self.add._seen = getattr(self.add, "_seen", set())
            self.add._seen.add(name)
        if value is None:
            return
        if labels:
            lbl = ",".join(f'{k}="{esc(v)}"' for k, v in labels.items() if v is not None)
            self.lines.append(f"{name}{{{lbl}}} {value}")
        else:
            self.lines.append(f"{name} {value}")

    def header(self, name, help_text, mtype="gauge"):
        self.lines.append(f"# HELP {name} {help_text}")
        self.lines.append(f"# TYPE {name} {mtype}")

    def text(self):
        return "\n".join(self.lines) + "\n"


_static_cache = None
_static_cache_at = 0.0


def get_static_data():
    """静态元数据缓存 30 秒，实时接口仍按 COLLECT_INTERVAL 查询。"""
    global _static_cache, _static_cache_at
    if _static_cache is None or time.time() - _static_cache_at >= STATIC_INTERVAL:
        try:
            _static_cache = {
                "aps": _client._cmd("ap_list").get("list") or [],
                "sta": _client.get_sta_list(),
                "remarks": get_remark_map(),
                "network": get_readonly_data("devConfig.get", "network"),
            }
            _static_cache_at = time.time()
        except Exception:
            if _static_cache is None:
                raise
    return _static_cache


def collect() -> None:
    global _metrics_text, _collect_success, _collect_duration, _last_collect_ts, _last_syslog_collect
    started = time.time()
    try:
        static = get_static_data()
        aps, sta, remarks, network = static["aps"], static["sta"], static["remarks"], static["network"]
        users = get_readonly_data(
            "devSta.get", "user_list", {"devType": "all", "dataType": "timely"}
        ).get("list") or []
        flow_status = get_readonly_data("devSta.get", "flow_status").get("data") or []
        # 离线终端也保留备注映射，确保历史事件不会退回 MAC 或原厂主机名。
        names = {**remarks, **LOCAL_NAME_OVERRIDES}
        for row in [*sta, *users]:
            mac = normalize_mac(row.get("mac"))
            if mac:
                host = _clean(row.get("hostName"))
                names[mac] = LOCAL_NAME_OVERRIDES.get(mac) or remarks.get(mac) or host or mac
        if started - _last_syslog_collect >= SYSLOG_INTERVAL:
            _last_syslog_collect = started
            try:
                log_data = get_readonly_data(
                    "devSta.get", "std_syslog_get",
                    {"user": "web", "option": "log_detail"}, no_parse=True,
                )
                logs = log_data.get("log_list")
                if not isinstance(logs, list):
                    raise RuntimeError("系统日志接口缺少 log_list")
                ap_names = {
                    normalize_mac(ap.get("mac")): _clean(ap.get("hostName")) or _clean(ap.get("serialNumber"))
                    for ap in aps if normalize_mac(ap.get("mac"))
                }
                inserted = _events.ingest_syslog(logs, names, ap_names)
                if inserted:
                    print(f"[reyee-exporter] 系统日志新增 {inserted} 条", flush=True)
            except Exception as syslog_exc:
                print(f"[reyee-exporter] 系统日志采集失败：{type(syslog_exc).__name__}: {syslog_exc}", flush=True)
        try:
            _events.observe(users, aps, names)
        except Exception as event_exc:
            print(f"[reyee-exporter] 事件记录失败：{type(event_exc).__name__}: {event_exc}", flush=True)
        s = Snapshot()

        s.header("reyee_ap_info", "AP 基础信息（恒为 1）")
        s.header("reyee_ap_online", "AP 在线状态（1=在线，0=离线）")
        s.header("reyee_ap_clients", "AP 当前关联终端数")
        s.header("reyee_ap_channel", "AP 当前信道")
        s.header("reyee_ap_channel_utilization_percent", "AP 信道利用率（%）")
        s.header("reyee_ap_noise_floor_dbm", "AP 噪声底（dBm）")
        s.header("reyee_ap_txpower_percent", "AP 发射功率（%）")
        s.header("reyee_ap_throughput_bps", "AP 当前关联无线终端实时吞吐（字节/秒）")
        s.header("reyee_ap_traffic_bytes_total", "AP 当前关联无线终端累计流量（字节）", "counter")
        s.header("reyee_gateway_throughput_bps", "网关 WAN 实时吞吐（字节/秒）")
        s.header("reyee_gateway_traffic_bytes_total", "网关 WAN 累计流量（字节）", "counter")
        s.header("reyee_clients_total", "当前无线终端总数")
        s.header("reyee_client_rssi_dbm", "终端信号强度（dBm，越接近 0 越好）")
        s.header("reyee_client_rxrate_mbps", "终端无线协商速率（Mbps）")
        s.header("reyee_client_throughput_bps", "终端实时吞吐（字节/秒）")
        s.header("reyee_client_mlo_enabled", "终端是否启用 MLO（Wi-Fi 7）")
        s.header("reyee_client_traffic_bytes_total", "终端累计流量（字节）", "counter")

        # AP 无设备级历史计数器，累计口径仅为当前关联无线终端。
        ap_traffic = {
            _clean(ap.get("hostName")) or _clean(ap.get("serialNumber")): {
                "up": 0.0, "down": 0.0, "total_up": 0.0, "total_down": 0.0
            }
            for ap in aps if _clean(ap.get("band"))
        }
        for user in users:
            if user.get("connectType") != "wireless":
                continue
            ap_name = _clean(user.get("deviceAliasName")) or _clean(user.get("sn"))
            if ap_name in ap_traffic:
                traffic = ap_traffic[ap_name]
                traffic["up"] += max(0.0, num(user.get("flowUp"), 0.0))
                traffic["down"] += max(0.0, num(user.get("flowDown"), 0.0))
                traffic["total_up"] += max(0.0, num(user.get("up"), 0.0))
                traffic["total_down"] += max(0.0, num(user.get("down"), 0.0))

        # flow_status 的速率单位为 Kibibit/s，乘 128 换算为 Byte/s。
        wan_ports = {str(row.get("portId")) for row in network.get("wan") or []}
        gateway_rates = {"up": 0.0, "down": 0.0}
        gateway_totals = {"up": 0.0, "down": 0.0}
        for row in flow_status:
            if str(row.get("lpid")) in wan_ports:
                gateway_rates["down"] += max(0.0, num(row.get("input_rate"), 0.0)) * 128
                gateway_rates["up"] += max(0.0, num(row.get("output_rate"), 0.0)) * 128
                gateway_totals["down"] += max(0.0, num(row.get("input_total"), 0.0))
                gateway_totals["up"] += max(0.0, num(row.get("output_total"), 0.0))
        for direction, rate in gateway_rates.items():
            s.add("reyee_gateway_throughput_bps", rate, {"direction": direction})
            s.add("reyee_gateway_traffic_bytes_total", gateway_totals[direction], {"direction": direction})

        for ap in aps:
            bands = [b.strip() for b in str(ap.get("band") or "").split(",") if b.strip()]
            labels = {
                "ap": ap.get("hostName") or ap.get("serialNumber"),
                "sn": ap.get("serialNumber"),
                "model": ap.get("devModel") or ap.get("deviceType"),
                "ip": ap.get("ip"),
                "kind": "ap" if bands else "gateway",
            }
            s.add("reyee_ap_info", 1, labels)
            base = {"ap": labels["ap"], "sn": labels["sn"], "kind": labels["kind"]}
            s.add("reyee_ap_online", 1 if str(ap.get("status")).upper() == "ON" else 0, base)
            s.add("reyee_ap_clients", num(ap.get("staNum"), 0), base)
            if labels["kind"] == "ap":
                traffic = ap_traffic.get(labels["ap"], {})
                for direction in ("up", "down"):
                    s.add("reyee_ap_throughput_bps", traffic.get(direction),
                          {"ap": labels["ap"], "direction": direction})
                    s.add("reyee_ap_traffic_bytes_total", traffic.get(f"total_{direction}"),
                          {"ap": labels["ap"], "direction": direction})

            channels = str(ap.get("channel") or "").split(",")
            chutils = str(ap.get("chutil") or "").split(",")
            noises = str(ap.get("channf") or "").split(",")
            powers = str(ap.get("txpower") or "").split(",")
            for i, band in enumerate(bands):
                bl = dict(base, band=band)
                raw_channel = str(channels[i] if i < len(channels) else "").strip()
                automatic = raw_channel.lower().startswith("auto-")
                channel = num(raw_channel[5:] if automatic else raw_channel)
                s.add("reyee_ap_channel", channel,
                      dict(bl, mode="auto" if automatic else "manual"))
                s.add("reyee_ap_channel_utilization_percent", num(chutils[i] if i < len(chutils) else None), bl)
                s.add("reyee_ap_noise_floor_dbm", num(noises[i] if i < len(noises) else None), bl)
                s.add("reyee_ap_txpower_percent", num(powers[i] if i < len(powers) else None), bl)

        s.add("reyee_clients_total", len(sta))
        for c in sta:
            mac = normalize_mac(c.get("mac"))
            host = _clean(c.get("hostName"))
            name = LOCAL_NAME_OVERRIDES.get(mac) or remarks.get(mac) or host or mac or "unknown"
            base = {
                "client": name, "mac": mac, "host": host,
                "ap": _clean(c.get("deviceAliasName")) or _clean(c.get("sn")),
                "band": _clean(c.get("band")), "ssid": _clean(c.get("ssid")),
            }
            s.add("reyee_client_rssi_dbm", num(c.get("rssi")), base)
            s.add("reyee_client_mlo_enabled", 1 if str(c.get("is_mlo")) == "1" else 0,
                  {"client": name, "mac": mac, "host": host})

        for user in users:
            mac = normalize_mac(user.get("mac"))
            host = _clean(user.get("hostName"))
            name = LOCAL_NAME_OVERRIDES.get(mac) or remarks.get(mac) or host or mac or "unknown"
            wireless = user.get("connectType") == "wireless"
            base = {
                "client": name, "mac": mac, "host": host,
                "ap": _clean(user.get("deviceAliasName")),
                "connection": "wireless" if wireless else "wired",
            }
            s.add("reyee_client_throughput_bps", max(0.0, num(user.get("flowUp"), 0.0)),
                  dict(base, direction="up"))
            s.add("reyee_client_throughput_bps", max(0.0, num(user.get("flowDown"), 0.0)),
                  dict(base, direction="down"))
            s.add("reyee_client_traffic_bytes_total", num(user.get("up")),
                  {"client": name, "mac": mac, "host": host, "direction": "up"})
            s.add("reyee_client_traffic_bytes_total", num(user.get("down")),
                  {"client": name, "mac": mac, "host": host, "direction": "down"})
            if wireless:
                s.add("reyee_client_rxrate_mbps", num(user.get("rxrate")), base)

        with _lock:
            _metrics_text = s.text()
            _collect_success = 1
            _collect_duration = time.time() - started
            _last_collect_ts = time.time()
    except Exception as exc:  # 采集失败：保留旧数据，只标记失败
        with _lock:
            _collect_success = 0
            _collect_duration = time.time() - started
            _last_collect_ts = time.time()
        print(f"[reyee-exporter] 采集失败：{type(exc).__name__}: {exc}", flush=True)


def collector_loop():
    while True:
        started = time.monotonic()
        collect()
        # 采集耗时计入周期间隔；接口偶发超时也避免无间隔紧密重试。
        elapsed = time.monotonic() - started
        time.sleep(max(0.1, INTERVAL - elapsed))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?")[0] != "/metrics":
            self.send_response(404)
            self.end_headers()
            return
        with _lock:
            body = _metrics_text
            body += f"reyee_exporter_collect_success {_collect_success}\n"
            body += f"reyee_exporter_collect_duration_seconds {_collect_duration:.3f}\n"
            body += f"reyee_exporter_last_collect_timestamp_seconds {_last_collect_ts:.0f}\n"
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def main():
    if "--once" in sys.argv:
        collect()
        with _lock:
            print(_metrics_text)
        print(f"collect_success={_collect_success} duration={_collect_duration:.2f}s")
        return
    threading.Thread(target=collector_loop, daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"[reyee-exporter] 已启动 :{PORT}/metrics，每 {INTERVAL}s 采集（只读）", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
