"""只读检查睿易终端备注，并按 MAC 与当前在线终端对应。"""
import json
import re

from tools.common import apply_env, artifact_path
from ap_lookup import ReyeeClient, _clean


def normalize_mac(value):
    compact = re.sub(r"[^0-9A-Fa-f]", "", _clean(value)).lower()
    return ":".join(compact[i:i + 2] for i in range(0, 12, 2)) if len(compact) == 12 else ""


apply_env("login.env")

client = ReyeeClient()
client._ensure_session()


def readonly_cmd(method, module, data=None):
    params = {"module": module}
    if data is not None:
        params["data"] = data
    response = client._sess.post(
        f"{client.eg_url}/cgi-bin/luci/api/cmd?auth={client._sid}",
        json={"method": method, "params": params},
        verify=False,
        timeout=client.timeout,
        headers={"Referer": f"{client.eg_url}/cgi-bin/luci/", "Origin": client.eg_url},
    )
    result = response.json()
    if result.get("code") != 0:
        raise RuntimeError(f"只读接口 {method}/{module} 返回异常，code={result.get('code')}")
    return result.get("data") or {}


remark_data = readonly_cmd("devConfig.get", "devRemark")
user_data = readonly_cmd(
    "devSta.get", "user_list", {"devType": "all", "dataType": "timely"}
)
sta = client._cmd("sta_list").get("list") or []
remarks = remark_data.get("list") or []
users = user_data.get("list") or []
remark_map = {
    normalize_mac(row.get("mac")): _clean(row.get("name"))
    for row in remarks
    if normalize_mac(row.get("mac")) and _clean(row.get("name"))
}
user_map = {
    normalize_mac(row.get("mac")): _clean(row.get("name"))
    for row in users
    if normalize_mac(row.get("mac")) and _clean(row.get("name"))
}

report = {
    "remark_count": len(remarks),
    "user_list_count": len(users),
    "online_count": len(sta),
    "devices": [],
}
for row in sta:
    mac = normalize_mac(row.get("mac"))
    report["devices"].append({
        "mac": mac,
        "ip": _clean(row.get("userIp")),
        "original_host": _clean(row.get("hostName")),
        "remark_name": remark_map.get(mac, ""),
        "user_list_name": user_map.get(mac, ""),
        "ap": _clean(row.get("deviceAliasName")) or _clean(row.get("sn")),
        "rssi": _clean(row.get("rssi")),
    })

with artifact_path("diagnostics", "reyee-name-matches.json").open("w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print(f"备注 {len(remarks)} 条；user_list {len(users)} 条；当前在线终端 {len(sta)} 台")
for index, row in enumerate(report["devices"], 1):
    print(
        f"{index:02d}. {row['mac']} | 备注={row['remark_name'] or '无'} "
        f"| user_list={row['user_list_name'] or '无'} | 原名={row['original_host'] or '空'} "
        f"| AP={row['ap']} | IP={row['ip']}"
    )
