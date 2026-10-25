"""验证事件只读 API 的结论、原因和证据输出，不启动服务、不访问网络。"""
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMP_ROOT = ROOT / "artifacts" / "tmp"
TEMP_ROOT.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(TEMP_ROOT)
sys.path.insert(0, str(ROOT / "apps" / "nexus" / "reyee-exporter"))
from event_store import EventStore

with tempfile.TemporaryDirectory() as tmp:
    db_path = str(Path(tmp) / "events.db")
    store = EventStore(db_path)
    now = 1792900000.0
    try:
        store.db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('events_since','2026-10-25')")
        users = [{"mac": "DE:51:44:74:80:1E", "connectType": "wireless", "deviceAliasName": "一楼客厅AP", "rssi": "-88"}]
        store.observe(users, [], {"DE:51:44:74:80:1E": "阿姨手机"}, now=now)
        store.observe([], [], {"DE:51:44:74:80:1E": "阿姨手机"}, now=now + 3)
        store.observe([], [], {"DE:51:44:74:80:1E": "阿姨手机"}, now=now + 6)
        store.ingest_syslog([
            [str(now + 3), "WLAN", "STA_ROAM", "6", "STA:(DE:51:44:74:80:1E) roam from OUT_AP (D8:33:2A:8A:85:25) rssi -88 to IN_AP(00:00:00:00:00:00) rssi 0"]
        ], {"DE:51:44:74:80:1E": "阿姨手机"}, {"D8:33:2A:8A:85:25": "一楼客厅AP"})
    finally:
        store.close()

    os.environ["EVENT_DB_PATH"] = db_path
    spec = importlib.util.spec_from_file_location("dashboard_server", ROOT / "apps" / "nexus" / "network-dashboard" / "dashboard_server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.event_stats()
    event = result["anomalies"]["recent"][0]
    assert event["name"] == "阿姨手机", event
    assert event["reason"] == "弱信号线索", event
    assert event["conclusion"] == "非漫游离线", event
    labels = {item["label"] for item in event["evidence"]}
    assert "实时采样确认终端消失" in labels, event
    assert "未观察到接入新 AP" in labels, event
    assert any(item["raw"] for item in event["evidence"] if item["label"] == "未观察到接入新 AP"), event
    print("事件 API 验证通过：名称、结论、原因、证据和原始日志均完整。")
