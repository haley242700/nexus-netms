"""只读探测睿易网关状态接口的流量字段。"""
import json
from tools.common import apply_env, artifact_path
from ap_lookup import ReyeeClient

apply_env("login.env")

client = ReyeeClient()
client._ensure_session()
results = {}
for module in ("intf_status", "waninfo", "lineNpmStat", "flow_status"):
    response = client._sess.post(
        f"{client.eg_url}/cgi-bin/luci/api/cmd?auth={client._sid}",
        json={"method": "devSta.get", "params": {"module": module}},
        verify=False, timeout=client.timeout,
        headers={"Referer": f"{client.eg_url}/cgi-bin/luci/", "Origin": client.eg_url},
    )
    result = response.json()
    results[module] = result.get("data") if result.get("code") == 0 else {"error_code": result.get("code")}

with artifact_path("diagnostics", "reyee-gateway-throughput.json").open("w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
for module, data in results.items():
    print(f"=== {module} ===")
    print(json.dumps(data, ensure_ascii=False))
