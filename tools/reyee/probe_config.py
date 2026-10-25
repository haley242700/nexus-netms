"""只读探测 devConfig/acConfig 方法族。绝不修改配置。"""
import json
from tools.common import apply_env
from ap_lookup import ReyeeClient

apply_env("login.env")

TARGET_SN = "G1UK5ZK04793A"

c = ReyeeClient()
c._ensure_session()

QUERIES = [
    ("devConfig.get", {"module": "radio"}),
    ("devConfig.get", {"module": "wireless"}),
    ("devConfig.get", {"module": "wifi"}),
    ("acConfig.get", {"module": "kvNavAc"}),
    ("acConfig.get", {"module": "radioLb"}),
]

for method, params in QUERIES:
    try:
        body = {"method": method, "params": params}
        resp = c._sess.post(
            f"{c.eg_url}/cgi-bin/luci/api/cmd?auth={c._sid}",
            json=body, verify=False, timeout=c.timeout,
            headers={"Referer": f"{c.eg_url}/cgi-bin/luci/", "Origin": c.eg_url},
        )
        result = resp.json()
        s = json.dumps(result, ensure_ascii=False)
        print(f"\n=== {method} {params['module']} len={len(s)} code={result.get('code')} ===")
        i = s.find(TARGET_SN)
        if i >= 0:
            print(f"--- 含 {TARGET_SN} 的片段 ---")
            print(s[max(0, i - 500):i + 1500])
        else:
            print(s[:350])
            print(f"(未找到 {TARGET_SN})")
    except Exception as e:
        print(f"\n=== {method} {params['module']} ERR {repr(e)[:150]} ===")
