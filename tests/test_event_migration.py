"""验证旧版事件数据库原地升级，不删除历史事件。"""
import sqlite3
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
    path = str(Path(tmp) / "events.db")
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT);
        INSERT INTO meta VALUES('events_since','2026-10-25');
        CREATE TABLE offline_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,start_ts REAL NOT NULL,end_ts REAL,
            entity_type TEXT NOT NULL,entity_id TEXT NOT NULL,name TEXT,ap TEXT,reason TEXT,
            last_rssi REAL,status TEXT NOT NULL DEFAULT 'open',excluded INTEGER NOT NULL DEFAULT 0,
            source TEXT NOT NULL DEFAULT 'live'
        );
        INSERT INTO offline_events(start_ts,entity_type,entity_id,name,reason,last_rssi)
        VALUES(1,'client','aa:bb:cc:dd:ee:ff','普通弱信号','离线前弱信号',-80);
        INSERT INTO offline_events(start_ts,entity_type,entity_id,name,reason,last_rssi)
        VALUES(2,'client','aa:bb:cc:dd:ee:00','特殊值','离线前弱信号',-95);
        INSERT INTO offline_events(start_ts,entity_type,entity_id,name,reason,last_rssi)
        VALUES(3,'ap','SN1','AP','未知',NULL);
    """)
    db.commit()
    db.close()

    store = EventStore(path)
    try:
        rows = store.db.execute("SELECT name,cause,reason FROM offline_events ORDER BY id").fetchall()
        assert [row["cause"] for row in rows] == ["弱信号线索", "设备未上报原因", "设备未上报原因"], rows
        assert all(row["reason"] == row["cause"] for row in rows), rows
        assert store.db.execute("SELECT COUNT(*) FROM offline_events").fetchone()[0] == 3
        assert store.db.execute("SELECT COUNT(*) FROM event_evidence").fetchone()[0] == 0
        print("旧数据库迁移验证通过：3 条历史事件保留，原因标签按新口径升级。")
    finally:
        store.close()
