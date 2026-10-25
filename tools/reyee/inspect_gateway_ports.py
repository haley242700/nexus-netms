"""只读确认网关 WAN 与物理流量端口映射，敏感配置不输出。"""
import json
from tools.common import apply_env, artifact_path
from ap_lookup import ReyeeClient

apply_env("login.env")

client = ReyeeClient()
client._ensure_session()


def get(method, module):
    response = client._sess.post(
        f"{client.eg_url}/cgi-bin/luci/api/cmd?auth={client._sid}",
        json={"method": method, "params": {"module": module}},
        verify=False, timeout=client.timeout,
        headers={"Referer": f"{client.eg_url}/cgi-bin/luci/", "Origin": client.eg_url},
    )
    result = response.json()
    return result.get("data") if result.get("code") == 0 else {"error_code": result.get("code")}


def redact(value):
    if isinstance(value, dict):
        return {
            k: ("***" if any(word in k.lower() for word in ("pass", "pwd", "secret", "user")) else redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


results = {
    "port_status": get("devSta.get", "port_status"),
    "port_base": get("devSta.get", "port_base"),
    "networkConnect": get("devSta.get", "networkConnect"),
    "network": get("devConfig.get", "network"),
}
results = redact(results)
with artifact_path("diagnostics", "reyee-gateway-ports.json").open("w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(json.dumps(results, ensure_ascii=False, indent=2))
