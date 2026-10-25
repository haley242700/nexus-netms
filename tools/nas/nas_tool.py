"""NAS 文件上传/长命令执行工具（不打印凭据）。"""
import base64
import sys

import paramiko

from tools.nas.nas_ssh import _load_env


def connect():
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
    return cli, env


def run(cli, cmd, timeout=60):
    _, out, err = cli.exec_command(cmd, timeout=timeout)
    return out.read().decode("utf-8", "replace"), err.read().decode("utf-8", "replace")


def sudo(cli, cmd, env, timeout=60):
    """以 root 执行整段命令（sh -c 包裹，&& 和管道都在 root 下）。"""
    import shlex
    return run(cli, f"echo '{env['NAS_PASSWORD']}' | sudo -S sh -c {shlex.quote(cmd)} 2>/dev/null", timeout)


def put(cli, env, local, remote):
    """本地文件 -> NAS 任意路径（base64 分块 + sudo 落盘）。"""
    data = base64.b64encode(open(local, "rb").read()).decode()
    tmp = "/tmp/nas_put.b64"
    run(cli, f"rm -f {tmp}")
    for i in range(0, len(data), 30000):
        part = data[i:i + 30000]
        out, err = run(cli, f"printf '%s' '{part}' >> {tmp}")
        if err.strip():
            raise RuntimeError(f"chunk failed: {err[:200]}")
    sudo(cli, f"base64 -d {tmp} > '{remote}' && rm -f {tmp} && wc -c '{remote}'", env)
    out, err = run(cli, f"wc -c '{remote}'")
    print(f"PUT {remote}: {out.strip() or err.strip()}")


def main():
    action = sys.argv[1]
    cli, env = connect()
    try:
        if action == "put":
            put(cli, env, sys.argv[2], sys.argv[3])
        elif action == "sudo":
            out, err = sudo(cli, sys.argv[2], env, timeout=int(sys.argv[3]) if len(sys.argv) > 3 else 60)
            print(out, end="")
            if err.strip():
                print(err, end="", file=sys.stderr)
        elif action == "run":
            out, err = run(cli, sys.argv[2], timeout=int(sys.argv[3]) if len(sys.argv) > 3 else 60)
            print(out, end="")
            if err.strip():
                print(err, end="", file=sys.stderr)
    finally:
        cli.close()


if __name__ == "__main__":
    main()
