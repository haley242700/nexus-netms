"""NEXUS 事件 V1 离线测试，不访问生产网络。"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMP_ROOT = ROOT / "artifacts" / "tmp"
TEMP_ROOT.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(TEMP_ROOT)
sys.path.insert(0, str(ROOT / "apps" / "nexus" / "reyee-exporter"))
from event_store import EventStore

AP_A = "D8:33:2A:8A:85:25"
AP_B = "D8:33:2A:8A:84:99"
CLIENT = "DE:51:44:74:80:1E"
AP_NAMES = {AP_A: "一楼客厅AP", AP_B: "负一电脑房AP"}
NAMES = {CLIENT: "阿姨手机"}


def user(mac=CLIENT, ap="一楼客厅AP", rssi="-60"):
    return {"mac": mac, "connectType": "wireless", "deviceAliasName": ap, "hostName": "test", "rssi": rssi}


def aps(online=True):
    return [{"serialNumber": "SN-A", "hostName": "一楼客厅AP", "band": "2.4G,5G" if online else "", "status": "ON" if online else "OFF", "mac": AP_A}]


def roam_log(ts, out=AP_A, new=AP_B, out_rssi=-80, mac=CLIENT):
    return [str(ts), "WLAN", "STA_ROAM", "6", f"STA:({mac}) roam from OUT_AP ({out}) rssi {out_rssi} to IN_AP({new}) rssi -50"]


class StoreCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = EventStore(str(Path(self.tmp.name) / "events.db"))
        self.store.db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('events_since','2026-10-25')")
        self.store.db.commit()
        self.t0 = 1792900000.0  # 2026-10-25，仅用于相对时间判定

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_zero_log_alone_does_not_create_anomaly(self):
        self.assertEqual(self.store.ingest_syslog([roam_log(self.t0, new="00:00:00:00:00:00")], NAMES, AP_NAMES), 1)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM offline_events").fetchone()[0], 0)

    def test_two_misses_and_zero_log_evidence(self):
        self.store.observe([user(rssi="-88")], aps(), NAMES, now=self.t0)
        self.store.observe([], aps(), NAMES, now=self.t0 + 3)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM offline_events").fetchone()[0], 0)
        self.store.ingest_syslog([roam_log(self.t0 + 3, new="00:00:00:00:00:00", out_rssi=-88)], NAMES, AP_NAMES)
        self.store.observe([], aps(), NAMES, now=self.t0 + 6)
        row = self.store.db.execute("SELECT * FROM offline_events").fetchone()
        self.assertEqual(row["cause"], "弱信号线索")
        evidence = self.store.db.execute("SELECT label FROM event_evidence WHERE event_id=?", (row["id"],)).fetchall()
        self.assertIn("未观察到接入新 AP", {item[0] for item in evidence})

    def test_special_rssi_does_not_create_weak_cause(self):
        for rssi in (-95, -99):
            self.store.db.execute("DELETE FROM client_state")
            self.store.db.execute("DELETE FROM offline_events")
            self.store.observe([user(rssi=str(rssi))], aps(), NAMES, now=self.t0)
            self.store.observe([], aps(), NAMES, now=self.t0 + 3)
            self.store.observe([], aps(), NAMES, now=self.t0 + 6)
            self.assertEqual(self.store.db.execute("SELECT cause FROM offline_events").fetchone()[0], "设备未上报原因")

    def test_roam_within_60_seconds_excludes_anomaly(self):
        self.store.observe([user()], aps(), NAMES, now=self.t0)
        self.store.observe([], aps(), NAMES, now=self.t0 + 3)
        self.store.observe([], aps(), NAMES, now=self.t0 + 6)
        self.store.observe([user(ap="负一电脑房AP")], aps(), NAMES, now=self.t0 + 30)
        row = self.store.db.execute("SELECT status,excluded FROM offline_events").fetchone()
        self.assertEqual(tuple(row), ("excluded", 1))

    def test_different_ap_after_long_offline_is_recovery(self):
        self.store.observe([user()], aps(), NAMES, now=self.t0)
        self.store.observe([], aps(), NAMES, now=self.t0 + 3)
        self.store.observe([], aps(), NAMES, now=self.t0 + 6)
        self.store.observe([user(ap="负一电脑房AP")], aps(), NAMES, now=self.t0 + 90)
        row = self.store.db.execute("SELECT status,excluded FROM offline_events").fetchone()
        self.assertEqual(tuple(row), ("recovered", 0))

    def test_live_and_syslog_roam_deduplicate(self):
        self.store.observe([user()], aps(), NAMES, now=self.t0)
        self.store.observe([user(ap="负一电脑房AP")], aps(), NAMES, now=self.t0 + 3)
        self.store.ingest_syslog([roam_log(self.t0 + 2)], NAMES, AP_NAMES)
        rows = self.store.db.execute("SELECT source FROM roam_events").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "syslog+live")

    def test_same_ap_is_not_roam(self):
        self.store.ingest_syslog([roam_log(self.t0, new=AP_A)], NAMES, AP_NAMES)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM roam_events").fetchone()[0], 0)

    def test_same_source_same_path_at_different_times_is_not_merged(self):
        self.store.ingest_syslog([roam_log(self.t0), roam_log(self.t0 + 20)], NAMES, AP_NAMES)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM roam_events").fetchone()[0], 2)

    def test_ap_reonline_is_evidence_not_cause(self):
        self.store.observe([], aps(), NAMES, now=self.t0)
        self.store.observe([], aps(False), NAMES, now=self.t0 + 3)
        event = self.store.db.execute("SELECT id,cause FROM offline_events WHERE entity_type='ap'").fetchone()
        self.store.ingest_syslog([[str(self.t0 + 5), "EASYSON", "DEVICE_REONLINE", "6", "device SN-A reonline"]])
        self.store.observe([], aps(), NAMES, now=self.t0 + 6)
        self.assertEqual(event["cause"], "设备未上报原因")
        labels = {row[0] for row in self.store.db.execute("SELECT label FROM event_evidence WHERE event_id=?", (event["id"],))}
        self.assertIn("设备重新上线", labels)


class RealLogCase(unittest.TestCase):
    def test_saved_real_logs_and_idempotency(self):
        payload = json.loads((ROOT / "tests" / "fixtures" / "syslog.json").read_text(encoding="utf-8"))
        logs = payload["data"]["log_list"]
        expected = len({"\0".join(str(value) for value in row) for row in logs})
        with tempfile.TemporaryDirectory() as tmp:
            store = EventStore(str(Path(tmp) / "events.db"))
            try:
                store.db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('events_since','2026-10-25')")
                store.db.commit()
                first = store.ingest_syslog(logs, NAMES, AP_NAMES)
                second = store.ingest_syslog(logs, NAMES, AP_NAMES)
                self.assertEqual(first, expected)
                self.assertEqual(second, 0)
                self.assertEqual(store.db.execute("SELECT COUNT(*) FROM syslog_events").fetchone()[0], expected)
                self.assertEqual(store.db.execute("SELECT COUNT(*) FROM offline_events").fetchone()[0], 0)
                self.assertEqual(store.db.execute("SELECT COUNT(*) FROM roam_events WHERE from_ap=to_ap").fetchone()[0], 0)
                self.assertEqual(store.db.execute("SELECT COUNT(*) FROM roam_events WHERE to_ap='00:00:00:00:00:00'").fetchone()[0], 0)
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
