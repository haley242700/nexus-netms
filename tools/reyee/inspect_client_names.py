"""只读检查睿易终端名称字段，不打印登录凭据或认证值。"""
import json

from tools.common import apply_env, artifact_path
from ap_lookup import ReyeeClient

apply_env("login.env")

client = ReyeeClient()
rows = client._cmd("sta_list").get("list") or []
with artifact_path("diagnostics", "reyee-sta-current.json").open("w", encoding="utf-8") as f:
    json.dump(rows, f, ensure_ascii=False, indent=2)

keys = sorted({key for row in rows for key in row})
print("终端数：", len(rows))
print("全部字段：", ", ".join(keys))
interesting = [key for key in keys if any(word in key.lower() for word in ("name", "alias", "remark", "nick", "note", "mac", "ip"))]
for index, row in enumerate(rows, 1):
    print(f"--- {index:02d} ---")
    print(json.dumps({key: row.get(key) for key in interesting}, ensure_ascii=False))
