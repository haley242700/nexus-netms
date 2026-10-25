"""探测 /cmd 接口的只读方法，查找终端-AP 关联数据。"""
import json
import sys

from tools.common import load_env
from reyee_session import api_post, login


def show(label, data, limit=800):
    print(f"\n### {label}")
    print(json.dumps(data, ensure_ascii=False)[:limit])


def main() -> int:
    sess = login(load_env("login.env"))
    base = "/cgi-bin/luci/api/cmd"

    probes = [
        ("devSta.get neighbor", {"method": "devSta.get", "params": {"module": "neighbor"}}),
        ("cmdArr neighbor", {"method": "cmdArr",
                             "params": [{"method": "devSta.get", "params": {"module": "neighbor"}}]}),
        ("cmdArr neighbor+esw", {"method": "cmdArr",
                                 "params": [{"method": "devSta.get", "params": {"module": "neighbor"}},
                                            {"method": "devSta.get", "params": {"module": "esw_neighbor"}}]}),
    ]
    for label, body in probes:
        try:
            resp = api_post(sess, base, body)
            show(f"{label} -> HTTP {resp.status_code}", resp.json() if resp.text.startswith(("{", "[")) else resp.text)
        except Exception as exc:
            print(f"{label} 异常: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
