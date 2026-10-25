"""仅分析已下载的睿易前端脚本，提取离线日志相关接口线索。"""
from tools.common import artifact_path

TERMS = (
    "系统日志", "日志", "离线", "上线", "下线", "断开", "漫游",
    "deauth", "disconnect", "offline", "syslog", "logList", "log_list", "reason",
)
chunks = []
for path in artifact_path("research", "reyee_admin_js").glob("*.js"):
    text = path.read_text(encoding="utf-8", errors="ignore")
    for term in TERMS:
        start = 0
        for occurrence in range(1, 21):
            index = text.lower().find(term.lower(), start)
            if index < 0:
                break
            chunks.append(
                f"\n===== {path.name} | {term} #{occurrence} @ {index} =====\n"
                f"{text[max(0, index - 500):index + 1100]}"
            )
            start = index + len(term)
artifact_path("diagnostics", "reyee-offline-js-snippets.txt").write_text("\n".join(chunks), encoding="utf-8")
print(f"提取 {len(chunks)} 个片段")
