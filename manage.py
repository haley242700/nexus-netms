"""nexus-netms 统一入口：目录可视化、离线测试、部署打包和只读生产验证。"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
PYTHON_TESTS = [
    "tests/test_event_store_v1.py",
    "tests/test_dashboard_events_api.py",
    "tests/test_event_migration.py",
    "tests/test_speedtest_integration.py",
    "tests/nexus_scale_test.py",
]
JS_TESTS = [
    "tests/test_dashboard_pagination.js",
    "tests/test_dashboard_throughput.js",
    "tests/test_speedtest_page.js",
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
    paths = [str(ROOT), str(ROOT / "apps" / "speedtest-ap")]
    if env.get("PYTHONPATH"):
        paths.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(paths)
    return env


def run(command):
    print("+", " ".join(str(part) for part in command), flush=True)
    subprocess.run([str(part) for part in command], cwd=ROOT, env=environment(), check=True)


def offline_test(_args):
    run([sys.executable, "-m", "compileall", "-q", "apps", "tools", "tests", "manage.py"])
    for script in PYTHON_TESTS:
        run([sys.executable, script])
    node = shutil.which("node") or "node"
    for script in ("apps/nexus/network-dashboard/app.js", "apps/nexus/network-dashboard/events.js", "apps/nexus/network-dashboard/speedtest-app.js", "apps/nexus/network-dashboard/navigation.js", "apps/nexus/network-dashboard/flow-field.js"):
        run([node, "--check", script])
    for script in JS_TESTS:
        run([node, script])
    print("\n离线全量测试通过：未连接 NAS、睿易后台或生产看板。")


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
    subparsers.add_parser("test", help="运行完全离线的全量测试").set_defaults(func=offline_test)
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
