"""NAS SSH 只读执行器。凭据从 nas.env 读取，绝不打印。

用法: python nas_ssh.py "<命令>"
"""
import sys

import paramiko

from tools.common import load_env


def _load_env():
    return load_env("nas.env")


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "docker ps"
    env = _load_env()
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(
        hostname=env["NAS_HOST"],
        port=int(env.get("NAS_PORT", "22")),
        username=env["NAS_USER"],
        password=env["NAS_PASSWORD"],
        timeout=10,
        look_for_keys=False,
        allow_agent=False,
    )
    def run(c):
        _, out, err = cli.exec_command(c, timeout=30)
        return out.read().decode("utf-8", "replace"), err.read().decode("utf-8", "replace")

    stdout, stderr = run(cmd)
    if "permission denied" in (stderr + stdout).lower() or "denied" in stderr.lower():
        # 尝试 sudo（密码通过 stdin 传入，不回显）
        stdout, stderr = run(f"echo '{env['NAS_PASSWORD']}' | sudo -S {cmd} 2>/dev/null")
    cli.close()
    sys.stdout.write(stdout)
    if stderr.strip():
        sys.stderr.write(stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
