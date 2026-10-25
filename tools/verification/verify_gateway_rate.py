"""只读用 WAN 累计计数器校验 flow_status 实时速率单位。"""
import time
from tools.common import apply_env
from ap_lookup import ReyeeClient

apply_env("login.env")
client = ReyeeClient()
client._ensure_session()


def sample():
    response = client._sess.post(
        f"{client.eg_url}/cgi-bin/luci/api/cmd?auth={client._sid}",
        json={"method": "devSta.get", "params": {"module": "flow_status"}},
        verify=False, timeout=client.timeout,
        headers={"Referer": f"{client.eg_url}/cgi-bin/luci/", "Origin": client.eg_url},
    )
    result = response.json()
    rows = (result.get("data") or {}).get("data") or []
    return time.monotonic(), next(row for row in rows if int(row.get("lpid", 0)) == 10)


t0, a = sample()
time.sleep(6)
t1, b = sample()
elapsed = t1 - t0
for direction in ("input", "output"):
    delta_bytes = float(b[direction + "_total"]) - float(a[direction + "_total"])
    calculated_bps = delta_bytes / elapsed
    reported_bps = float(b[direction + "_rate"]) * 1024
    print(f"{direction}: 总计数器换算={calculated_bps:.0f} B/s，接口速率换算={reported_bps:.0f} B/s")
