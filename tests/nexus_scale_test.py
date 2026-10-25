"""十万级合成数据扩展性测试，全部在临时数据库执行，不访问生产服务。"""
import importlib.util
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMP_ROOT = ROOT / "artifacts" / "tmp"
TEMP_ROOT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "apps" / "nexus" / "reyee-exporter"))
from event_store import EventStore

COUNT = 50000
APS = ["一楼主卧AP", "一楼北卧AP", "一楼客厅AP", "负一卧室AP", "负一客厅AP", "负一电脑房AP"]
with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as tmp:
    path = str(Path(tmp) / "scale.db")
    store = EventStore(path)
    try:
        now = 1792900000
        store.db.executemany("INSERT INTO ap_state(sn,name,last_seen) VALUES(?,?,?)", [(f"SN{i}", name, now) for i, name in enumerate(APS)])
        store.db.executemany(
            "INSERT INTO roam_events(ts,mac,client,from_ap,to_ap,trigger_rssi,duration_s,source) VALUES(?,?,?,?,?,?,?,?)",
            [
                (now + i, f"aa:bb:cc:dd:{i // 100 % 256:02x}:{i % 256:02x}", "终端", APS[i % 6], APS[(i + 1) % 6], -70, 3, "live")
                for i in range(COUNT)
            ],
        )
        store.db.executemany(
            "INSERT INTO syslog_events(signature,ts,mac,from_ap,to_ap,module,tag,level,text) VALUES(?,?,?,?,?,?,?,?,?)",
            [
                (f"sig{i}", now + i, "aa:bb:cc:dd:ee:ff", "D8:33:2A:8A:85:25", "00:00:00:00:00:00", "WLAN", "STA_ROAM", "6", " synthetic ")
                for i in range(COUNT)
            ],
        )
        store.db.commit()
    finally:
        store.close()

    os.environ["EVENT_DB_PATH"] = path
    spec = importlib.util.spec_from_file_location("dashboard_scale", ROOT / "apps" / "nexus" / "network-dashboard" / "dashboard_server.py")
    dashboard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dashboard)
    timings = []
    for _ in range(7):
        started = time.perf_counter()
        result = dashboard.event_stats()
        timings.append((time.perf_counter() - started) * 1000)
        assert result["roam"]["count"] == COUNT
        assert len(result["roam"]["apStats"]) == 6
        assert sum(ap["joinCount"] for ap in result["roam"]["apStats"]) == COUNT
        assert sum(ap["leaveCount"] for ap in result["roam"]["apStats"]) == COUNT

    store = EventStore(path)
    try:
        started = time.perf_counter()
        store._record_roam(now + COUNT + 1, "aa:bb:cc:dd:ee:ff", "终端", APS[0], APS[1], -70, 3, "live")
        dedup_ms = (time.perf_counter() - started) * 1000
        old_logs = [[str(now + COUNT + i), "WLAN", "STA_ROAM", "6", f"unchanged {i}"] for i in range(2000)]
        assert store.ingest_syslog(old_logs) == len(old_logs)
        started = time.perf_counter()
        inserted = store.ingest_syslog(old_logs)
        repeat_ms = (time.perf_counter() - started) * 1000
        assert inserted == 0
    finally:
        store.close()
    print({
        "roam_rows": COUNT,
        "syslog_rows": COUNT,
        "event_stats_median_ms": round(statistics.median(timings), 2),
        "event_stats_p95_ms": round(sorted(timings)[-2], 2),
        "single_roam_write_ms": round(dedup_ms, 2),
        "repeat_2000_old_logs_ms": round(repeat_ms, 2),
    })
