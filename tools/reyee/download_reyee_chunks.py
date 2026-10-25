"""只读下载与终端管理有关的后台懒加载脚本。"""
from tools.common import apply_env, artifact_path
from ap_lookup import ReyeeClient

chunks = {
    "advanced": "da15dba5a941b48c0f8e",
    "network": "ca5dee572fb833a072c0",
    "manage": "6cc4418e78f9bd15cefb",
    "whole": "5937e47d55e7ad960f56",
    "monitor": "390e52ee9013fbc60b39",
}
apply_env("login.env")
client = ReyeeClient()
client._ensure_session()
out = artifact_path("research", "reyee_admin_js")
for name, digest in chunks.items():
    url = f"{client.eg_url}/luci-static/web/static/js/{name}{digest}.js"
    response = client._sess.get(url, verify=False, timeout=client.timeout, headers={"Accept-Encoding": "identity"}, stream=True)
    response.raise_for_status()
    content = response.raw.read(decode_content=False)
    response.close()
    target = out / f"chunk-{name}.js"
    target.write_bytes(content)
    print(target, len(content), content[:20])
