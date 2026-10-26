"""Run an authenticated registry benchmark without writing registry secrets to disk."""
import json
import os

from tools.nas.nas_tool import connect


def main():
    cli, env = connect()
    try:
        registry = os.environ.get("XUANYUAN_REGISTRY", "https://docker.xuanyuan.run")
        command = f"sudo -S python3 /tmp/speedtest_registry_benchmark.py --authenticated-stdin {registry}"
        stdin, stdout, stderr = cli.exec_command(command, timeout=60)
        credentials = {
            "username": os.environ["XUANYUAN_USERNAME"],
            "password": os.environ["XUANYUAN_PASSWORD"],
        }
        stdin.write(env["NAS_PASSWORD"] + "\n" + json.dumps(credentials))
        stdin.channel.shutdown_write()
        print(stdout.read().decode("utf-8", "replace"), end="")
        error = stderr.read().decode("utf-8", "replace")
        if error.strip():
            print(error, end="")
    finally:
        cli.close()


if __name__ == "__main__":
    main()
