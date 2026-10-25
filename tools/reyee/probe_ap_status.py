import json
from tools.common import apply_env
from ap_lookup import ReyeeClient

apply_env("login.env")

c = ReyeeClient()
c._ensure_session()
for mod in ["ap", "ap_list", "ap_list_lite"]:
    try:
        d = c._cmd(mod)
        s = json.dumps(d, ensure_ascii=False)
        print(f"=== module {mod} len={len(s)} ===")
        for kw in ["G1UK5ZK04793A", "G1V20RU046407"]:
            i = s.find(kw)
            if i >= 0:
                print(f"--- {kw} ---")
                print(s[max(0, i - 100):i + 1800])
            else:
                print(f"--- {kw}: 未出现 ---")
    except Exception as e:
        print(mod, "ERR", repr(e)[:200])
