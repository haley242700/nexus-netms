# 本地验证漫游日志功能：临时端口 18099、10 秒轮询，日志写入 artifacts。
import os, subprocess, sys, time, urllib.request, json, signal
from tools.common import SPEEDTEST_AP_DIR, artifact_path, load_env

env = dict(os.environ)
env.update(load_env("login.env"))
env["AP_SERVER_PORT"] = "18099"
env["ROAM_POLL_INTERVAL"] = "10"
env["ROAM_LOG_DIR"] = str(artifact_path("logs", "roam_logs_test"))
env["EG_TIMEOUT"] = "8"

log_path = os.path.join(env["ROAM_LOG_DIR"], "roam_log.jsonl")
if os.path.exists(log_path):
    os.remove(log_path)

proc = subprocess.Popen(
    [sys.executable, "server.py"],
    cwd=SPEEDTEST_AP_DIR, env=env,
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
)

try:
    # 等服务就绪
    ready = False
    for _ in range(20):
        try:
            urllib.request.urlopen("http://127.0.0.1:18099/api/ap-info?ip=127.0.0.1", timeout=2)
            ready = True
            break
        except Exception:
            time.sleep(1)
    print("服务就绪:", ready)

    # 等至少 2 轮轮询（10s 间隔 + 余量）
    time.sleep(33)

    lines = []
    if os.path.exists(log_path):
        with open(log_path, encoding="utf-8") as f:
            lines = [l for l in f if l.strip()]
    print("日志行数:", len(lines))
    if lines:
        rec = json.loads(lines[0])
        print("首条字段:", sorted(rec.keys()))
        print("首条样例(隐藏IP):", {k: ("***" if k == "ip" else v) for k, v in rec.items()})

    try:
        with urllib.request.urlopen("http://127.0.0.1:18099/api/roam-log?limit=3", timeout=5) as r:
            body = r.read().decode()
        d = json.loads(body)
        print("/api/roam-log 返回键:", sorted(d.keys()) if isinstance(d, dict) else type(d).__name__)
        sample = (d.get("records") or d.get("list") or [])[:1] if isinstance(d, dict) else []
        if sample:
            print("接口样例字段:", sorted(sample[0].keys()))
    except Exception as e:
        print("/api/roam-log 请求失败:", e)

    print("结果:", "PASS" if len(lines) >= 2 else "FAIL(日志不足)")
finally:
    proc.send_signal(signal.SIGTERM)
    try:
        out, _ = proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _ = proc.communicate()
    print("--- server 输出(尾部) ---")
    print("\n".join(out.splitlines()[-8:]))
