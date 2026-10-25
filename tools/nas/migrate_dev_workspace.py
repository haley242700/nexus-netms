"""Upload the Git bundle and local project secrets without printing their contents."""
from pathlib import Path

from tools.nas.nas_tool import connect, run, sudo

ROOT = Path(__file__).resolve().parents[2]
REMOTE_ROOT = "/volume1/docker/dev-workspace"


def main():
    cli, env = connect()
    try:
        sudo(cli, f"mkdir -p {REMOTE_ROOT}/secrets/project {REMOTE_ROOT}/workspace", env)
        files = [(ROOT / "artifacts/SpeedTest-migration.bundle", f"{REMOTE_ROOT}/workspace/SpeedTest-migration.bundle")]
        files += [(ROOT / "config/secrets" / name, f"{REMOTE_ROOT}/secrets/project/{name}")
                  for name in ("login.env", "nas.env", "cloud.env")
                  if (ROOT / "config/secrets" / name).is_file()]
        for index, (local, remote) in enumerate(files):
            temporary = f"/tmp/speedtest-migrate-{index}"
            stdin, stdout, stderr = cli.exec_command(f"cat > '{temporary}'", timeout=120)
            stdin.write(local.read_bytes())
            stdin.channel.shutdown_write()
            if stdout.channel.recv_exit_status() != 0:
                raise RuntimeError(stderr.read().decode("utf-8", "replace"))
            out, err = sudo(cli, f"mv '{temporary}' '{remote}' && chown 1000:1000 '{remote}'", env)
            if err.strip():
                raise RuntimeError(err)
            print(f"Uploaded {local.name} ({local.stat().st_size} bytes)")
        out, err = sudo(cli, f"chown -R 1000:1000 {REMOTE_ROOT}/secrets/project {REMOTE_ROOT}/workspace && chmod 700 {REMOTE_ROOT}/secrets/project && chmod 600 {REMOTE_ROOT}/secrets/project/* && chmod 644 {REMOTE_ROOT}/workspace/SpeedTest-migration.bundle", env)
        if err.strip():
            raise RuntimeError(err)
        print("Migration files uploaded; secret contents were not displayed.")
    finally:
        cli.close()


if __name__ == "__main__":
    main()
