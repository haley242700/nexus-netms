"""项目统一路径与配置读取，不打印任何凭据。"""
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEEDTEST_AP_DIR = PROJECT_ROOT / "apps" / "speedtest-ap"
NEXUS_DIR = PROJECT_ROOT / "apps" / "nexus"
NEXUS_EXPORTER_DIR = NEXUS_DIR / "reyee-exporter"
NEXUS_DASHBOARD_DIR = NEXUS_DIR / "network-dashboard"
SECRETS_DIR = PROJECT_ROOT / "config" / "secrets"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"

# 诊断脚本继续复用应用中的同一个只读客户端，不复制实现。
if str(SPEEDTEST_AP_DIR) not in sys.path:
    sys.path.insert(0, str(SPEEDTEST_AP_DIR))


def load_env(filename: str) -> dict[str, str]:
    """从受保护的 config/secrets 读取键值，不接受目录穿越。"""
    if Path(filename).name != filename:
        raise ValueError("配置文件名不能包含路径")
    values = {}
    with (SECRETS_DIR / filename).open(encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def apply_env(filename: str) -> None:
    os.environ.update(load_env(filename))


def artifact_path(*parts: str) -> Path:
    path = ARTIFACTS_DIR.joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
