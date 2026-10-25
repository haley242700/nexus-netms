"""登录后抓取后台首页，找出引用的 JS 文件路径。"""
import re
import sys

from tools.common import load_env
from reyee_session import login

sess = login(load_env("login.env"))
eg_url = sess._eg_url  # type: ignore[attr-defined]
resp = sess.get(f"{eg_url}/cgi-bin/luci/", verify=False, timeout=8)
print("index:", resp.status_code, len(resp.text))
for m in sorted(set(re.findall(r'(?:src|href)="([^"]+\.(?:js|css)[^"]*)"', resp.text))):
    print(m)
