"""仅分析已保存的系统日志，不访问网络或修改设备。"""
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

def show(row):
    return {
        "time": datetime.fromtimestamp(row["ts"]).isoformat(timespec="seconds"),
        "module": row["module"], "tag": row["tag"], "level": row["level"], "text": row["text"],
    }

print("=== 非 STA_ROAM、非 WEB 日志 ===")
other = [row for row in rows if row["tag"] != "STA_ROAM" and row["module"] != "WEB"]
print("条数", len(other))
for row in sorted(other, key=lambda item: item["ts"]):
    print(json.dumps(show(row), ensure_ascii=False))

pattern = re.compile(
    r"STA:\((?P<sta>[0-9A-F:]{17})\) roam from OUT_AP \((?P<out>[0-9A-F:]{17})\) "
    r"rssi (?P<out_rssi>-?\d+) to IN_AP\((?P<in>[0-9A-F:]{17})\) rssi (?P<in_rssi>-?\d+)",
    re.I,
)
roams = [row for row in rows if row["tag"] == "STA_ROAM"]
parsed = []
unparsed = []
for row in roams:
    match = pattern.fullmatch(row["text"])
    (parsed if match else unparsed).append((row, match))
zero = [(row, match) for row, match in parsed if match.group("in") == "00:00:00:00:00:00"]
same = [(row, match) for row, match in parsed if match.group("in") == match.group("out")]
different = [(row, match) for row, match in parsed if match.group("in") not in {"00:00:00:00:00:00", match.group("out")}]
print("\n=== STA_ROAM 结构统计 ===")
print(json.dumps({"total": len(roams), "parsed": len(parsed), "unparsed": len(unparsed), "zero_in_ap": len(zero), "same_ap": len(same), "different_ap": len(different)}, ensure_ascii=False))
print("零 AP 的终端数", len({match.group("sta") for _, match in zero}))
print("零 AP 的离开 AP 数", len({match.group("out") for _, match in zero}))
print("零 AP 接入 RSSI", Counter(match.group("in_rssi") for _, match in zero))
print("离开 RSSI 分布（前 15）", Counter(match.group("out_rssi") for _, match in parsed).most_common(15))
print("接入 RSSI 分布（前 15）", Counter(match.group("in_rssi") for _, match in parsed).most_common(15))
for title, group in [("未解析样本", unparsed[:10]), ("零 AP 样本", zero[-15:])]:
    print("\n===", title, "===")
    for row, _ in group:
        print(json.dumps(show(row), ensure_ascii=False))
