"""测速结果持久化、绝对评分与同组合历史分位分析。"""
import json
import math
import os
import sqlite3
import time

MIN_SAMPLES = 5
RELIABLE_SAMPLES = 20
PERCENTILES = (1, 5, 20, 50, 80, 95, 99)
METRICS = {
    "download": {"label": "下载速率", "unit": "Mbps", "higherBetter": True, "weight": 0.40},
    "upload": {"label": "上传速率", "unit": "Mbps", "higherBetter": True, "weight": 0.25},
    "ping": {"label": "网络延迟", "unit": "ms", "higherBetter": False, "weight": 0.20},
    "jitter": {"label": "抖动", "unit": "ms", "higherBetter": False, "weight": 0.15},
}
RATE_BASE = ((0, 0), (10, 5), (50, 15), (100, 30), (300, 55), (500, 70))
WIRED_RATE_ANCHORS = RATE_BASE + ((1000, 80), (1600, 88), (2000, 95), (2500, 100))
WIRELESS_RATE_ANCHORS = RATE_BASE + ((1000, 85), (1600, 93), (2401, 100))
JITTER_ANCHORS = ((0, 100), (1, 100), (2, 95), (5, 80), (10, 60), (20, 35), (50, 10), (80, 0))
SCORE_ANCHORS = {
    "wired": {
        "download": WIRED_RATE_ANCHORS,
        "upload": WIRED_RATE_ANCHORS,
        "ping": ((0, 100), (3, 100), (5, 95), (10, 85), (20, 70), (30, 55), (50, 35), (100, 10), (150, 0)),
        "jitter": JITTER_ANCHORS,
    },
    "wireless": {
        "download": WIRELESS_RATE_ANCHORS,
        "upload": WIRELESS_RATE_ANCHORS,
        "ping": ((0, 100), (5, 100), (10, 95), (20, 85), (30, 70), (50, 45), (100, 10), (150, 0)),
        "jitter": JITTER_ANCHORS,
    },
}


def clean_text(value, fallback="未识别", limit=120):
    text = str(value or "").strip()
    if text.upper() in {"NULL", "UNDEFINED", "NONE"}:
        text = ""
    return (text or fallback)[:limit]


def metric_value(payload, key):
    value = float(payload[key])
    if not math.isfinite(value) or value < 0 or value > 100000:
        raise ValueError(f"invalid {key}")
    return round(value, 3)


def score_metric(key, value, access_type="wired"):
    anchors = SCORE_ANCHORS[access_type][key]
    if value <= anchors[0][0]:
        return anchors[0][1]
    if value >= anchors[-1][0]:
        return anchors[-1][1]
    for (left_x, left_y), (right_x, right_y) in zip(anchors, anchors[1:]):
        if left_x <= value <= right_x:
            ratio = (value - left_x) / (right_x - left_x)
            return round(left_y + ratio * (right_y - left_y), 1)
    return 0


def score_results(metrics, access_type="wired"):
    scores = {key: score_metric(key, metrics[key], access_type) for key in METRICS}
    overall = round(sum(scores[key] * config["weight"] for key, config in METRICS.items()), 1)
    grade = "卓越" if overall >= 90 else "良好" if overall >= 80 else "中等" if overall >= 70 else "合格" if overall >= 60 else "待优化"
    return {"overall": overall, "grade": grade, "accessType": access_type, "metrics": scores}


def percentile(values, percent):
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent / 100
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def superiority(values, current, higher_better):
    """当前值在经验分布中的位置，并列值按半计，避免夸大排名。"""
    less = sum(value < current for value in values)
    equal = sum(value == current for value in values)
    if not higher_better:
        less = sum(value > current for value in values)
    return round((less + equal * 0.5) / len(values) * 100, 1)


def context_identity(context, gateway_host):
    """生成稳定组合键；有线交换机以 SN 隔离历史，以型号和 IP 展示。"""
    client_ip = clean_text(context.get("clientIp"), "未知 IP", 64)
    client_mac = clean_text(context.get("clientMac"), "", 32).lower()
    wireless = bool(clean_text(context.get("band"), "") or clean_text(context.get("ssid"), ""))
    access_type = "wireless" if wireless else "wired"
    switch_sn = clean_text(context.get("switchSn"), "", 64)
    if wireless:
        connection_device = clean_text(context.get("apName"))
        connection_key = connection_device
    elif switch_sn:
        connection_device = clean_text(context.get("switchName") or context.get("switchModel"), f"交换机 {switch_sn}")
        connection_key = f"switch:{switch_sn}"
    else:
        connection_device = "未识别交换机"
        connection_key = connection_device
    gateway = f"网关 {gateway_host}" if gateway_host else "未识别网关"
    client_key = client_mac or f"ip:{client_ip}"
    return {
        "clientKey": client_key,
        "clientIp": client_ip,
        "accessType": access_type,
        "connectionDevice": connection_device,
        "gateway": gateway,
        "comboKey": "|".join((client_key, access_type, connection_key, gateway)),
    }


def connect(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    db = sqlite3.connect(path, timeout=5)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.execute("""
        CREATE TABLE IF NOT EXISTS speedtest_results(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            combo_key TEXT NOT NULL,
            client_key TEXT NOT NULL,
            client_name TEXT NOT NULL,
            client_ip TEXT NOT NULL,
            access_type TEXT NOT NULL,
            connection_device TEXT NOT NULL,
            gateway TEXT NOT NULL,
            download REAL NOT NULL,
            upload REAL NOT NULL,
            ping REAL NOT NULL,
            jitter REAL NOT NULL,
            context_json TEXT NOT NULL
        )
    """)
    db.execute("CREATE INDEX IF NOT EXISTS idx_speedtest_combo_ts ON speedtest_results(combo_key,ts)")
    return db


def analyze_rows(rows, current):
    sample_size = len(rows)
    response = {
        "sampleSize": sample_size,
        "minimumSamples": MIN_SAMPLES,
        "reliableSamples": RELIABLE_SAMPLES,
        "reliable": sample_size >= RELIABLE_SAMPLES,
        "needed": max(0, MIN_SAMPLES - sample_size),
        "metrics": {},
    }
    for key, config in METRICS.items():
        values = [float(row[key]) for row in rows]
        item = {**config, "current": current[key]}
        if sample_size >= MIN_SAMPLES:
            item["percentiles"] = {str(p): round(percentile(values, p), 3) for p in PERCENTILES}
            item["superiority"] = superiority(values, current[key], config["higherBetter"])
            item["deltaMedian"] = round(current[key] - percentile(values, 50), 3)
        response["metrics"][key] = item
    return response


def record_and_analyze(path, payload, context, client_name, gateway_host):
    metrics = {key: metric_value(payload, key) for key in METRICS}
    identity = context_identity(context, gateway_host)
    safe_context = {
        key: clean_text(context.get(key), "", 200)
        for key in (
            "clientMac", "hostName", "apName", "apSn", "ssid", "band", "channel", "rssi", "rxRate",
            "switchName", "switchModel", "switchIp", "switchSn",
        )
    }
    name = clean_text(client_name or context.get("hostName") or context.get("clientIp"), "未知终端")
    db = connect(path)
    try:
        cursor = db.execute("""
            INSERT INTO speedtest_results(
                ts,combo_key,client_key,client_name,client_ip,access_type,
                connection_device,gateway,download,upload,ping,jitter,context_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            time.time(), identity["comboKey"], identity["clientKey"], name,
            identity["clientIp"], identity["accessType"], identity["connectionDevice"],
            identity["gateway"], metrics["download"], metrics["upload"],
            metrics["ping"], metrics["jitter"], json.dumps(safe_context, ensure_ascii=False),
        ))
        result_id = cursor.lastrowid
        rows = db.execute("""
            SELECT download,upload,ping,jitter FROM speedtest_results
            WHERE combo_key=? ORDER BY ts,id
        """, (identity["comboKey"],)).fetchall()
        db.commit()
    finally:
        db.close()
    return {
        "saved": True,
        "resultId": result_id,
        "terminal": name,
        "identity": identity,
        "context": safe_context,
        "scores": score_results(metrics, identity["accessType"]),
        "analysis": analyze_rows(rows, metrics),
    }
