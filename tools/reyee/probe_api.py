"""探测锐捷睿易 luci API 的只读接口（不调用任何 set/update/reboot）。

输出只显示 HTTP 状态码和 JSON 顶层结构，不回显 token/sid/密码。
"""
import json
import sys

from tools.common import load_env
from reyee_session import api_get, api_post, login

CANDIDATE_PATHS = [
    "/cgi-bin/luci/api/overview",
    "/cgi-bin/luci/api/network",
    "/cgi-bin/luci/api/wireless",
    "/cgi-bin/luci/api/common",
    "/cgi-bin/luci/api/monitor",
    "/cgi-bin/luci/api/system",
    "/cgi-bin/luci/api/status",
    "/cgi-bin/luci/api/app",
    "/cgi-bin/luci/api/device",
    "/cgi-bin/luci/api/terminal",
    "/cgi-bin/luci/api/client",
    "/cgi-bin/luci/api/sta",
    "/cgi-bin/luci/api/host",
    "/cgi-bin/luci/api/dpi",
]

PROBE_METHODS = ["get", "getInfo", "getList", "getStatus"]


def summarize(obj, depth=0):
    """只打印结构：dict 显示 key 列表，list 显示长度和首个元素的 key。"""
    if isinstance(obj, dict):
        return {k: summarize(v, depth + 1) if depth < 1 else "..." for k, v in list(obj.items())[:20]}
    if isinstance(obj, list):
        if not obj:
            return "[]"
        return [summarize(obj[0], depth + 1), f"... 共{len(obj)}项"]
    return type(obj).__name__


def main() -> int:
    sess = login(load_env("login.env"))
    print("登录成功")

    for path in CANDIDATE_PATHS:
        try:
            resp = api_get(sess, path)
        except Exception as exc:
            print(f"GET  {path:<40} 异常 {exc}")
            continue
        text = resp.text[:120].replace("\n", " ")
        print(f"GET  {path:<40} -> {resp.status_code}  {text}")
    print()

    for path in CANDIDATE_PATHS:
        for method in PROBE_METHODS:
            try:
                resp = api_post(sess, path, {"method": method, "params": {}})
            except Exception as exc:
                continue
            if resp.status_code != 200:
                continue
            try:
                data = resp.json()
            except ValueError:
                continue
            # 只关心看起来像正常应答的（code==0 且有数据），或结构可读的
            code = data.get("code")
            print(f"POST {path:<36} method={method:<10} code={code} 结构: {json.dumps(summarize(data), ensure_ascii=False)[:300]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
