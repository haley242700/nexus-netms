"""汇总只读系统日志中的离线相关字段与证据，不访问网络。"""
import json
import re
from collections import Counter
from datetime import datetime
from tools.common import artifact_path

payload = json.loads(artifact_path("diagnostics", "reyee-syslog-probe.json").read_text(encoding="utf-8"))
logs = (payload.get("data") or {}).get("log_list") or []
rows = [
    {"ts": float(row[0]), "module": row[1], "tag": row[2], "level": row[3], "text": row[4]}
    for row in logs if isinstance(row, list) and len(row) == 5
]
print("时间范围", datetime.fromtimestamp(min(r["ts"] for r in rows)), "至", datetime.fromtimestamp(max(r["ts"] for r in rows)))
print("模块", Counter(r["module"] for r in rows).most_common(25))
print("消息标识", Counter(r["tag"] for r in rows).most_common(35))
print("等级", Counter(r["level"] for r in rows))
pattern = re.compile(
    r"deauth|disassoc|reassoc|assoc|station|\bsta\b|wireless|wlan|wifi|"
    r"offline|online|reboot|restart|boot|power|漫游|离线|上线|下线|断开|重启|断电",
    re.I,
)
related = [r for r in rows if pattern.search(f'{r["module"]} {r["tag"]} {r["text"]}')]
print("相关条数", len(related))
for row in related[-100:]:
    stamp = datetime.fromtimestamp(row["ts"]).isoformat(timespec="seconds")
    print(json.dumps({"time": stamp, **row}, ensure_ascii=False))
