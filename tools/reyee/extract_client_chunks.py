"""提取终端管理懒加载脚本中的名称和接口片段。"""
from tools.common import artifact_path

terms = ["clientName", "noSetName", "confirmDelete", "hostName", "remark", "ntm", "sta_list", "annotation"]
chunks = []
for path in artifact_path("research", "reyee_admin_js").glob("chunk-*.js"):
    text = path.read_text(encoding="utf-8")
    for term in terms:
        start = 0
        for count in range(1, 21):
            index = text.find(term, start)
            if index < 0:
                break
            chunks.append(f"\n===== {path.name} | {term} #{count} @ {index} =====\n{text[max(0,index-600):index+1200]}")
            start = index + len(term)
artifact_path("diagnostics", "reyee-client-chunk-snippets.txt").write_text("\n".join(chunks), encoding="utf-8")
print("snippets:", len(chunks))
