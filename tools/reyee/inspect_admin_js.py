"""只读下载睿易管理后台前端脚本，用于定位终端自定义名称接口。"""
import hashlib
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

from tools.common import apply_env, artifact_path
from ap_lookup import ReyeeClient

apply_env("login.env")

client = ReyeeClient()
client._ensure_session()
base = f"{client.eg_url}/cgi-bin/luci/"
response = client._sess.get(base, verify=False, timeout=client.timeout)
response.raise_for_status()
out = artifact_path("research", "reyee_admin_js")
out.mkdir(exist_ok=True)
(out / "index.html").write_text(response.text, encoding="utf-8")
sources = re.findall(r"<script[^>]+src=[\"']([^\"']+)", response.text, re.I)
print("脚本数量：", len(sources))
for index, source in enumerate(sources):
    url = urljoin(base, source)
    if urlparse(url).netloc != urlparse(base).netloc:
        continue
    data = client._sess.get(url, verify=False, timeout=client.timeout)
    data.raise_for_status()
    name = Path(urlparse(url).path).name or f"script-{index}.js"
    target = out / f"{index:02d}-{name}"
    target.write_bytes(data.content)
    print(target, len(data.content))
