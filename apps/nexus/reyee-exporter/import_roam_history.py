"""把今天已有的 roam_log.jsonl 快照导入 NEXUS 事件库，只执行一次。"""
import argparse
import json
import os
from datetime import datetime

from event_store import EventStore, clean


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("logfile")
    parser.add_argument("--since", default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()
    store = EventStore()
    if store.db.execute("SELECT value FROM meta WHERE key='history_import_completed'").fetchone():
        print("历史日志已导入，跳过。")
        return
    start = datetime.strptime(args.since, "%Y-%m-%d").timestamp()
    batches = {}
    with open(args.logfile, encoding="utf-8") as handle:
        for line in handle:
            try:
                row = json.loads(line)
                stamp = datetime.strptime(row["ts"], "%Y-%m-%dT%H:%M:%S").timestamp()
            except (ValueError, KeyError, TypeError):
                continue
            if stamp >= start:
                batches.setdefault(stamp, []).append(row)
    for stamp in sorted(batches):
        users = []
        names = {}
        for row in batches[stamp]:
            users.append({
                "mac": row.get("mac"), "connectType": "wireless",
                "deviceAliasName": row.get("apName"), "sn": row.get("apSn"),
                "hostName": row.get("host"), "rssi": row.get("rssi"),
            })
            mac = clean(row.get("mac")).lower()
            if clean(row.get("host")):
                names[mac] = clean(row.get("host"))
        store.observe(users, [], names, now=stamp, source="history")
    store.finish_history_import()
    with store.db:
        store.db.execute(
            "INSERT OR REPLACE INTO meta(key,value) VALUES('history_import_completed',?)",
            (datetime.now().isoformat(timespec="seconds"),),
        )
    roam = store.db.execute("SELECT COUNT(*) FROM roam_events WHERE source='history'").fetchone()[0]
    offline = store.db.execute("SELECT COUNT(*) FROM offline_events WHERE source='history' AND excluded=0").fetchone()[0]
    print(f"导入完成：{len(batches)} 个快照，{roam} 次漫游，{offline} 次非漫游离线。")
    store.close()


if __name__ == "__main__":
    main()
