"""下载后台前端 JS 并提取 API 调用线索。"""
import re
import sys
from pathlib import Path

from tools.common import artifact_path, load_env
from reyee_session import login

OUT = artifact_path("research", "recon")
OUT.mkdir(exist_ok=True)

sess = login(load_env("login.env"))
eg_url = sess._eg_url  # type: ignore[attr-defined]

FILES = [
    "/luci-static/web/static/js/app54169bd7c8c547dd33f7.js",
    "/luci-static/web/static/js/vendor0ff3f747407c74df245d.js",
]

for path in FILES:
    resp = sess.get(f"{eg_url}{path}", verify=False, timeout=15)
    name = Path(path).name
    (OUT / name).write_text(resp.text, encoding="utf-8")
    print(name, resp.status_code, len(resp.text))

# 提取 api 路径和 method 名
for f in OUT.glob("*.js"):
    text = f.read_text(encoding="utf-8", errors="ignore")
    apis = sorted(set(re.findall(r'/cgi-bin/luci/api/[\w/.-]+', text)))
    methods = sorted(set(re.findall(r'method["\']?\s*[:=]\s*["\']([\w.-]+)["\']', text)))
    print(f"\n=== {f.name} ===")
    print("API paths:")
    for a in apis:
        print("  ", a)
    print("methods:", methods[:80])
