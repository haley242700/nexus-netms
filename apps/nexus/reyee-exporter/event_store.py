"""NEXUS 漫游与非漫游离线事件：SQLite 持久化，仅处理只读遥测。"""
import hashlib
import os
import re
import sqlite3
import time


def norm_mac(value):
    compact = re.sub(r"[^0-9A-Fa-f]", "", str(value or "")).lower()
    return ":".join(compact[i:i + 2] for i in range(0, 12, 2)) if len(compact) == 12 else ""


def clean(value):
    value = str(value or "").strip()
    return "" if value.upper() in {"NULL", "UNDEFINED", "NONE"} else value


def number(value):
    try:
        return float(str(value).strip().rstrip("M"))
    except (TypeError, ValueError):
        return None


class EventStore:
    ZERO_MAC = "00:00:00:00:00:00"
    ROAM_RE = re.compile(
        r"STA:\((?P<sta>[0-9A-F:]{17})\) roam from OUT_AP \((?P<out>[0-9A-F:]{17})\) "
        r"rssi (?P<out_rssi>-?\d+) to IN_AP\((?P<in>[0-9A-F:]{17})\) rssi (?P<in_rssi>-?\d+)",
        re.I,
    )
    REONLINE_RE = re.compile(r"device\s+(\S+)\s+reonline", re.I)

    def __init__(self, path=None):
        self.path = path or os.getenv("EVENT_DB_PATH", "/app/data/events.db")
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        # 采集线程独占写入，页面通过另一个只读连接查询。
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self._schema()
        self.db.execute(
            "INSERT OR IGNORE INTO meta(key,value) VALUES('events_since',?)",
            (time.strftime("%Y-%m-%d"),),
        )
        self.db.commit()

    def _schema(self):
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS roam_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL, mac TEXT NOT NULL, client TEXT,
            from_ap TEXT, to_ap TEXT, trigger_rssi REAL, duration_s REAL,
            source TEXT NOT NULL DEFAULT 'live',
            UNIQUE(mac,ts,from_ap,to_ap)
        );
        CREATE TABLE IF NOT EXISTS offline_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_ts REAL NOT NULL, end_ts REAL,
            entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
            name TEXT, ap TEXT, reason TEXT, last_rssi REAL,
            status TEXT NOT NULL DEFAULT 'open', excluded INTEGER NOT NULL DEFAULT 0,
            source TEXT NOT NULL DEFAULT 'live'
        );
        CREATE TABLE IF NOT EXISTS client_state(
            mac TEXT PRIMARY KEY, client TEXT, ap TEXT, last_seen REAL,
            last_rssi REAL, missing_since REAL, offline_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS ap_state(
            sn TEXT PRIMARY KEY, name TEXT, last_seen REAL, offline_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS client_names(
            mac TEXT PRIMARY KEY, name TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS syslog_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signature TEXT NOT NULL UNIQUE, ts REAL NOT NULL,
            mac TEXT, from_ap TEXT, to_ap TEXT, out_rssi REAL, in_rssi REAL, sn TEXT,
            module TEXT, tag TEXT, level TEXT, text TEXT
        );
        CREATE TABLE IF NOT EXISTS event_evidence(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL, ts REAL, kind TEXT NOT NULL,
            label TEXT NOT NULL, detail TEXT, raw TEXT,
            UNIQUE(event_id,kind,ts,detail)
        );
        CREATE INDEX IF NOT EXISTS idx_roam_ts ON roam_events(ts DESC);
        CREATE INDEX IF NOT EXISTS idx_roam_dedup ON roam_events(mac,from_ap,to_ap,ts DESC);
        CREATE INDEX IF NOT EXISTS idx_roam_to_ap ON roam_events(to_ap);
        CREATE INDEX IF NOT EXISTS idx_roam_from_ap ON roam_events(from_ap);
        CREATE INDEX IF NOT EXISTS idx_offline_ts ON offline_events(start_ts DESC);
        CREATE INDEX IF NOT EXISTS idx_offline_entity ON offline_events(entity_type,entity_id,status,start_ts DESC);
        CREATE INDEX IF NOT EXISTS idx_offline_visible ON offline_events(excluded,start_ts DESC);
        CREATE INDEX IF NOT EXISTS idx_syslog_mac_ts ON syslog_events(mac,ts DESC);
        CREATE INDEX IF NOT EXISTS idx_syslog_sn_ts ON syslog_events(sn,ts DESC);
        CREATE INDEX IF NOT EXISTS idx_syslog_zero ON syslog_events(mac,to_ap,tag,ts DESC);
        CREATE INDEX IF NOT EXISTS idx_evidence_event ON event_evidence(event_id,ts);
        """)
        # 在线升级旧数据库，不删除任何既有事件。
        offline_columns = {row[1] for row in self.db.execute("PRAGMA table_info(offline_events)")}
        if "conclusion" not in offline_columns:
            self.db.execute("ALTER TABLE offline_events ADD COLUMN conclusion TEXT")
        if "cause" not in offline_columns:
            self.db.execute("ALTER TABLE offline_events ADD COLUMN cause TEXT")
        self.db.execute("UPDATE offline_events SET conclusion=COALESCE(conclusion,'非漫游离线')")
        self.db.execute("""
            UPDATE offline_events SET cause=CASE
                WHEN reason='离线前弱信号' AND last_rssi NOT IN (0,-95,-99) THEN '弱信号线索'
                ELSE '设备未上报原因' END
            WHERE cause IS NULL OR cause=''
        """)
        self.db.execute("UPDATE offline_events SET reason=cause")

    @staticmethod
    def _is_weak(rssi):
        # -95/-99 的含义尚未由设备文档证实，只展示原值，不参与原因分类。
        return rssi is not None and rssi <= -75 and rssi not in (0, -95, -99)

    def _add_evidence(self, event_id, ts, kind, label, detail="", raw=""):
        self.db.execute(
            """INSERT OR IGNORE INTO event_evidence(event_id,ts,kind,label,detail,raw)
               VALUES(?,?,?,?,?,?)""",
            (event_id, ts, kind, label, clean(detail), clean(raw)),
        )

    def _set_weak_cause(self, event_id):
        self.db.execute(
            "UPDATE offline_events SET cause='弱信号线索',reason='弱信号线索' WHERE id=? AND cause='设备未上报原因'",
            (event_id,),
        )

    def _attach_zero_log(self, event_id, row):
        detail = f"离开 AP {row['from_ap'] or '未知'} · 日志记录信号 {row['out_rssi']} dBm"
        self._add_evidence(event_id, row["ts"], "syslog", "未观察到接入新 AP", detail, row["text"])
        if self._is_weak(row["out_rssi"]):
            self._set_weak_cause(event_id)

    def _attach_recent_zero_logs(self, event_id, mac, now):
        rows = self.db.execute(
            """SELECT * FROM syslog_events
               WHERE mac=? AND to_ap=? AND tag='STA_ROAM' AND ts BETWEEN ?-60 AND ?+60
               ORDER BY ts DESC LIMIT 3""",
            (mac, self.ZERO_MAC, now, now),
        ).fetchall()
        for row in rows:
            self._attach_zero_log(event_id, row)

    def _open_offline(self, now, entity_type, entity_id, name, ap, rssi, source):
        cause = "弱信号线索" if entity_type == "client" and self._is_weak(rssi) else "设备未上报原因"
        conclusion = "AP 离线" if entity_type == "ap" else "非漫游离线"
        cursor = self.db.execute(
            """INSERT INTO offline_events
               (start_ts,entity_type,entity_id,name,ap,reason,last_rssi,source,conclusion,cause)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (now, entity_type, entity_id, name, ap, cause, rssi, source, conclusion, cause),
        )
        event_id = cursor.lastrowid
        if entity_type == "client":
            detail = f"最后连接 {ap or '未知 AP'}"
            if rssi is not None:
                detail += f" · 最后采样信号 {rssi:g} dBm"
            self._add_evidence(event_id, now, "snapshot", "实时采样确认终端消失", detail)
            self._attach_recent_zero_logs(event_id, entity_id, now)
        else:
            self._add_evidence(event_id, now, "snapshot", "实时采样确认 AP 非在线", f"设备 SN {entity_id}")
        return event_id

    def _resolve_offline_for_roam(self, mac, now):
        rows = self.db.execute(
            "SELECT id,start_ts FROM offline_events WHERE entity_type='client' AND entity_id=? AND status='open'",
            (mac,),
        ).fetchall()
        for row in rows:
            if now < row["start_ts"]:
                continue
            if now - row["start_ts"] <= 60:
                self.db.execute(
                    "UPDATE offline_events SET end_ts=?,status='excluded',excluded=1 WHERE id=?",
                    (now, row["id"]),
                )
            else:
                # 长时间离线后接入不同 AP 是恢复，不应抹掉已经发生的异常。
                self.db.execute(
                    "UPDATE offline_events SET end_ts=?,status='recovered' WHERE id=?",
                    (now, row["id"]),
                )

    def _record_roam(self, now, mac, client, from_ap, to_ap, rssi, duration, source):
        if not from_ap or not to_ap or from_ap == to_ap or to_ap == self.ZERO_MAC:
            return
        self._resolve_offline_for_roam(mac, now)
        existing = self.db.execute(
            """SELECT id,ts,source FROM roam_events
               WHERE mac=? AND from_ap=? AND to_ap=? AND ts BETWEEN ?-60 AND ?+60
               ORDER BY abs(ts-?) LIMIT 1""",
            (mac, from_ap, to_ap, now, now, now),
        ).fetchone()
        # 只合并不同数据来源对同一次漫游的重复观察；同源的不同时间记录仍是独立事件。
        if existing and (existing["source"] != source or existing["source"] == "syslog+live"):
            if source == "syslog" and existing["source"] == "live":
                self.db.execute(
                    "UPDATE roam_events SET source='syslog+live',trigger_rssi=? WHERE id=?",
                    (rssi, existing["id"]),
                )
            return
        self.db.execute(
            """INSERT OR IGNORE INTO roam_events(ts,mac,client,from_ap,to_ap,trigger_rssi,duration_s,source)
               VALUES(?,?,?,?,?,?,?,?)""",
            (now, mac, client, from_ap, to_ap, rssi, duration, source),
        )

    def _attach_reonline(self, sn, ts, text):
        row = self.db.execute(
            """SELECT id FROM offline_events
               WHERE entity_type='ap' AND entity_id=? AND excluded=0 AND start_ts<=?
               ORDER BY start_ts DESC LIMIT 1""",
            (sn, ts),
        ).fetchone()
        if row:
            self._add_evidence(row["id"], ts, "syslog", "设备重新上线", f"设备 SN {sn}", text)

    def observe(self, users, aps, names=None, now=None, source="live"):
        """记录一次完整快照；调用失败时不应传入不完整快照。"""
        now = float(now if now is not None else time.time())
        names = {norm_mac(key): value for key, value in (names or {}).items() if norm_mac(key)}
        current = {}
        for user in users:
            mac = norm_mac(user.get("mac"))
            if mac and user.get("connectType") == "wireless":
                current[mac] = user
        previous = {row["mac"]: row for row in self.db.execute("SELECT * FROM client_state")}
        existing_names = {row["mac"]: row["name"] for row in self.db.execute("SELECT mac,name FROM client_names")}
        changed_names = []
        for mac, raw_name in names.items():
            name = clean(raw_name)
            if name and name.lower() != mac and existing_names.get(mac) != name:
                changed_names.append((mac, name))

        with self.db:
            self.db.executemany(
                """INSERT INTO client_names(mac,name) VALUES(?,?)
                   ON CONFLICT(mac) DO UPDATE SET name=excluded.name""",
                changed_names,
            )
            for mac, user in current.items():
                ap = clean(user.get("deviceAliasName")) or clean(user.get("sn")) or "未知 AP"
                client = names.get(mac) or clean(user.get("hostName")) or mac
                rssi = number(user.get("rssi"))
                old = previous.get(mac)
                if old:
                    old_ap = old["ap"]
                    if old_ap and old_ap != ap:
                        gap = max(0.0, now - old["last_seen"])
                        duration = gap if gap <= 60 else None
                        self._record_roam(now, mac, client, old_ap, ap, old["last_rssi"], duration, source)
                    elif old["offline_id"]:
                        self.db.execute(
                            "UPDATE offline_events SET end_ts=?,status='recovered' WHERE id=?",
                            (now, old["offline_id"]),
                        )
                self.db.execute(
                    """INSERT INTO client_state(mac,client,ap,last_seen,last_rssi,missing_since,offline_id)
                       VALUES(?,?,?,?,?,NULL,NULL)
                       ON CONFLICT(mac) DO UPDATE SET client=excluded.client,ap=excluded.ap,
                       last_seen=excluded.last_seen,last_rssi=excluded.last_rssi,
                       missing_since=NULL,offline_id=NULL""",
                    (mac, client, ap, now, rssi),
                )

            for mac, old in previous.items():
                if mac in current or old["offline_id"] or not old["ap"]:
                    continue
                missing_since = old["missing_since"] or now
                # 从最后在线时间计算两次采样宽限，第二次缺失即可确认事件。
                if now - old["last_seen"] < 6:
                    self.db.execute("UPDATE client_state SET missing_since=? WHERE mac=?", (missing_since, mac))
                    continue
                offline_id = self._open_offline(
                    missing_since, "client", mac, old["client"], old["ap"], old["last_rssi"], source
                )
                self.db.execute(
                    "UPDATE client_state SET missing_since=?,offline_id=? WHERE mac=?",
                    (missing_since, offline_id, mac),
                )

            current_aps = {
                clean(ap.get("serialNumber")): ap for ap in aps
                if clean(ap.get("serialNumber")) and clean(ap.get("band"))
            }
            previous_aps = {row["sn"]: row for row in self.db.execute("SELECT * FROM ap_state")}
            for sn in set(current_aps) | set(previous_aps):
                ap = current_aps.get(sn)
                old = previous_aps.get(sn)
                name = clean((ap or {}).get("hostName")) or (old and old["name"]) or sn
                online = bool(ap) and str(ap.get("status")).upper() == "ON" and bool(clean(ap.get("band")))
                if online:
                    if old and old["offline_id"]:
                        self.db.execute(
                            "UPDATE offline_events SET end_ts=?,status='recovered' WHERE id=?",
                            (now, old["offline_id"]),
                        )
                        row = self.db.execute(
                            "SELECT ts,text FROM syslog_events WHERE sn=? AND tag='DEVICE_REONLINE' AND ts<=? ORDER BY ts DESC LIMIT 1",
                            (sn, now),
                        ).fetchone()
                        if row:
                            self._add_evidence(old["offline_id"], row["ts"], "syslog", "设备重新上线", f"设备 SN {sn}", row["text"])
                    self.db.execute(
                        """INSERT INTO ap_state(sn,name,last_seen,offline_id) VALUES(?,?,?,NULL)
                           ON CONFLICT(sn) DO UPDATE SET name=excluded.name,
                           last_seen=excluded.last_seen,offline_id=NULL""",
                        (sn, name, now),
                    )
                else:
                    offline_id = old["offline_id"] if old else None
                    if not offline_id:
                        offline_id = self._open_offline(now, "ap", sn, name, name, None, source)
                    self.db.execute(
                        """INSERT INTO ap_state(sn,name,last_seen,offline_id) VALUES(?,?,?,?)
                           ON CONFLICT(sn) DO UPDATE SET name=excluded.name,offline_id=excluded.offline_id""",
                        (sn, name, old["last_seen"] if old else now, offline_id),
                    )

    def ingest_syslog(self, logs, names=None, ap_names=None):
        """保存只读系统日志；仅异 AP 记录计漫游，零 AP 记录只作离线证据。"""
        names = {norm_mac(key): value for key, value in (names or {}).items() if norm_mac(key)}
        ap_names = {norm_mac(key): value for key, value in (ap_names or {}).items() if norm_mac(key)}
        since_row = self.db.execute("SELECT value FROM meta WHERE key='events_since'").fetchone()
        since_ts = time.mktime(time.strptime(since_row[0], "%Y-%m-%d")) if since_row else 0
        latest_ts = self.db.execute("SELECT COALESCE(MAX(ts),0) FROM syslog_events").fetchone()[0] or 0
        # 日志接口每轮会返回大量旧记录；保留两分钟重叠，兼容轻微乱序和重复。
        cutoff = latest_ts - 120 if latest_ts else 0
        inserted = 0
        with self.db:
            for raw in logs:
                if not isinstance(raw, (list, tuple)) or len(raw) != 5:
                    continue
                try:
                    ts = float(raw[0])
                except (TypeError, ValueError):
                    continue
                if ts < cutoff:
                    continue
                module, tag, level, text = (clean(raw[1]), clean(raw[2]), clean(raw[3]), clean(raw[4]))
                signature = hashlib.sha256("\0".join((str(ts), module, tag, level, text)).encode()).hexdigest()
                match = self.ROAM_RE.fullmatch(text) if tag == "STA_ROAM" else None
                reonline = self.REONLINE_RE.search(text) if tag == "DEVICE_REONLINE" else None
                mac = norm_mac(match.group("sta")) if match else ""
                from_mac = norm_mac(match.group("out")) if match else ""
                to_mac = norm_mac(match.group("in")) if match else ""
                out_rssi = number(match.group("out_rssi")) if match else None
                in_rssi = number(match.group("in_rssi")) if match else None
                sn = reonline.group(1) if reonline else ""
                cursor = self.db.execute(
                    """INSERT OR IGNORE INTO syslog_events
                       (signature,ts,mac,from_ap,to_ap,out_rssi,in_rssi,sn,module,tag,level,text)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (signature, ts, mac, from_mac, to_mac, out_rssi, in_rssi, sn, module, tag, level, text),
                )
                if not cursor.rowcount:
                    continue
                inserted += 1
                if reonline:
                    self._attach_reonline(sn, ts, text)
                if not match or ts < since_ts:
                    continue
                if to_mac == self.ZERO_MAC:
                    event = self.db.execute(
                        """SELECT id FROM offline_events
                           WHERE entity_type='client' AND entity_id=? AND excluded=0
                           AND start_ts BETWEEN ?-60 AND ?+60
                           ORDER BY abs(start_ts-?) LIMIT 1""",
                        (mac, ts, ts, ts),
                    ).fetchone()
                    if event:
                        self._attach_zero_log(event["id"], {
                            "ts": ts, "from_ap": from_mac, "out_rssi": out_rssi, "text": text,
                        })
                elif from_mac != to_mac:
                    self._record_roam(
                        ts, mac, names.get(mac) or mac,
                        ap_names.get(from_mac) or from_mac,
                        ap_names.get(to_mac) or to_mac,
                        out_rssi, None, "syslog",
                    )
        return inserted

    def finish_history_import(self):
        """历史文件结束后清空状态，防止与当前实时快照拼接出跨小时假事件。"""
        with self.db:
            self.db.execute("UPDATE offline_events SET status='history_end' WHERE status='open' AND source='history'")
            self.db.execute("DELETE FROM client_state")
            self.db.execute("DELETE FROM ap_state")

    def close(self):
        self.db.close()
