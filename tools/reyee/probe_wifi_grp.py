"""只读探测 wifi_grp 模块（AP Wi-Fi 实况）。绝不修改配置。"""
import json
from tools.common import apply_env
from ap_lookup import ReyeeClient

apply_env("login.env")

TARGET_SN = "G1UK5ZK04793A"

c = ReyeeClient()
c._ensure_session()

QUERIES = [
    ("wifi_grp", {"obj": "wifi", "fuc": "dev", "uid": []}),
    ("wifi_grp", {"obj": "wifi", "fuc": "cfg", "uid": []}),
    ("wifi_grp", {"obj": "grp", "gid": []}),
]

for mod, data in QUERIES:
    try:
        body = {"method": "devSta.get", "params": {"module": mod, "data": data}}
        resp = c._sess.post(
            f"{c.eg_url}/cgi-bin/luci/api/cmd?auth={c._sid}",
            json=body, verify=False, timeout=c.timeout,
            headers={"Referer": f"{c.eg_url}/cgi-bin/luci/", "Origin": c.eg_url},
        )
        result = resp.json()
        s = json.dumps(result, ensure_ascii=False)
        tag = f"{mod} {data.get('fuc') or data.get('obj')}"
        print(f"\n=== {tag} len={len(s)} code={result.get('code')} ===")
        i = s.find(TARGET_SN)
        if i >= 0:
            print(f"--- 含 {TARGET_SN} 的片段 ---")
            print(s[max(0, i - 600):i + 1600])
        else:
            print(s[:400])
            print(f"(未找到 {TARGET_SN})")
    except Exception as e:
        print(f"\n=== {mod} {data} ERR {repr(e)[:150]} ===")
