"""只读验证睿易系统日志接口；不调用任何配置、控制或重启方法。"""
import json

from tools.common import apply_env, artifact_path
from ap_lookup import ReyeeClient

apply_env("login.env")

client = ReyeeClient()
client._ensure_session()
body = {
    "method": "devSta.get",
    "params": {"module": "std_syslog_get", "noParse": True, "data": {"user": "web", "option": "log_detail"}},
}
response = client._sess.post(
    f"{client.eg_url}/cgi-bin/luci/api/cmd?auth={client._sid}",
    json=body,
    verify=False,
    timeout=client.timeout,
    headers={"Referer": f"{client.eg_url}/cgi-bin/luci/", "Origin": client.eg_url},
)
result = response.json()
output = {"http": response.status_code, "code": result.get("code"), "data": result.get("data"), "error": result.get("error")}
artifact_path("diagnostics", "reyee-syslog-probe.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
data = result.get("data") or {}
logs = data.get("log_list") or [] if isinstance(data, dict) else []
print("HTTP", response.status_code, "业务码", result.get("code"), "日志条数", len(logs))
print("返回键", sorted(data.keys()) if isinstance(data, dict) else type(data).__name__)
print("单条字段数", sorted({len(row) for row in logs if isinstance(row, list)}))
