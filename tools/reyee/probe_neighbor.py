import json
from tools.common import apply_env
from ap_lookup import ReyeeClient

apply_env("login.env")

c = ReyeeClient()
c._ensure_session()
for mod in ["neighbor", "radio_channel"]:
    try:
        d = c._cmd(mod)
        s = json.dumps(d, ensure_ascii=False)
        print(f"=== {mod} len={len(s)} ===")
        print(s[:400])
        for kw in ["G1UK5ZK04793A", "58:B4:BB", "58b4.bb68"]:
            i = s.find(kw)
            if i >= 0:
                print(f"--- 含 {kw} 的条目 ---")
                print(s[max(0, i - 300):i + 900])
                print()
    except Exception as e:
        print(mod, "ERR", repr(e)[:150])
