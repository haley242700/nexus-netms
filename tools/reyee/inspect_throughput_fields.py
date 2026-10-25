"""只读检查 AP、网关和终端流量字段，不输出认证信息。"""
import json
from tools.common import apply_env, artifact_path
from ap_lookup import ReyeeClient

apply_env("login.env")

client = ReyeeClient()
client._ensure_session()
aps = client._cmd("ap_list").get("list") or []
body = {
    "method": "devSta.get",
    "params": {"module": "user_list", "data": {"devType": "all", "dataType": "timely"}},
}
response = client._sess.post(
    f"{client.eg_url}/cgi-bin/luci/api/cmd?auth={client._sid}",
    json=body, verify=False, timeout=client.timeout,
    headers={"Referer": f"{client.eg_url}/cgi-bin/luci/", "Origin": client.eg_url},
)
result = response.json()
if result.get("code") != 0:
    raise RuntimeError(f"user_list 查询失败：code={result.get('code')}")
users = (result.get("data") or {}).get("list") or []
with artifact_path("diagnostics", "reyee-throughput-fields.json").open("w", encoding="utf-8") as f:
    json.dump({"ap_list": aps, "user_list": users}, f, ensure_ascii=False, indent=2)

print("=== AP / 网关字段 ===")
for row in aps:
    print(json.dumps(row, ensure_ascii=False))
print("=== 无线终端实时流量示例 ===")
for row in users:
    if row.get("connectType") == "wireless":
        print(json.dumps({k: row.get(k) for k in (
            "mac", "hostName", "deviceAliasName", "rxrate", "up", "down", "flowUp", "flowDown"
        )}, ensure_ascii=False))
