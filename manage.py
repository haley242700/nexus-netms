"""nexus-netms 统一入口：目录可视化、离线测试、部署打包和只读生产验证。"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
TEST_HISTORY = ROOT / "artifacts" / "test-metrics.jsonl"
PYTHON_TESTS = [
    "tests/test_event_store_v1.py",
    "tests/test_dashboard_events_api.py",
    "tests/test_event_migration.py",
    "tests/test_speedtest_analysis.py",
    "tests/test_speedtest_integration.py",
    "tests/nexus_scale_test.py",
]
JS_TESTS = [
    "tests/test_dashboard_pagination.js",
    "tests/test_dashboard_throughput.js",
    "tests/test_speedtest_page.js",
]
JS_SOURCES = [
    "apps/nexus/network-dashboard/app.js",
    "apps/nexus/network-dashboard/events.js",
    "apps/nexus/network-dashboard/speedtest-app.js",
    "apps/nexus/network-dashboard/navigation.js",
    "apps/nexus/network-dashboard/flow-field.js",
]
VERIFY_SCRIPTS = [
    "tools/verification/nexus_health_check.py",
    "tools/verification/verify_nexus_totals.py",
    "tools/verification/nexus_performance_check.py",
]
IGNORE_DIRS = {".git", ".venv", "__pycache__", "artifacts", "dist", ".pytest_cache"}
FORBIDDEN_PACKAGE_NAMES = {".env", "login.env", "nas.env", "cloud.env", "htpasswd"}


def environment():
    env = os.environ.copy()
    paths = [str(ROOT), str(ROOT / "apps" / "speedtest-ap"), str(ROOT / "apps" / "nexus" / "network-dashboard")]
    if env.get("PYTHONPATH"):
        paths.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(paths)
    return env


def run(command):
    print("+", " ".join(str(part) for part in command), flush=True)
    subprocess.run([str(part) for part in command], cwd=ROOT, env=environment(), check=True)


def execute_timed(label, command):
    """独立子进程执行并采集输出，避免并行日志交错。"""
    started = time.perf_counter()
    result = subprocess.run(
        [str(part) for part in command], cwd=ROOT, env=environment(),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )
    return {
        "label": label,
        "command": [str(part) for part in command],
        "seconds": round(time.perf_counter() - started, 3),
        "returncode": result.returncode,
        "output": result.stdout,
    }


def emit_result(result):
    print(f"\n+ {' '.join(result['command'])}")
    if result["output"].strip():
        print(result["output"].rstrip())
    state = "PASS" if result["returncode"] == 0 else "FAIL"
    print(f"[{state}] {result['label']}: {result['seconds']:.3f}s", flush=True)


def recent_test_summary():
    """根据成功记录统计最近五次，不混入失败运行或单项性能指标。"""
    try:
        lines = TEST_HISTORY.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return
    runs = []
    for line in lines:
        try:
            record = json.loads(line)
            if record.get("status") == "passed":
                float(record["total_seconds"])
                runs.append(record)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
    recent = runs[-5:]
    if not recent:
        return
    durations = [record["total_seconds"] for record in recent]
    print(
        f"最近 {len(recent)} 次成功全量测试：平均 {statistics.mean(durations):.3f}s，"
        f"中位数 {statistics.median(durations):.3f}s，范围 {min(durations):.3f}–{max(durations):.3f}s。"
    )
    module_durations = {}
    for record in recent:
        for module in record.get("modules", []):
            module_durations.setdefault(module["label"], []).append(module["seconds"])
    averages = {label: statistics.mean(values) for label, values in module_durations.items()}
    if averages:
        label = max(averages, key=averages.get)
        print(f"最近 {len(recent)} 次平均最慢模块：{label}（{averages[label]:.3f}s）。")


def offline_test(args):
    """编译前置；彼此独立的 Python/Node 测试并行，范围与串行版一致。"""
    started = time.perf_counter()
    results = []
    compile_result = execute_timed(
        "Python 编译检查",
        [sys.executable, "-m", "compileall", "-q", "apps", "tools", "tests", "manage.py"],
    )
    results.append(compile_result)
    if compile_result["returncode"] == 0:
        node = shutil.which("node") or "node"
        tasks = [(f"Python · {script}", [sys.executable, script]) for script in PYTHON_TESTS]
        tasks += [(f"JS 语法 · {Path(script).name}", [node, "--check", script]) for script in JS_SOURCES]
        tasks += [(f"JS · {script}", [node, script]) for script in JS_TESTS]
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            futures = [executor.submit(execute_timed, label, command) for label, command in tasks]
            results.extend(future.result() for future in futures)
    for result in results:
        emit_result(result)
    passed = all(result["returncode"] == 0 for result in results)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if passed else "failed",
        "total_seconds": round(time.perf_counter() - started, 3),
        "jobs": args.jobs,
        "modules": [{key: value for key, value in result.items() if key != "output"} for result in results],
    }
    TEST_HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with TEST_HISTORY.open("a", encoding="utf-8") as history:
        history.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"\n本次全量测试总耗时：{record['total_seconds']:.3f}s（并行度 {args.jobs}）。")
    slowest = max(results, key=lambda result: result["seconds"])
    print(f"本次最慢模块：{slowest['label']}（{slowest['seconds']:.3f}s）。")
    recent_test_summary()
    if not passed:
        raise RuntimeError("全量测试存在失败模块，详情见上方输出")
    module_count = 1 + len(PYTHON_TESTS) + len(JS_SOURCES) + len(JS_TESTS)
    print(f"离线全量测试通过：{module_count} 个模块全部执行，未连接 NAS、睿易后台或生产看板。")
    print(f"计时历史：{TEST_HISTORY}")


def production_verify(_args):
    for script in VERIFY_SCRIPTS:
        run([sys.executable, script])


def package_ignore(_directory, names):
    ignored = set()
    for name in names:
        if name in IGNORE_DIRS or name in {"events", "logs"} or name in FORBIDDEN_PACKAGE_NAMES:
            ignored.add(name)
        elif name.endswith((".pyc", ".db", ".db-wal", ".db-shm")):
            ignored.add(name)
    return ignored


def make_package(target):
    source = ROOT / "apps" / target
    destination = DIST / target
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination, ignore=package_ignore)
    if target == "nexus":
        runtime = destination / "runtime"
        runtime.mkdir(exist_ok=True)
        for filename in ("ap_lookup.py", "reyee_session.py", "test.py"):
            shutil.copy2(ROOT / "apps" / "speedtest-ap" / filename, runtime / filename)
    files = [path for path in destination.rglob("*") if path.is_file()]
    forbidden = [
        path for path in files
        if path.name in FORBIDDEN_PACKAGE_NAMES or path.suffix in {".pkl", ".b64"}
    ]
    if forbidden:
        raise RuntimeError(f"部署包包含受保护文件：{forbidden}")
    print(f"{target}: {len(files)} 个文件 -> {destination}")
    print("部署包不包含密钥、会话、数据库、日志或缓存。")


def package(args):
    targets = ("speedtest-ap", "nexus") if args.target == "all" else (args.target,)
    DIST.mkdir(exist_ok=True)
    for target in targets:
        make_package(target)


def show_tree(args):
    def walk(directory, prefix="", depth=0):
        entries = sorted(
            (path for path in directory.iterdir() if path.name not in IGNORE_DIRS),
            key=lambda path: (not path.is_dir(), path.name.lower()),
        )
        for index, path in enumerate(entries):
            last = index == len(entries) - 1
            connector = "└── " if last else "├── "
            if path.is_dir():
                print(prefix + connector + path.name + "/")
                if depth + 1 < args.depth and path.name != "secrets":
                    walk(path, prefix + ("    " if last else "│   "), depth + 1)
            else:
                print(prefix + connector + path.name)

    print("SpeedTest/")
    for name in ("artifacts/", "dist/"):
        if (ROOT / name).exists():
            print(f"├── {name}  # 本地产物，不上传 Git")
    walk(ROOT, depth=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("tree", help="显示项目结构").set_defaults(func=show_tree)
    test_parser = subparsers.add_parser("test", help="运行完全离线的全量测试并记录分模块耗时")
    test_parser.add_argument("--jobs", type=int, choices=range(1, 9), default=min(4, os.cpu_count() or 1), metavar="1-8", help="独立测试并行度，默认最多 4")
    test_parser.set_defaults(func=offline_test)
    subparsers.add_parser("verify", help="运行生产只读验证（需要内网）").set_defaults(func=production_verify)
    package_parser = subparsers.add_parser("package", help="生成可重复上传的干净部署包")
    package_parser.add_argument("target", choices=("speedtest-ap", "nexus", "all"), nargs="?", default="all")
    package_parser.set_defaults(func=package)
    tree_parser = subparsers.choices["tree"]
    tree_parser.add_argument("--depth", type=int, default=3)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
