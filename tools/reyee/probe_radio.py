"""只读探测：AP 射频/邻居/漫游相关模块。绝不修改任何配置。"""
import json
from tools.common import apply_env
from ap_lookup import ReyeeClient

apply_env("login.env")

TARGET_SN = "G1UK5ZK04793A"  # 负一卧室AP EAP162

c = ReyeeClient()
c._ensure_session()

MODULES = ["radioInfo", "radio", "neighbor", "roam", "kvNavAc", "wifiAcdev",
           "ineffective_ssid", "radio_channel", "country_channel"]

for mod in MODULES:
    try:
        d = c._cmd(mod)
        s = json.dumps(d, ensure_ascii=False)
        print(f"\n=== module {mod} len={len(s)} ===")
        print(s[:300])
        i = s.find(TARGET_SN)
        if i >= 0:
            print(f"--- 含 {TARGET_SN} 的片段 ---")
            print(s[max(0, i - 400):i + 1200])
        else:
            print(f"(未找到 {TARGET_SN})")
    except Exception as e:
        print(f"\n=== module {mod} ERR {repr(e)[:150]} ===")
