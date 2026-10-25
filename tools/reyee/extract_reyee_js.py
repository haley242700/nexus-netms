"""从已下载的压缩前端脚本中提取指定关键词附近片段。"""
from tools.common import artifact_path

path = artifact_path("research", "reyee_admin_js", "05-app54169bd7c8c547dd33f7.js")
text = path.read_text(encoding="utf-8")
terms = ["getRemark", "updateRemark", "delRemark", "reMarkList", "devRemark", "remarkMap", "supRemark"]
chunks = []
for term in terms:
    start = 0
    count = 0
    while True:
        index = text.find(term, start)
        if index < 0:
            break
        count += 1
        chunks.append(f"\n===== {term} #{count} @ {index} =====\n{text[max(0, index-450):index+900]}")
        start = index + len(term)
        if count >= 30:
            chunks.append(f"===== {term} 仅显示前 30 处 =====")
            break
    print(term, count)
artifact_path("diagnostics", "reyee-js-snippets.txt").write_text("\n".join(chunks), encoding="utf-8")
